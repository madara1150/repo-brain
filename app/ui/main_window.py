"""Repo Brain main window."""
from __future__ import annotations

import os
import sys
import threading
from datetime import datetime

from PySide6.QtCore import QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QRadioButton, QScrollArea, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from .. import claude_connect
from ..config import (APP_NAME, TEAM_EXT, VERSION, Source, TeamFileError, apply_team, data_dir, export_team,
                      index_path, load_config, read_team, save_config)
from ..github import GitHub, parse_repo
from ..i18n import language, set_language, tr
from ..store import Store
from ..sync import Cancelled, Syncer, check_updates, knowledge_repo
from . import styles


# ---------------------------------------------------------------------------- helpers
class Worker(QThread):
    progress = Signal(str, float)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.cancel = threading.Event()

    def run(self):
        try:
            res = self.fn(lambda msg, frac=None: self.progress.emit(msg or "", -1.0 if frac is None else float(frac)),
                          self.cancel)
        except Cancelled:
            self.failed.emit("cancelled")
        except Exception as e:  # shown to the user
            self.failed.emit(str(e) or type(e).__name__)
        else:
            self.done.emit(res)


def card(*widgets, layout=None) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    lay = layout or QVBoxLayout()
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    frame.setLayout(lay)
    for w in widgets:
        lay.addWidget(w)
    return frame


def label(text: str, name: str = "", wrap: bool = True, rich: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    if rich:
        lab.setTextFormat(Qt.RichText)
        lab.setOpenExternalLinks(True)
    return lab


def local_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------- dialogs
class AddRepoDialog(QDialog):
    def __init__(self, parent, existing: set[str]):
        super().__init__(parent)
        self.existing = existing
        self.setWindowTitle(tr("add_repo_title"))
        self.setMinimumWidth(460)
        form = QFormLayout()
        self.repo = QLineEdit()
        self.repo.setPlaceholderText("owner/name  ·  https://github.com/owner/name")
        self.branch = QLineEdit()
        self.branch.setPlaceholderText(tr("default_branch"))
        form.addRow(tr("add_repo_label"), self.repo)
        form.addRow(tr("branch_label"), self.branch)
        self.err = label("", "hint")
        self.err.setStyleSheet(f"color: {styles.BAD}")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.err)
        lay.addWidget(buttons)

    def _accept(self):
        repo = parse_repo(self.repo.text())
        if not repo:
            self.err.setText(tr("bad_repo"))
        elif repo.lower() in {r.lower() for r in self.existing}:
            self.err.setText(tr("dup_repo"))
        else:
            self.result_repo = repo
            self.result_branch = self.branch.text().strip()
            self.accept()


class KnowledgeDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("kn_dialog"))
        self.resize(620, 520)
        form = QFormLayout()
        self.title = QLineEdit()
        self.tags = QLineEdit()
        self.content = QPlainTextEdit()
        form.addRow(tr("kn_title"), self.title)
        form.addRow(tr("kn_tags"), self.tags)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(label(tr("kn_content")))
        lay.addWidget(self.content, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.save_btn = buttons.addButton(tr("kn_save"), QDialogButtonBox.AcceptRole)
        self.save_btn.setObjectName("primary")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self):
        if self.title.text().strip() and self.content.toPlainText().strip():
            self.accept()

    def values(self):
        tags = [t.strip() for t in self.tags.text().split(",") if t.strip()]
        return self.title.text().strip(), self.content.toPlainText().strip(), tags


class DepsDialog(QDialog):
    def __init__(self, parent, found: dict, unknown: list, odoo_version: str, existing: set[str]):
        super().__init__(parent)
        self.setWindowTitle(tr("deps_title"))
        self.resize(640, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("deps_intro", ver=odoo_version)))
        self.list = QListWidget()
        for repo, mods in sorted(found.items()):
            if repo.lower() in {r.lower() for r in existing}:
                continue
            item = QListWidgetItem(f"{repo}   ·   {tr('n_modules', n=len(mods))}: {', '.join(sorted(mods))}")
            item.setData(Qt.UserRole, repo)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.list.addItem(item)
        lay.addWidget(self.list, 1)
        if unknown:
            lay.addWidget(label(tr("deps_core", mods=", ".join(unknown)), "hint"))
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        add = buttons.addButton(tr("deps_add"), QDialogButtonBox.AcceptRole)
        add.setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def selected(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


# ---------------------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        set_language(self.cfg.language)
        self.store = Store(index_path())
        self.checks = {}
        self.worker = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(styles.resource("assets", "icon.png")))
        self.resize(1080, 740)
        self._build()
        if self.cfg.sources:
            QTimer.singleShot(1200, lambda: self.check_updates(quiet=True))

    # ---- layout
    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        head = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QPixmap(styles.resource("assets", "icon.png")).scaled(
            48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        head.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label(APP_NAME, "title", wrap=False))
        titles.addWidget(label(tr("subtitle"), "subtitle", wrap=False))
        head.addLayout(titles)
        head.addStretch(1)
        self.lang = QComboBox()
        self.lang.addItem("ไทย", "th")
        self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(1 if language() == "en" else 0)
        self.lang.currentIndexChanged.connect(self._change_language)
        head.addWidget(self.lang)
        root.addLayout(head)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._sources_tab(), tr("tab_sources"))
        self.tabs.addTab(self._knowledge_tab(), tr("tab_knowledge"))
        self.tabs.addTab(self._claude_tab(), tr("tab_claude"))
        self.tabs.addTab(self._settings_tab(), tr("tab_settings"))
        root.addWidget(self.tabs, 1)
        root.addWidget(self._update_bar())
        self.setCentralWidget(central)
        self.refresh()

    def _change_language(self):
        self.cfg.language = self.lang.currentData()
        save_config(self.cfg)
        set_language(self.cfg.language)
        tab = self.tabs.currentIndex()
        self._build()
        self.tabs.setCurrentIndex(tab)

    def _update_bar(self):
        bar = QFrame()
        bar.setObjectName("updateBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 12, 18, 12)
        left = QVBoxLayout()
        self.status = label("", wrap=True)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        left.addWidget(self.status)
        left.addWidget(self.progress)
        lay.addLayout(left, 1)
        self.check_btn = QPushButton(tr("check"))
        self.check_btn.clicked.connect(lambda: self.check_updates(quiet=False))
        self.update_btn = QPushButton(tr("update"))
        self.update_btn.setObjectName("primary")
        self.update_btn.setMinimumWidth(150)
        self.update_btn.clicked.connect(self._update_clicked)
        lay.addWidget(self.check_btn)
        lay.addWidget(self.update_btn)
        return bar

    def _sources_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.addWidget(label(tr("sources_hint"), "hint"))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([tr("col_repo"), tr("col_branch"), tr("col_commit"), tr("col_synced"),
                                              tr("col_files"), tr("col_state")])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        add = QPushButton("＋ " + tr("add_repo"))
        add.clicked.connect(self._add_repo)
        rm = QPushButton(tr("remove_repo"))
        rm.setObjectName("danger")
        rm.clicked.connect(self._remove_repo)
        deps = QPushButton(tr("find_deps"))
        deps.clicked.connect(self._find_deps)
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch(1)
        row.addWidget(deps)
        lay.addLayout(row)
        return page

    def _knowledge_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 10, 0, 0)
        k = self.cfg.knowledge

        self.kn_group = QButtonGroup(page)
        radios = QHBoxLayout()
        for mode, key in (("github", "kn_github"), ("folder", "kn_folder"), ("none", "kn_none")):
            rb = QRadioButton(tr(key))
            rb.setProperty("mode", mode)
            rb.setChecked(k.mode == mode)
            self.kn_group.addButton(rb)
            radios.addWidget(rb)
        radios.addStretch(1)
        self.kn_group.buttonToggled.connect(lambda *_: self._knowledge_changed())

        self.kn_repo = QLineEdit(k.repo)
        self.kn_repo.setPlaceholderText("owner/team-knowledge")
        self.kn_branch = QLineEdit(k.branch)
        self.kn_branch.setPlaceholderText(tr("default_branch"))
        self.kn_subdir = QLineEdit(k.subdir)
        self.kn_folder = QLineEdit(k.folder)
        browse = QPushButton(tr("browse"))
        browse.clicked.connect(self._browse_folder)
        for w in (self.kn_repo, self.kn_branch, self.kn_subdir, self.kn_folder):
            w.editingFinished.connect(self._knowledge_changed)

        self.gh_box = QWidget()
        g = QFormLayout(self.gh_box)
        g.setContentsMargins(0, 0, 0, 0)
        g.addRow(tr("kn_repo"), self.kn_repo)
        g.addRow(tr("col_branch"), self.kn_branch)
        g.addRow(tr("kn_subdir"), self.kn_subdir)
        g.addRow("", label(tr("kn_github_note"), "hint"))
        self.folder_box = QWidget()
        f = QFormLayout(self.folder_box)
        f.setContentsMargins(0, 0, 0, 0)
        fr = QHBoxLayout()
        fr.addWidget(self.kn_folder, 1)
        fr.addWidget(browse)
        f.addRow(tr("kn_folder_label"), fr)
        f.addRow("", label(tr("kn_folder_note"), "hint"))

        top = card(label(tr("kn_hint"), "hint"), label(tr("kn_where"), "sectionTitle"))
        top.layout().addLayout(radios)
        top.layout().addWidget(self.gh_box)
        top.layout().addWidget(self.folder_box)
        lay.addWidget(top)

        split = QSplitter()
        self.kn_list = QListWidget()
        self.kn_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.kn_list.setWordWrap(True)
        self.kn_list.setTextElideMode(Qt.ElideMiddle)
        self.kn_list.currentItemChanged.connect(self._show_note)
        self.kn_view = QTextBrowser()
        self.kn_view.setOpenExternalLinks(True)
        split.addWidget(self.kn_list)
        split.addWidget(self.kn_view)
        split.setSizes([400, 620])
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        self.kn_count = label("", "hint", wrap=False)
        row.addWidget(self.kn_count)
        row.addWidget(label(tr("kn_tip"), "hint"), 1)
        self.kn_add = QPushButton("＋ " + tr("kn_add"))
        self.kn_add.clicked.connect(self._add_note)
        row.addWidget(self.kn_add)
        lay.addLayout(row)
        self._knowledge_visibility()
        return page

    def _claude_tab(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 10, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)

        self.cl_state = label("", wrap=False)
        top = card(label(tr("cl_title"), "sectionTitle"), label(tr("cl_body"), "hint"), self.cl_state)
        row = QHBoxLayout()
        self.cl_connect = QPushButton(tr("cl_connect"))
        self.cl_connect.setObjectName("primary")
        self.cl_connect.clicked.connect(self._connect_claude)
        self.cl_disconnect = QPushButton(tr("cl_disconnect"))
        self.cl_disconnect.clicked.connect(self._disconnect_claude)
        row.addWidget(self.cl_connect)
        row.addWidget(self.cl_disconnect)
        row.addStretch(1)
        top.layout().addLayout(row)
        lay.addWidget(top)

        cols = QHBoxLayout()
        cols.addWidget(card(label(tr("cl_steps"), rich=True)), 1)
        cols.addWidget(card(label(tr("cl_examples"), rich=True)), 1)
        lay.addLayout(cols)

        cmd = QLineEdit(claude_connect.claude_code_command())
        cmd.setReadOnly(True)
        copy = QPushButton(tr("copy"))
        copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(cmd.text()), copy.setText(tr("copied"))))
        code = card(label(tr("cl_code"), "sectionTitle"))
        r2 = QHBoxLayout()
        r2.addWidget(cmd, 1)
        r2.addWidget(copy)
        code.layout().addLayout(r2)
        lay.addWidget(code)
        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    def _settings_tab(self):
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 10, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        scroll.setWidget(page)
        outer_lay.addWidget(scroll)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        team = card(label(tr("team_title"), "sectionTitle"), label(tr("team_hint"), "hint"))
        row = QHBoxLayout()
        imp = QPushButton(tr("team_import"))
        imp.setObjectName("primary")
        imp.clicked.connect(self._import_team)
        exp = QPushButton(tr("team_export"))
        exp.clicked.connect(self._export_team)
        row.addWidget(imp)
        row.addWidget(exp)
        row.addStretch(1)
        team.layout().addLayout(row)
        lay.addWidget(team)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(18)

        self.token = QLineEdit(self.cfg.github_token)
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("github_pat_…")
        self.token.editingFinished.connect(self._settings_changed)
        show = QCheckBox(tr("st_show"))
        show.toggled.connect(lambda on: self.token.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        test = QPushButton(tr("st_test"))
        test.clicked.connect(self._test_token)
        tr_row = QHBoxLayout()
        tr_row.addWidget(self.token, 1)
        tr_row.addWidget(show)
        tr_row.addWidget(test)
        form.addRow(tr("st_token"), tr_row)
        form.addRow("", label(tr("st_token_hint"), "hint", wrap=False, rich=True))  # short lines; wrapping clips in forms

        self.author = QLineEdit(self.cfg.author)
        self.author.editingFinished.connect(self._settings_changed)
        form.addRow(tr("st_author"), self.author)
        form.addRow("", label(tr("st_author_hint"), "hint"))

        self.odoo = QComboBox()
        self.odoo.setEditable(True)
        self.odoo.addItems(["18.0", "17.0", "16.0", "15.0", "14.0"])
        self.odoo.setCurrentText(self.cfg.odoo_version)
        self.odoo.currentTextChanged.connect(lambda *_: self._settings_changed())
        form.addRow(tr("st_odoo"), self.odoo)
        form.addRow("", label(tr("st_odoo_hint"), "hint"))

        dd = QHBoxLayout()
        path = QLineEdit(data_dir())
        path.setReadOnly(True)
        openb = QPushButton(tr("st_open"))
        openb.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(data_dir())))
        dd.addWidget(path, 1)
        dd.addWidget(openb)
        form.addRow(tr("st_data"), dd)
        box = card(layout=QVBoxLayout())
        box.layout().addLayout(form)
        lay.addWidget(box)
        lay.addWidget(card(label(tr("st_privacy"), "hint"), label(f"{APP_NAME} {VERSION} · MIT License", "hint")))
        lay.addStretch(1)
        return outer

    # ---- refresh views
    def refresh(self):
        self._fill_sources()
        self._fill_notes()
        self._fill_claude()
        self._fill_status()

    def _fill_sources(self):
        self.table.setRowCount(0)
        for s in self.cfg.sources:
            st = self.store.source(s.repo) or {}
            chk = self.checks.get(s.repo)
            if not st:
                state, color = tr("state_new"), styles.MUTED
            elif chk and chk.error:
                state, color = chk.error[:60], styles.BAD
            elif chk and chk.has_update:
                state, color = "● " + tr("state_behind"), styles.WARN
            elif chk:
                state, color = "✓ " + tr("state_ok"), styles.OK
            else:
                state, color = tr("state_unknown"), styles.MUTED
            cells = [s.repo, st.get("branch") or s.branch or tr("default_branch"), (st.get("sha") or "")[:7] or "—",
                     local_time(st.get("synced_at")), str(st.get("file_count") or "—"), state]
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 5:
                    item.setForeground(Qt.GlobalColor.black if color == styles.TEXT else _qcolor(color))
                if c == 0:
                    item.setToolTip(f"https://github.com/{s.repo}")
                self.table.setItem(r, c, item)
            self.table.setRowHeight(r, 36)

    def _fill_notes(self):
        current = self.kn_list.currentItem().data(Qt.UserRole) if self.kn_list.currentItem() else None
        self.kn_list.clear()
        repo = knowledge_repo(self.cfg)
        rows = [r for r in self.store.list_files(kind="knowledge", limit=2000)[0] if r["repo"] == repo] if repo else []
        for r in sorted(rows, key=lambda r: r["path"], reverse=True):
            text = self.store.read_file(r["repo"], r["path"]) or ""
            title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()), r["path"])
            item = QListWidgetItem(f"{title}\n{r['path']}")
            item.setData(Qt.UserRole, (r["repo"], r["path"]))
            self.kn_list.addItem(item)
            if (r["repo"], r["path"]) == current:
                self.kn_list.setCurrentItem(item)
        self.kn_count.setText(tr("kn_count", n=len(rows)))
        if not rows:
            self.kn_view.setMarkdown(tr("kn_list_empty"))
        elif self.kn_list.currentItem() is None:
            self.kn_list.setCurrentRow(0)
        self.kn_add.setEnabled(bool(repo))

    def _show_note(self, item, _prev=None):
        if item is None:
            return
        repo, path = item.data(Qt.UserRole)
        self.kn_view.setMarkdown(self.store.read_file(repo, path) or "")

    def _fill_claude(self):
        if not claude_connect.claude_desktop_found():
            text, color = tr("cl_no_desktop"), styles.WARN
        else:
            st = claude_connect.status()
            text, color = {"connected": (tr("cl_connected"), styles.OK), "outdated": (tr("cl_outdated"), styles.WARN),
                           "missing": (tr("cl_missing"), styles.MUTED)}[st]
        self.cl_state.setText(f"<span style='color:{color}; font-size:15px'>●</span>&nbsp; <b>{text}</b>")
        self.cl_disconnect.setEnabled(claude_connect.status() != "missing")

    def _fill_status(self):
        srcs = self.store.sources()
        if not srcs:
            self.status.setText(tr("idle_never"))
            return
        c = self.store.counts()
        when = local_time(max(s["synced_at"] for s in srcs))
        text = tr("idle_status", when=when, files=f"{c['files']:,}", modules=c["modules"], notes=c["knowledge"])
        behind = [x for x in self.checks.values() if x.has_update]
        if behind:
            text += f"<br><span style='color:{styles.WARN}'>● {tr('has_updates', n=len(behind))}</span>"
        self.status.setText(text)

    # ---- sources actions
    def _add_repo(self):
        dlg = AddRepoDialog(self, {s.repo for s in self.cfg.sources})
        if dlg.exec() == QDialog.Accepted:
            self.cfg.sources.append(Source(dlg.result_repo, dlg.result_branch))
            save_config(self.cfg)
            self._fill_sources()

    def _remove_repo(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.cfg.sources):
            return
        repo = self.cfg.sources[r].repo
        if QMessageBox.question(self, APP_NAME, tr("confirm_remove", repo=repo)) != QMessageBox.Yes:
            return
        del self.cfg.sources[r]
        save_config(self.cfg)
        self.store.remove_source(repo)
        self.checks.pop(repo, None)
        self.refresh()

    def _find_deps(self):
        from ..deps import suggest_repos
        missing = self.store.missing_depends()
        if not missing:
            QMessageBox.information(self, tr("deps_title"), tr("deps_none"))
            return
        ver = self.cfg.odoo_version
        self._run(lambda progress, cancel: suggest_repos(missing, ver, progress),
                  lambda res: self._deps_found(*res), busy=tr("deps_running"))

    def _deps_found(self, found, unknown):
        dlg = DepsDialog(self, found, unknown, self.cfg.odoo_version, {s.repo for s in self.cfg.sources})
        if dlg.exec() == QDialog.Accepted:
            for repo in dlg.selected():
                self.cfg.sources.append(Source(repo, self.cfg.odoo_version))
            save_config(self.cfg)
            self._fill_sources()

    # ---- update / check
    def _update_clicked(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            return
        cfg = self.cfg

        def job(progress, cancel):
            store = Store(index_path())
            try:
                return Syncer(cfg, store, progress=progress, cancel=cancel).run()
            finally:
                store.close()
        self._run(job, self._update_done, busy=tr("updating", msg=""), cancellable=True)

    def _update_done(self, results):
        parts, failed = [], False
        for r in results:
            name = r.repo.split("/")[-1]
            if r.mode == "error":
                failed = True
                parts.append(f"{name}: {tr('mode_error')} ({r.error})")
            elif r.mode == "incremental":
                parts.append(f"{name}: {tr('mode_incremental', n=r.changed)}")
            elif r.mode == "folder":
                parts.append(f"{name}: {tr('mode_folder', n=r.changed)}")
            else:
                parts.append(f"{name}: {tr('mode_' + r.mode)}")
        for r in results:
            if r.mode != "error" and r.repo in self.checks:
                self.checks[r.repo].local_sha = r.new_sha or self.checks[r.repo].local_sha
                self.checks[r.repo].remote_sha = r.new_sha or self.checks[r.repo].remote_sha
        self.refresh()
        msg = tr("update_done", summary=" · ".join(parts) if parts else "—")
        self.status.setText(self.status.text() + f"<br><span style='color:{styles.BAD if failed else styles.OK}'>{msg}</span>")

    def check_updates(self, quiet=False):
        if self.worker and self.worker.isRunning():
            return
        cfg = self.cfg

        def job(progress, cancel):
            store = Store(index_path())
            try:
                return check_updates(cfg, store)
            finally:
                store.close()

        def done(checks):
            self.checks = {c.repo: c for c in checks}
            self.refresh()
            if not quiet and not any(c.has_update for c in checks):
                self.status.setText(self.status.text() + f"<br><span style='color:{styles.OK}'>✓ {tr('no_updates')}</span>")
        self._run(job, done, busy=tr("checking"), quiet=quiet)

    def _run(self, fn, on_done, busy="", cancellable=False, quiet=False):
        self.worker = Worker(fn, self)
        self.update_btn.setText(tr("cancel") if cancellable else tr("update"))
        self.update_btn.setEnabled(cancellable)
        self.check_btn.setEnabled(False)
        if not quiet:
            self.progress.show()
            self.progress.setRange(0, 0)
            self.status.setText(busy)

        def progress(msg, frac):
            if quiet:
                return
            if frac >= 0:
                self.progress.setRange(0, 100)
                self.progress.setValue(int(frac * 100))
            if msg:
                self.status.setText(tr("updating", msg=msg) if cancellable else f"{busy} {msg}")

        def finish():
            self.progress.hide()
            self.update_btn.setText(tr("update"))
            self.update_btn.setEnabled(True)
            self.check_btn.setEnabled(True)

        def ok(res):
            finish()
            on_done(res)

        def fail(err):
            finish()
            self.refresh()
            if err != "cancelled" and not quiet:
                QMessageBox.warning(self, tr("error"), err)
        self.worker.progress.connect(progress)
        self.worker.done.connect(ok)
        self.worker.failed.connect(fail)
        self.worker.start()

    # ---- knowledge actions
    def _knowledge_visibility(self):
        mode = self.cfg.knowledge.mode
        self.gh_box.setVisible(mode == "github")
        self.folder_box.setVisible(mode == "folder")

    def _knowledge_changed(self):
        k = self.cfg.knowledge
        btn = self.kn_group.checkedButton()
        k.mode = btn.property("mode") if btn else "none"
        k.repo = parse_repo(self.kn_repo.text()) or self.kn_repo.text().strip()
        k.branch = self.kn_branch.text().strip()
        k.subdir = self.kn_subdir.text().strip().strip("/")
        k.folder = self.kn_folder.text().strip()
        save_config(self.cfg)
        self._knowledge_visibility()
        self._fill_notes()

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("kn_folder_label"), self.kn_folder.text() or os.path.expanduser("~"))
        if folder:
            self.kn_folder.setText(folder)
            self._knowledge_changed()

    def _add_note(self):
        dlg = KnowledgeDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        title, content, tags = dlg.values()
        cfg = self.cfg

        def job(progress, cancel):
            from ..knowledge import add_entry
            store = Store(index_path())
            try:
                return add_entry(cfg, store, title, content, tags)
            finally:
                store.close()

        def done(where):
            self._fill_notes()
            self._fill_status()
            QMessageBox.information(self, tr("kn_dialog"), tr("kn_saved", where=where))
        self._run(job, done, busy=tr("kn_save"))

    # ---- claude / settings actions
    def _connect_claude(self):
        try:
            path = claude_connect.install()
        except ValueError:
            QMessageBox.warning(self, tr("error"), tr("cl_broken", path=claude_connect.desktop_config_path()))
            return
        except OSError as e:
            QMessageBox.warning(self, tr("error"), str(e))
            return
        self._fill_claude()
        QMessageBox.information(self, APP_NAME, tr("cl_done", path=path))

    def _disconnect_claude(self):
        try:
            claude_connect.uninstall()
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, tr("error"), str(e))
        self._fill_claude()

    def _settings_changed(self):
        self.cfg.github_token = self.token.text().strip()
        self.cfg.author = self.author.text().strip()
        self.cfg.odoo_version = self.odoo.currentText().strip() or "16.0"
        save_config(self.cfg)

    def _export_team(self):
        self._settings_changed()
        self._knowledge_changed()
        include = False
        if self.cfg.github_token:
            ans = QMessageBox.question(self, tr("team_export"), tr("team_ask_token"),
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
            if ans == QMessageBox.Cancel:
                return
            include = ans == QMessageBox.Yes
        path, _ = QFileDialog.getSaveFileName(self, tr("team_export"),
                                              os.path.join(os.path.expanduser("~"), "team" + TEAM_EXT),
                                              f"Repo Brain (*{TEAM_EXT})")
        if not path:
            return
        if not path.endswith(TEAM_EXT):
            path += TEAM_EXT
        try:
            export_team(self.cfg, path, include)
        except OSError as e:
            QMessageBox.warning(self, tr("error"), str(e))
            return
        QMessageBox.information(self, tr("team_export"),
                                tr("team_exported_token" if include else "team_exported", path=path))

    def _import_team(self, path: str = ""):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, tr("team_import"), os.path.expanduser("~"),
                                                  f"Repo Brain (*{TEAM_EXT} *.json)")
        if not path:
            return
        try:
            data = read_team(path)
        except TeamFileError as e:
            QMessageBox.warning(self, tr("error"), tr("team_bad", err=str(e)))
            return
        new = apply_team(self.cfg, data)
        repos = "\n".join(f"  • {s.repo} ({s.branch or tr('default_branch')})" for s in new.sources) or "  —"
        k = new.knowledge
        kn = {"github": f"GitHub: {k.repo}", "folder": tr("kn_folder"), "none": tr("kn_none")}.get(k.mode, k.mode)
        summary = tr("team_summary", repos=repos, knowledge=kn, odoo=new.odoo_version,
                     token=tr("team_has_token") if data.get("github_token") else tr("team_no_token"))
        if QMessageBox.question(self, tr("team_import"), summary) != QMessageBox.Yes:
            return
        self.cfg = new
        save_config(self.cfg)
        self.checks = {}
        self._build()
        self.tabs.setCurrentIndex(3 if not self.cfg.author else 0)
        msg = tr("team_imported")
        if not self.cfg.author:
            msg += "\n\n" + tr("team_need_name")
            self.author.setFocus()
        if k.mode == "folder" and not k.folder:
            msg += "\n\n" + tr("team_need_folder")
        QMessageBox.information(self, tr("team_import"), msg)

    def _test_token(self):
        self._settings_changed()
        token = self.cfg.github_token
        self._run(lambda p, c: GitHub(token).current_user(),
                  lambda login: QMessageBox.information(self, APP_NAME, tr("st_token_ok", login=login)),
                  busy=tr("checking"))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.worker.wait(5000)
        super().closeEvent(event)


def _qcolor(hex_color):
    from PySide6.QtGui import QColor
    return QColor(hex_color)


def run_app():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    family = styles.load_fonts()
    from PySide6.QtGui import QFont
    app.setFont(QFont(family, 13))
    app.setStyleSheet(styles.stylesheet(family))
    win = MainWindow()
    win.show()
    return app.exec()
