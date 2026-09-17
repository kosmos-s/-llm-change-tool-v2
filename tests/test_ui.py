import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from llm_change_tool.core.projects import create_project  # noqa: E402
from llm_change_tool.ui.window import MainWindow  # noqa: E402


def test_window_and_real_worker_lifecycle(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    assert not window.diagnose_button.isEnabled()
    window.set_project(create_project(tmp_path / "한글 project", "테스트 프로젝트"))
    assert window.diagnose_button.isEnabled()
    window.start_diagnosis()
    assert not window.new_button.isEnabled()
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if window.process is None else None)
    poll.start(10)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(10_000)
    loop.exec()
    poll.stop()
    timeout.stop()
    try:
        assert window.process is None
        assert "점검 완료" in window.result.text()
        assert window.new_button.isEnabled()
        window._backup()
        poll.timeout.disconnect()
        poll.timeout.connect(lambda: loop.quit() if not window.active_task.isRunning() else None)
        poll.start(10)
        timeout.start(10000)
        loop.exec()
        poll.stop()
        timeout.stop()
        assert not window.active_task.isRunning()
        assert "DB 백업 완료" in window.result.text()
    finally:
        window.close()
        app.processEvents()
