"""Frozen GUI startup + QProcess diagnostic contract without a desktop session."""

import tempfile
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from llm_change_tool.core.projects import create_project
from llm_change_tool.ui.window import MainWindow


def gui_smoke():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="llm-change-gui-smoke-") as temporary:
        window = MainWindow()
        window.set_project(create_project(Path(temporary) / "project", "GUI smoke"))
        window.show()
        window.start_diagnosis()
        loop = QEventLoop()
        timer = QTimer()
        timeout = QTimer()
        timer.timeout.connect(lambda: loop.quit() if window.process is None else None)
        timer.start(20)
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(15000)
        loop.exec()
        timer.stop()
        timeout.stop()
        passed = window.process is None and "점검 완료" in window.result.text()
        window.close()
        app.processEvents()
        if not passed:
            raise RuntimeError("Frozen GUI/worker diagnostic failed")
        return {"passed": True, "gui": True, "worker": True}
