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
from ..config import (APP_NAME, config_path, TEAM_EXT, VERSION, Source, TeamFileError, apply_team, data_dir, export_team,
                      index_path, load_config, read_team, save_config)
from ..github import GitHub, parse_repo
from ..i18n import language, set_language, tr
from ..store import Store
from .. import line_chat, questions, teach, updater
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



# ---------------------------------------------------------------------------- message boxes in the UI language
_BUTTON_TEXT = {"Ok": "btn_ok", "Cancel": "btn_cancel", "Yes": "btn_yes", "No": "btn_no", "Close": "btn_close"}


def localize(box):
    """Qt ships no Thai translation for standard buttons: label them ourselves."""
    if isinstance(box, QMessageBox):
        for b in box.buttons():
            key = _BUTTON_TEXT.get(QMessageBox.StandardButton(box.standardButton(b)).name)
            if key:
                b.setText(tr(key))
    else:
        for name, key in _BUTTON_TEXT.items():
            b = box.button(getattr(QDialogButtonBox.StandardButton, name))
            if b is not None:
                b.setText(tr(key))
    return box


def make_box(parent, icon, title, text, buttons, default=None):
    box = QMessageBox(icon, title, text, buttons, parent)
    if default is not None:
        box.setDefaultButton(default)
    return localize(box)


def ask(parent, title, text, buttons=QMessageBox.Yes | QMessageBox.No, default=None):
    return QMessageBox.StandardButton(make_box(parent, QMessageBox.Question, title, text, buttons, default).exec())


def info(parent, title, text):
    make_box(parent, QMessageBox.Information, title, text, QMessageBox.Ok).exec()


def warn(parent, title, text):
    make_box(parent, QMessageBox.Warning, title, text, QMessageBox.Ok).exec()


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
        localize(buttons)
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
        localize(buttons)
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
        localize(buttons)
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
        self._release = None
        self._release_dismissed = False
        self.upd_worker = None
        if getattr(sys, "frozen", False) or os.environ.get("REPO_BRAIN_UPDATE_CHECK"):
            QTimer.singleShot(3000, lambda: self.check_app_update(manual=False))

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
        root.addWidget(self._update_banner())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._sources_tab(), tr("tab_sources"))
        self.tabs.addTab(self._knowledge_tab(), tr("tab_knowledge"))
        self.questions_index = self.tabs.addTab(self._questions_tab(), tr("tab_questions"))
        self.tabs.addTab(self._teach_tab(), tr("tab_teach"))
        self.tabs.addTab(self._claude_tab(), tr("tab_claude"))
        self.settings_index = self.tabs.addTab(self._settings_tab(), tr("tab_settings"))
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

    def _update_banner(self):
        bar = QFrame()
        bar.setObjectName("updateBanner")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 12, 10)
        self.up_label = label("", wrap=True)
        self.up_label.setTextFormat(Qt.RichText)
        lay.addWidget(self.up_label, 1)
        self.up_notes = QPushButton(tr("up_notes"))
        self.up_notes.clicked.connect(self._show_release_notes)
        self.up_go = QPushButton(tr("up_now"))
        self.up_go.setObjectName("primary")
        self.up_go.clicked.connect(self._start_app_update)
        self.up_later = QPushButton(tr("up_later"))
        self.up_later.clicked.connect(self._dismiss_update)
        for b in (self.up_notes, self.up_go, self.up_later):
            lay.addWidget(b)
        bar.setVisible(bool(getattr(self, "_release", None)) and not getattr(self, "_release_dismissed", False))
        self.up_banner = bar
        if bar.isVisible():
            self._show_update_banner()
        return bar

    def check_app_update(self, manual=False):
        if self.upd_worker and self.upd_worker.isRunning():
            return
        self.upd_worker = Worker(lambda p, c: updater.fetch_latest(), self)

        def done(rel):
            if rel.version and updater.is_newer(rel.version):
                self._release = rel
                self._release_dismissed = False
                self._show_update_banner()
            elif manual:
                info(self, APP_NAME, tr("up_latest", ver=VERSION))

        def fail(err):
            if manual:
                warn(self, tr("error"), tr("up_failed", err=err))
        self.upd_worker.done.connect(done)
        self.upd_worker.failed.connect(fail)
        self.upd_worker.start()

    def _show_update_banner(self):
        rel = self._release
        if not rel:
            return
        self.up_label.setText(tr("up_available", new=rel.version, cur=VERSION))
        self.up_go.setText(tr("up_now") if updater.can_self_update() and rel.asset_url else tr("up_download"))
        self.up_banner.show()

    def _dismiss_update(self):
        self._release_dismissed = True
        self.up_banner.hide()

    def _show_release_notes(self):
        rel = self._release
        if not rel:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("up_notes_title", ver=rel.version))
        dlg.resize(620, 480)
        lay = QVBoxLayout(dlg)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setMarkdown(rel.notes or tr("up_no_notes"))
        lay.addWidget(view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        go = buttons.addButton(self.up_go.text(), QDialogButtonBox.AcceptRole)
        go.setObjectName("primary")
        localize(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() == QDialog.Accepted:
            self._start_app_update()

    def _start_app_update(self):
        rel = self._release
        if not rel:
            return
        if not updater.can_self_update() or not rel.asset_url:
            QDesktopServices.openUrl(QUrl(rel.page or updater.RELEASES_PAGE))
            return
        if ask(self, APP_NAME, tr("up_confirm", ver=rel.version)) != QMessageBox.Yes:
            return
        if self.worker and self.worker.isRunning():
            warn(self, APP_NAME, tr("up_busy"))
            return
        self.up_go.setEnabled(False)
        self.up_later.setEnabled(False)
        self.upd_worker = Worker(lambda progress, cancel: updater.download(
            rel, lambda done, total: progress(tr("up_downloading", pct=int(done * 100 / total) if total else 0),
                                              done / total if total else None)), self)
        self.upd_worker.progress.connect(lambda msg, frac: self.up_label.setText(msg))

        def done(path):
            try:
                updater.launch_installer(path)
            except Exception as e:  # noqa: BLE001 - shown to the user
                fail(str(e))
                return
            QApplication.instance().quit()

        def fail(err):
            self.up_go.setEnabled(True)
            self.up_later.setEnabled(True)
            self._show_update_banner()
            warn(self, tr("error"), tr("up_failed", err=err))
        self.upd_worker.done.connect(done)
        self.upd_worker.failed.connect(fail)
        self.upd_worker.start()

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

    def _questions_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 10, 0, 0)
        self.questions = []
        lay.addWidget(label(tr("q_hint"), "hint"))
        row = QHBoxLayout()
        self.q_filter = QComboBox()
        for key, val in (("q_open", "open"), ("q_answered", "answered"), ("q_all", "all")):
            self.q_filter.addItem(tr(key), val)
        self.q_area = QComboBox()
        self.q_search = QLineEdit()
        self.q_search.setPlaceholderText(tr("q_search"))
        self.q_count = label("", "hint", wrap=False)
        new_btn = QPushButton("＋ " + tr("q_new"))
        new_btn.clicked.connect(self._new_question)
        for w in (self.q_filter, self.q_area):
            w.currentIndexChanged.connect(lambda *_: self._fill_questions())
        self.q_search.textChanged.connect(lambda *_: self._fill_questions())
        row.addWidget(self.q_filter)
        row.addWidget(self.q_area)
        row.addWidget(self.q_search, 1)
        row.addWidget(self.q_count)
        row.addWidget(new_btn)
        lay.addLayout(row)

        split = QSplitter()
        self.q_list = QListWidget()
        self.q_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.q_list.setWordWrap(True)
        self.q_list.currentItemChanged.connect(lambda *_: self._show_question())
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.q_view = QTextBrowser()
        self.q_view.setOpenExternalLinks(True)
        rl.addWidget(self.q_view, 3)
        rl.addWidget(label(tr("q_your_answer"), "sectionTitle"))
        self.q_answer = QPlainTextEdit()
        self.q_answer.setPlaceholderText(tr("q_answer_ph"))
        rl.addWidget(self.q_answer, 2)
        r2 = QHBoxLayout()
        self.q_status = label("", "hint")
        r2.addWidget(self.q_status, 1)
        self.q_send = QPushButton(tr("q_send"))
        self.q_send.setObjectName("primary")
        self.q_send.clicked.connect(self._send_answer)
        r2.addWidget(self.q_send)
        rl.addLayout(r2)
        split.addWidget(self.q_list)
        split.addWidget(right)
        split.setSizes([420, 600])
        lay.addWidget(split, 1)
        self._load_questions()
        return page

    def _load_questions(self, keep_path: str = ""):
        from ..sync import knowledge_repo
        repo = knowledge_repo(self.cfg)
        self.questions = questions.list_questions(self.store, repo) if repo else []
        areas = sorted({q["area"] for q in self.questions if q["area"]})
        current = self.q_area.currentData()
        self.q_area.blockSignals(True)
        self.q_area.clear()
        self.q_area.addItem(tr("q_all_areas"), "")
        for a in areas:
            self.q_area.addItem(a, a)
        idx = self.q_area.findData(current)
        self.q_area.setCurrentIndex(max(idx, 0))
        self.q_area.blockSignals(False)
        self._fill_questions(keep_path)
        n_open = sum(1 for q in self.questions if q["status"] == "open")
        if hasattr(self, "questions_index"):
            self.tabs.setTabText(self.questions_index, tr("tab_questions") + (f" ({n_open})" if n_open else ""))

    def _fill_questions(self, keep_path: str = ""):
        keep_path = keep_path or (self.q_list.currentItem().data(Qt.UserRole) if self.q_list.currentItem() else "")
        status, area = self.q_filter.currentData(), self.q_area.currentData()
        text = self.q_search.text().strip().lower()
        shown = [q for q in self.questions
                 if (status == "all" or q["status"] == status) and (not area or q["area"] == area)
                 and (not text or text in (q["title"] + " " + q["details"]).lower())]
        self.q_list.blockSignals(True)
        self.q_list.clear()
        for q in shown:
            mark = "✓ " if q["status"] == "answered" else ""
            item = QListWidgetItem(f"{mark}{q['title']}\n{q['area']} · {tr('q_n_answers', n=len(q['answers']))}")
            item.setData(Qt.UserRole, q["path"])
            self.q_list.addItem(item)
            if q["path"] == keep_path:
                self.q_list.setCurrentItem(item)
        self.q_list.blockSignals(False)
        if self.q_list.currentItem() is None and self.q_list.count():
            self.q_list.setCurrentRow(0)
        self._show_question()
        self.q_count.setText(tr("q_count", shown=len(shown), total=len(self.questions)))
        ready = bool(self.questions) or bool(self._knowledge_ready())
        self.q_send.setEnabled(bool(shown) and ready)
        if not self._knowledge_ready():
            self.q_view.setMarkdown(tr("q_no_repo"))
        elif not self.questions:
            self.q_view.setMarkdown(tr("q_empty"))

    def _knowledge_ready(self) -> bool:
        from ..sync import knowledge_repo
        return bool(knowledge_repo(self.cfg))

    def _current_question(self):
        item = self.q_list.currentItem()
        if item is None:
            return None
        path = item.data(Qt.UserRole)
        return next((q for q in self.questions if q["path"] == path), None)

    def _show_question(self):
        q = self._current_question()
        if q is None:
            self.q_view.clear()
            return
        st = tr("q_answered") if q["status"] == "answered" else tr("q_open")
        md = [f"### {q['title']}", f"{q['area']} · **{st}**", ""]
        if q["details"] and q["details"] != q["title"]:
            md += [q["details"], ""]
        if q["note"]:
            md += [f"{tr('q_related')}: `{q['note']}`", ""]
        md.append(f"#### {tr('q_answers')} ({len(q['answers'])})")
        for a in q["answers"]:
            md += ["", f"**{a['author']}** · {a['date']}", "", a["text"]]
        if not q["answers"]:
            md += ["", tr("q_no_answers")]
        self.q_view.setMarkdown("\n".join(md))

    def _send_answer(self):
        q = self._current_question()
        text = self.q_answer.toPlainText().strip()
        if q is None or not text:
            return
        if not self.cfg.author:
            warn(self, tr("error"), tr("q_need_name"))
            self.tabs.setCurrentIndex(self.settings_index)
            self.author.setFocus()
            return
        cfg, path = self.cfg, q["path"]

        def job(progress, cancel):
            store = Store(index_path())
            try:
                return questions.answer_question(cfg, store, path, text)
            finally:
                store.close()

        def done(_):
            self.q_answer.clear()
            self._load_questions(path)
            self.q_status.setText(tr("q_sent"))
        self._run(job, done, busy=tr("q_sending"))

    def _new_question(self):
        if not self._knowledge_ready():
            warn(self, tr("error"), tr("q_no_repo"))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("q_new"))
        dlg.resize(560, 380)
        form = QFormLayout()
        title = QLineEdit()
        area = QComboBox()
        area.setEditable(True)
        area.addItems(sorted({q["area"] for q in self.questions if q["area"]}) or [tr("q_default_area")])
        details = QPlainTextEdit()
        form.addRow(tr("q_question"), title)
        form.addRow(tr("q_area"), area)
        form.addRow(tr("q_details"), details)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        localize(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay = QVBoxLayout(dlg)
        lay.addLayout(form)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.Accepted or not title.text().strip():
            return
        cfg = self.cfg
        t, a, d = title.text().strip(), area.currentText().strip(), details.toPlainText().strip()

        def job(progress, cancel):
            store = Store(index_path())
            try:
                return questions.ask_question(cfg, store, t, a, d)
            finally:
                store.close()
        self._run(job, lambda path: (self._load_questions(path), self.q_status.setText(tr("q_asked"))),
                  busy=tr("q_sending"))

    def _teach_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 10, 0, 0)
        self.cases = []
        self.cases_done = self._load_done()

        line_card = card(label(tr("te_line_title"), "sectionTitle"), label(tr("te_line_hint"), "hint"))
        r1 = QHBoxLayout()
        open_btn = QPushButton(tr("te_open"))
        open_btn.clicked.connect(self._open_line_file)
        paste_btn = QPushButton(tr("te_paste"))
        paste_btn.clicked.connect(self._paste_chat)
        r1.addWidget(open_btn)
        r1.addWidget(paste_btn)
        r1.addStretch(1)
        line_card.layout().addLayout(r1)
        line_card.layout().addWidget(label(tr("te_screens"), "hint", rich=True))

        flow_card = card(label(tr("te_flow_title"), "sectionTitle"), label(tr("te_flow_hint"), "hint"))
        r2 = QHBoxLayout()
        self.flow_topic = QLineEdit()
        self.flow_topic.setPlaceholderText(tr("te_flow_ph"))
        flow_btn = QPushButton(tr("te_flow_copy"))
        flow_btn.setObjectName("primary")
        flow_btn.clicked.connect(self._copy_flow)
        r2.addWidget(self.flow_topic, 1)
        r2.addWidget(flow_btn)
        flow_card.layout().addLayout(r2)
        top = QHBoxLayout()
        top.addWidget(line_card, 1)
        top.addWidget(flow_card, 1)
        lay.addLayout(top)

        split = QSplitter()
        self.case_list = QListWidget()
        self.case_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.case_list.setWordWrap(True)
        self.case_list.currentRowChanged.connect(self._show_case)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.case_text = QPlainTextEdit()
        self.case_text.setPlaceholderText(tr("te_empty"))
        rl.addWidget(self.case_text, 1)
        r3 = QHBoxLayout()
        self.teach_status = label("", "hint")
        r3.addWidget(self.teach_status, 1)
        self.done_btn = QPushButton(tr("te_done"))
        self.done_btn.clicked.connect(self._mark_done)
        self.copy_case_btn = QPushButton(tr("te_copy_case"))
        self.copy_case_btn.setObjectName("primary")
        self.copy_case_btn.clicked.connect(self._copy_case)
        r3.addWidget(self.done_btn)
        r3.addWidget(self.copy_case_btn)
        rl.addLayout(r3)
        split.addWidget(self.case_list)
        split.addWidget(right)
        split.setSizes([330, 690])
        lay.addWidget(split, 1)
        self._fill_cases()
        return page

    # ---- teach actions
    def _done_path(self):
        return os.path.join(os.path.dirname(config_path()), "cases_done.json")

    def _load_done(self) -> set:
        import json
        try:
            with open(self._done_path(), encoding="utf-8") as fh:
                return set(json.load(fh))
        except (OSError, ValueError):
            return set()

    def _save_done(self):
        import json
        with open(self._done_path(), "w", encoding="utf-8") as fh:
            json.dump(sorted(self.cases_done), fh)

    def _load_chat(self, text: str):
        self.cases = line_chat.split_cases(text)
        self._fill_cases()
        first_open = next((i for i, c in enumerate(self.cases) if c.key not in self.cases_done), 0)
        if self.cases:
            self.case_list.setCurrentRow(first_open)
        self.teach_status.setText(tr("te_loaded", n=len(self.cases)))

    def _fill_cases(self):
        self.case_list.clear()
        for c in self.cases:
            mark = "✓ " if c.key in self.cases_done else ""
            item = QListWidgetItem(f"{mark}{c.date or '—'} · {tr('te_msgs', n=len(c.messages))}\n{c.preview}")
            if c.key in self.cases_done:
                item.setForeground(_qcolor(styles.MUTED))
            self.case_list.addItem(item)
        has = bool(self.cases)
        self.copy_case_btn.setEnabled(has)
        self.done_btn.setEnabled(has)

    def _show_case(self, row):
        if 0 <= row < len(self.cases):
            self.case_text.setPlainText(self.cases[row].text)

    def _open_line_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("te_open"), os.path.expanduser("~"), "LINE chat (*.txt);;All (*)")
        if not path:
            return
        with open(path, "rb") as fh:
            raw = fh.read()
        for enc in ("utf-8-sig", "utf-16", "cp874"):
            try:
                self._load_chat(raw.decode(enc))
                return
            except UnicodeDecodeError:
                continue
        self._load_chat(raw.decode("utf-8", "replace"))

    def _paste_chat(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("te_paste"))
        dlg.resize(620, 480)
        lay = QVBoxLayout(dlg)
        lay.addWidget(label(tr("te_paste_hint"), "hint"))
        box = QPlainTextEdit()
        box.setPlainText(QGuiApplication.clipboard().text())
        lay.addWidget(box, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        localize(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() == QDialog.Accepted and box.toPlainText().strip():
            self._load_chat(box.toPlainText())

    def _copy_case(self):
        text = self.case_text.toPlainText().strip()
        if not text:
            return
        # anything typed or pasted into the editor gets the same redaction
        QGuiApplication.clipboard().setText(teach.case_prompt(line_chat.redact(text, {})))
        self.teach_status.setText(tr("te_copied"))

    def _mark_done(self):
        row = self.case_list.currentRow()
        if 0 <= row < len(self.cases):
            self.cases_done.add(self.cases[row].key)
            self._save_done()
            self._fill_cases()
            nxt = next((i for i, c in enumerate(self.cases) if c.key not in self.cases_done), row)
            self.case_list.setCurrentRow(nxt)

    def _copy_flow(self):
        QGuiApplication.clipboard().setText(teach.flow_prompt(self.flow_topic.text()))
        self.teach_status.setText(tr("te_copied"))

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
        about = card(label(tr("st_privacy"), "hint"))
        ar = QHBoxLayout()
        ar.addWidget(label(f"{APP_NAME} {VERSION} · MIT License", "hint"), 1)
        upd = QPushButton(tr("up_check"))
        upd.clicked.connect(lambda: self.check_app_update(manual=True))
        ar.addWidget(upd)
        about.layout().addLayout(ar)
        lay.addWidget(about)
        lay.addStretch(1)
        return outer

    # ---- refresh views
    def refresh(self):
        self._fill_sources()
        self._fill_notes()
        self._load_questions()
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
        rows = [r for r in self.store.list_files(kind="knowledge", limit=5000)[0]
                if r["repo"] == repo and not r["path"].startswith("questions/")] if repo else []
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
        if ask(self, APP_NAME, tr("confirm_remove", repo=repo)) != QMessageBox.Yes:
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
            info(self, tr("deps_title"), tr("deps_none"))
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
                self.status.setText(tr("updating", msg=_progress_text(msg)) if cancellable else f"{busy} {msg}")

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
                warn(self, tr("error"), err)
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
            info(self, tr("kn_dialog"), tr("kn_saved", where=where))
        self._run(job, done, busy=tr("kn_save"))

    # ---- claude / settings actions
    def _connect_claude(self):
        try:
            path = claude_connect.install()
        except ValueError:
            warn(self, tr("error"), tr("cl_broken", path=claude_connect.desktop_config_path()))
            return
        except OSError as e:
            warn(self, tr("error"), str(e))
            return
        self._fill_claude()
        info(self, APP_NAME, tr("cl_done", path=path))

    def _disconnect_claude(self):
        try:
            claude_connect.uninstall()
        except (OSError, ValueError) as e:
            warn(self, tr("error"), str(e))
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
            ans = ask(self, tr("team_export"), tr("team_ask_token"),
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
            warn(self, tr("error"), str(e))
            return
        info(self, tr("team_export"),
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
            warn(self, tr("error"), tr("team_bad", err=str(e)))
            return
        new = apply_team(self.cfg, data)
        repos = "\n".join(f"  • {s.repo} ({s.branch or tr('default_branch')})" for s in new.sources) or "  —"
        k = new.knowledge
        kn = {"github": f"GitHub: {k.repo}", "folder": tr("kn_folder"), "none": tr("kn_none")}.get(k.mode, k.mode)
        summary = tr("team_summary", repos=repos, knowledge=kn, odoo=new.odoo_version,
                     token=tr("team_has_token") if data.get("github_token") else tr("team_no_token"))
        if ask(self, tr("team_import"), summary) != QMessageBox.Yes:
            return
        self.cfg = new
        save_config(self.cfg)
        self.checks = {}
        self._build()
        self.tabs.setCurrentIndex(self.settings_index if not self.cfg.author else 0)
        msg = tr("team_imported")
        if not self.cfg.author:
            msg += "\n\n" + tr("team_need_name")
            self.author.setFocus()
        if k.mode == "folder" and not k.folder:
            msg += "\n\n" + tr("team_need_folder")
        info(self, tr("team_import"), msg)

    def _test_token(self):
        self._settings_changed()
        token = self.cfg.github_token
        self._run(lambda p, c: GitHub(token).current_user(),
                  lambda login: info(self, APP_NAME, tr("st_token_ok", login=login)),
                  busy=tr("checking"))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.worker.wait(5000)
        super().closeEvent(event)


def _progress_text(msg: str) -> str:
    """Sync progress comes from the engine in English; show it in the UI language."""
    if language() != "th":
        return msg
    import re
    msg = re.sub(r": downloading$", ": กำลังดาวน์โหลด", msg)
    msg = re.sub(r": indexing (\d+) files$", r": กำลังทำดัชนี \1 ไฟล์", msg)
    return re.sub(r": (\d+) files$", r": \1 ไฟล์", msg)


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
