import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM Change Tool v2")
    parser.add_argument("--project", type=Path, help="기존 프로젝트 폴더")
    args = parser.parse_args(argv)
    from PySide6.QtWidgets import QApplication, QMessageBox

    from llm_change_tool.core.projects import open_project
    from llm_change_tool.ui.window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("LLM Change Tool v2")
    app.setOrganizationName("LLM Change Tool")
    window = MainWindow()
    if args.project:
        try:
            window.set_project(open_project(args.project))
        except Exception as exc:
            QMessageBox.warning(window, "프로젝트를 열 수 없습니다", str(exc))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
