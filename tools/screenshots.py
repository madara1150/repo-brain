"""Take README screenshots from the real app (Thai and English UI) -> docs/screenshots/*-th.png / *-en.png.

Uses a throw-away data folder (build/screenshot-home) with public OCA repositories and the sample
notes in tools/demo_knowledge, runs a real update from GitHub, then grabs each tab.
Run:  QT_QPA_PLATFORM=offscreen .venv/bin/python tools/screenshots.py   (or without offscreen on a desktop)
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(ROOT, "build", "screenshot-home")
OUT = os.path.join(ROOT, "docs", "screenshots")
sys.path.insert(0, ROOT)
os.environ["REPO_BRAIN_HOME"] = HOME


def prepare():
    if os.path.isdir(HOME) and os.path.exists(os.path.join(HOME, "index.db")) and "--fresh" not in sys.argv:
        return
    shutil.rmtree(HOME, ignore_errors=True)
    os.makedirs(HOME)
    kn = os.path.join(HOME, "team-notes")
    shutil.copytree(os.path.join(ROOT, "tools", "demo_knowledge"), kn)
    shutil.copytree(os.path.join(ROOT, "tools", "demo_questions"), os.path.join(kn, "questions"))
    cfg = {"sources": [{"repo": "OCA/purchase-workflow", "branch": "16.0"},
                       {"repo": "OCA/l10n-thailand", "branch": "16.0"},
                       {"repo": "OCA/server-ux", "branch": "16.0"}],
           "knowledge": {"mode": "folder", "folder": kn, "subdir": "knowledge"},
           "odoo_version": "16.0", "author": "demo"}
    with open(os.path.join(HOME, "config.json"), "w") as fh:
        json.dump(cfg, fh)
    from app.config import index_path, load_config
    from app.store import Store
    from app.sync import Syncer
    store = Store(index_path())
    for r in Syncer(load_config(), store, progress=lambda m, f=None: None).run():
        print(r)
    store.close()


def main():
    prepare()
    from PySide6.QtWidgets import QApplication
    from app import claude_connect
    from app.config import load_config, save_config
    from app.ui import styles
    from app.ui.main_window import MainWindow
    MainWindow.check_updates = lambda self, quiet=False: None  # the real check result is set below

    # show the connected state without touching this computer's real Claude config
    fake_cfg = os.path.join(HOME, "claude", "claude_desktop_config.json")
    claude_connect.desktop_config_paths = lambda: [fake_cfg]
    claude_connect.install(fake_cfg)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    family = styles.load_fonts()
    from PySide6.QtGui import QFont
    app.setFont(QFont(family, 13))
    app.setStyleSheet(styles.stylesheet(family))
    os.makedirs(OUT, exist_ok=True)
    from app.config import index_path
    from app.store import Store
    from app.sync import check_updates
    checks = check_updates(load_config(), Store(index_path()))  # real "Check for changes" result
    for lang in ("th", "en"):
        cfg = load_config()
        cfg.language = lang
        save_config(cfg)
        win = MainWindow()
        win.resize(1120, 720)
        win.checks = {c.repo: c for c in checks}
        win.refresh()
        win.show()
        for idx, name in ((0, "main"), (1, "knowledge"), (2, "questions"), (3, "teach"), (4, "claude"), (5, "settings")):
            win.tabs.setCurrentIndex(idx)
            if idx == 1:
                win.kn_list.setCurrentRow(1)
            if idx == 2:
                win.q_filter.setCurrentIndex(2)
                win.q_list.setCurrentRow(0)
            if idx == 3:
                with open(os.path.join(ROOT, "tools", "demo_line_chat.txt"), encoding="utf-8") as fh:
                    win._load_chat(fh.read())
                win.flow_topic.setText("ขอซื้อ-จัดซื้อ" if lang == "th" else "Purchase request to PO")
            for _ in range(5):
                app.processEvents()
            path = os.path.join(OUT, f"{name}-{lang}.png")
            win.grab().save(path)
            print("saved", path)
        win.close()


if __name__ == "__main__":
    main()
