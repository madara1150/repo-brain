"""Step-by-step screenshots for the user guide, taken from the real app -> docs/screenshots/guide/*-th.png / *-en.png.

Needs the data prepared by tools/screenshots.py (build/screenshot-home). Dialogs are the app's own
dialogs, filled the way a user would fill them. Network is used for the live update and the PyPI lookup.
Run:  QT_QPA_PLATFORM=offscreen .venv/bin/python tools/guide_shots.py
"""
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(ROOT, "build", "screenshot-home")
OUT = os.path.join(ROOT, "docs", "screenshots", "guide")
sys.path.insert(0, ROOT)
os.environ["REPO_BRAIN_HOME"] = HOME


def pump(app, n=8):
    for _ in range(n):
        app.processEvents()


def save(widget, name, lang):
    path = os.path.join(OUT, f"{name}-{lang}.png")
    widget.grab().save(path)
    print("saved", path)


def message(parent, icon, title, text, buttons):
    from app.ui.main_window import make_box
    box = make_box(parent, icon, title, text, buttons)
    box.show()
    return box


def main():
    if not os.path.exists(os.path.join(HOME, "index.db")):
        sys.exit("run tools/screenshots.py first")
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    from app import claude_connect
    from app.config import load_config, save_config
    from app.deps import suggest_repos
    from app.i18n import set_language, tr
    from app.ui import styles
    from app.ui.main_window import AddRepoDialog, DepsDialog, KnowledgeDialog, MainWindow

    fake_cfg = os.path.join(HOME, "claude", "claude_desktop_config.json")
    claude_connect.desktop_config_paths = lambda: [fake_cfg]
    claude_connect.install(fake_cfg)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    family = styles.load_fonts()
    app.setFont(QFont(family, 13))
    app.setStyleSheet(styles.stylesheet(family))
    os.makedirs(OUT, exist_ok=True)

    base = load_config()
    found, unknown = suggest_repos(load_config_missing(), base.odoo_version)

    for lang in ("th", "en"):
        cfg = load_config()
        cfg.language = lang
        save_config(cfg)
        set_language(lang)
        win = MainWindow()
        win.resize(1120, 720)
        win.show()
        pump(app)

        # 1. add a repository
        dlg = AddRepoDialog(win, set())
        dlg.repo.setText("OCA/purchase-workflow")
        dlg.branch.setText("16.0")
        dlg.show()
        pump(app)
        save(dlg, "01-add-repo", lang)
        dlg.close()

        # 2. a real update in progress (a separate data folder with one repository)
        live = os.path.join(ROOT, "build", "guide-live")
        shutil.rmtree(live, ignore_errors=True)
        os.makedirs(live)
        with open(os.path.join(live, "config.json"), "w") as fh:
            json.dump({"sources": [{"repo": "OCA/server-ux", "branch": "16.0"}], "language": lang}, fh)
        os.environ["REPO_BRAIN_HOME"] = live
        w2 = MainWindow()
        w2.resize(1120, 720)
        w2.show()
        pump(app)
        w2._update_clicked()
        deadline = time.time() + 60
        while time.time() < deadline and "files" not in w2.status.text() and "ไฟล์" not in w2.status.text():
            pump(app, 2)
            time.sleep(0.05)
        save(w2, "02-updating", lang)
        w2.worker.wait(120000)
        pump(app)
        w2.close()
        os.environ["REPO_BRAIN_HOME"] = HOME

        # 3. dependency repositories found on PyPI
        deps = DepsDialog(win, found, unknown, base.odoo_version, {s.repo for s in base.sources})
        deps.show()
        pump(app)
        save(deps, "03-deps", lang)
        deps.close()

        # 4. team knowledge: private GitHub repository
        win.tabs.setCurrentIndex(1)
        for b in win.kn_group.buttons():
            b.blockSignals(True)
            b.setChecked(b.property("mode") == "github")
            b.blockSignals(False)
        win.kn_repo.setText("your-team/team-knowledge")
        win.gh_box.setVisible(True)
        win.folder_box.setVisible(False)
        pump(app)
        save(win, "04-knowledge-github", lang)

        # 5. add a note by hand
        note = KnowledgeDialog(win)
        if lang == "th":
            note.title.setText("ยกเลิกใบสั่งซื้อที่อนุมัติแล้ว")
            note.tags.setText("purchase, ยกเลิก")
            note.content.setPlainText("## สรุป\nยกเลิกได้ แต่ต้องยกเลิกใบรับของก่อน\n\n## วิธีทำ\n"
                                      "1. เปิดใบรับของที่ผูกกับใบสั่งซื้อ แล้วกด Cancel\n2. กลับมาที่ใบสั่งซื้อ แล้วกด Cancel")
        else:
            note.title.setText("Cancel an approved purchase order")
            note.tags.setText("purchase, cancel")
            note.content.setPlainText("## Summary\nPossible, but cancel the receipt first.\n\n## Steps\n"
                                      "1. Open the receipt linked to the PO and press Cancel\n2. Go back to the PO and press Cancel")
        note.show()
        pump(app)
        save(note, "05-add-note", lang)
        note.close()

        # 6. settings: team file import / export
        win.tabs.setCurrentIndex(win.settings_index)
        pump(app)
        save(win, "06-settings", lang)
        box = message(win, QMessageBox.Question, tr("team_export"), tr("team_ask_token"),
                      QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        pump(app)
        save(box, "07-export-token", lang)
        box.close()
        repos = "\n".join(f"  • {s.repo} ({s.branch})" for s in base.sources)
        summary = tr("team_summary", repos=repos, knowledge="GitHub: your-team/team-knowledge",
                     odoo=base.odoo_version, token=tr("team_has_token"))
        box = message(win, QMessageBox.Question, tr("team_import"), summary, QMessageBox.Yes | QMessageBox.No)
        pump(app)
        save(box, "08-import-summary", lang)
        box.close()

        # 7. connect to Claude Desktop
        win.tabs.setCurrentIndex(3)
        pump(app)
        save(win, "09-claude", lang)
        box = message(win, QMessageBox.Information, "Repo Brain",
                      tr("cl_done", path="~/Library/Application Support/Claude/claude_desktop_config.json"),
                      QMessageBox.Ok)
        pump(app)
        save(box, "10-connected", lang)
        box.close()

        # 8. teach: LINE case loaded and copied
        win.tabs.setCurrentIndex(2)
        with open(os.path.join(ROOT, "tools", "demo_line_chat.txt"), encoding="utf-8") as fh:
            win._load_chat(fh.read())
        win._copy_case()
        pump(app)
        save(win, "11-teach-copied", lang)
        win.close()


def load_config_missing():
    from app.config import index_path
    from app.store import Store
    st = Store(index_path())
    try:
        return st.missing_depends()
    finally:
        st.close()


if __name__ == "__main__":
    main()
