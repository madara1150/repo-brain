"""UI smoke tests (offscreen): window builds in both languages, actions update config."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("REPO_BRAIN_HOME", str(tmp_path / "home"))
    from PySide6.QtWidgets import QApplication
    from app import claude_connect
    monkeypatch.setattr(claude_connect, "desktop_config_paths",
                        lambda: [str(tmp_path / "Claude" / "claude_desktop_config.json")])
    app = QApplication.instance() or QApplication([])
    from app.ui.main_window import MainWindow
    w = MainWindow()
    yield w
    w.close()
    app.processEvents()


def test_builds_and_switches_language(win):
    from app.config import load_config
    assert win.tabs.count() == 5
    assert win.update_btn.text() == "อัปเดตข้อมูล"
    win.lang.setCurrentIndex(1)
    assert win.update_btn.text() == "Update" and load_config().language == "en"


def test_knowledge_mode_saves(win):
    from app.config import load_config
    for b in win.kn_group.buttons():
        if b.property("mode") == "github":
            b.setChecked(True)
    win.kn_repo.setText("https://github.com/me/team-notes")
    win._knowledge_changed()
    k = load_config().knowledge
    assert k.mode == "github" and k.repo == "me/team-notes"
    assert not win.gh_box.isHidden() and win.folder_box.isHidden()


def test_connect_claude(win, tmp_path):
    from app import claude_connect
    (tmp_path / "Claude").mkdir()
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    win._connect_claude()
    assert claude_connect.status() == "connected"
    assert "เชื่อมแล้ว" in win.cl_state.text()


def test_import_team_file(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from app.config import Config, Knowledge, Source, export_team, load_config
    path = tmp_path / "team.repobrain"
    export_team(Config(sources=[Source("me/erp", "16.0")], knowledge=Knowledge(mode="github", repo="me/notes"),
                       github_token="tok"), str(path))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    win._import_team(str(path))
    cfg = load_config()
    assert cfg.sources[0].repo == "me/erp" and cfg.knowledge.repo == "me/notes" and cfg.github_token == "tok"
    assert win.table.rowCount() == 1 and win.tabs.currentIndex() == win.settings_index  # asks for the name next


def test_teach_tab_loads_line_cases(win):
    import os
    from PySide6.QtGui import QGuiApplication
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "tools", "demo_line_chat.txt"), encoding="utf-8") as fh:
        win._load_chat(fh.read())
    assert win.case_list.count() == 3
    assert "สมชาย" not in win.case_text.toPlainText()
    win.case_text.setPlainText(win.case_text.toPlainText() + "\nโทร 0899999999")
    win._copy_case()
    clip = QGuiApplication.clipboard().text()
    assert "add_knowledge" in clip and "0899999999" not in clip
    win._mark_done()
    assert win.case_list.currentRow() == 1 and win.case_list.item(0).text().startswith("✓")
    assert len(win._load_done()) == 1
