import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from llm_change_tool.core.exporting import final_gate
from llm_change_tool.core.projects import create_project
from llm_change_tool.ui.window import MainWindow


def until(predicate, timeout=15000):
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    deadline = QTimer()
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    poll.start(5)
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    deadline.start(timeout)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert predicate(), "UI operation timed out"


def test_main_window_pipeline_and_review(imported, tmp_path):
    app = QApplication.instance() or QApplication([])
    project, _ = imported
    window = MainWindow()
    window.show()
    window.set_project(project)
    window.new_job()
    until(lambda: not window.active_task.isRunning())
    app.processEvents()
    assert window.job_id
    window.start_job()
    until(lambda: not window.active_task.isRunning())
    app.processEvents()
    window.compare()
    until(lambda: not window.active_task.isRunning())
    reviewer = window.review_widget
    until(lambda: reviewer.task is not None and not reviewer.task.isRunning())
    app.processEvents()
    assert len(reviewer.items) == 6
    reviewer.reviewer.setText("GUI tester")
    for i in range(6):
        reviewer.reason.setPlainText("GUI confirmed")
        assert reviewer.save()
        if i < 5:
            reviewer.move(1)
            until(lambda: not reviewer.task.isRunning())
            app.processEvents()
    assert final_gate(project, window.run_id)["passed"]
    reviewer.left.actual()
    reviewer.left.scale(2, 2)
    reviewer.left.sync()
    assert reviewer.right.transform().m11() == reviewer.left.transform().m11()
    # Switching project must clear prior review context.
    window.set_project(create_project(tmp_path / "second", "second"))
    assert not reviewer.items and reviewer.project is None
    window.close()
    app.processEvents()
