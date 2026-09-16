import json
import sys
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from llm_change_tool.core.projects import Project, backup_project, create_project, open_project

STYLE = """
QMainWindow { background: #f4f6fa; }
QWidget { color: #1d293d; font-size: 14px; }
QFrame#sidebar { background: #15243a; border-radius: 12px; }
QFrame#sidebar QLabel { color: #dce6f4; background: transparent; }
QLabel#brand { font-size: 23px; font-weight: 700; color: white; }
QLabel#title { font-size: 28px; font-weight: 700; }
QLabel#muted { color: #58677d; }
QLabel#badge { color: #087f73; font-weight: 700; }
QFrame#card { background: white; border: 1px solid #dbe2ec; border-radius: 12px; }
QPushButton { background: white; border: 1px solid #bac6d5; border-radius: 7px;
              padding: 10px 16px; }
QPushButton:hover { background: #e9f0fb; }
QPushButton:disabled { color: #8a97a8; background: #edf0f5; border-color: #dbe2ec; }
QPushButton#primary { color: white; background: #2563eb; border: none; }
QPushButton#primary:hover { background: #1d4ed8; }
"""


def label(text: str, name: str = "") -> QLabel:
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    result.setObjectName(name)
    return result


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project: Project | None = None
        self.process: QProcess | None = None
        self.worker_timed_out = False
        self.worker_timer = QTimer(self)
        self.worker_timer.setSingleShot(True)
        self.worker_timer.timeout.connect(self._worker_timeout)
        self.setWindowTitle("LLM Change Tool v2 · Phase 0")
        self.resize(1060, 740)
        self.setMinimumSize(880, 660)
        self.setStyleSheet(STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(24)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 28, 22, 28)
        side.addWidget(label("LLM Change\nTool v2", "brand"))
        side.addWidget(label("항공영상 변화탐지\n학습데이터 검수"))
        side.addSpacing(36)
        side.addWidget(label("●  프로젝트"))
        side.addSpacing(20)
        side.addWidget(
            label("다음 단계\n\n데이터 가져오기\n자동판정 · 비교\n사람 검수\n최종 데이터 내보내기")
        )
        side.addStretch()
        side.addWidget(label("LOCAL FIRST\n내 PC에 저장되는 작업 공간"))
        layout.addWidget(sidebar)

        main = QVBoxLayout()
        main.setSpacing(16)
        main.addWidget(label("PHASE 0  ·  프로젝트 기반", "badge"))
        main.addWidget(label("작업 공간을 준비하세요", "title"))
        main.addWidget(label("프로젝트를 만들거나 이전 작업 폴더를 열어 시작합니다.", "muted"))
        actions = QHBoxLayout()
        self.new_button = QPushButton("새 프로젝트")
        self.new_button.setObjectName("primary")
        self.new_button.clicked.connect(self._new_project)
        self.open_button = QPushButton("프로젝트 열기")
        self.open_button.clicked.connect(self._open_project)
        actions.addWidget(self.new_button)
        actions.addWidget(self.open_button)
        actions.addStretch()
        main.addLayout(actions)

        card = QFrame()
        card.setObjectName("card")
        details = QVBoxLayout(card)
        details.setContentsMargins(24, 22, 24, 22)
        details.setSpacing(14)
        self.project_name = label("열린 프로젝트 없음", "title")
        self.project_details = label("새 프로젝트를 만들면 로컬 작업 DB가 준비됩니다.", "muted")
        self.project_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.addWidget(self.project_name)
        details.addWidget(self.project_details)
        detail_actions = QHBoxLayout()
        self.diagnose_button = QPushButton("프로젝트 점검")
        self.diagnose_button.clicked.connect(self.start_diagnosis)
        self.backup_button = QPushButton("DB 백업")
        self.backup_button.clicked.connect(self._backup)
        detail_actions.addWidget(self.diagnose_button)
        detail_actions.addWidget(self.backup_button)
        detail_actions.addStretch()
        details.addLayout(detail_actions)
        self.result = label("프로젝트를 열면 점검과 백업을 사용할 수 있습니다.", "muted")
        details.addWidget(self.result)
        main.addWidget(card)

        note = QFrame()
        note.setObjectName("card")
        note_layout = QVBoxLayout(note)
        note_layout.setContentsMargins(24, 20, 24, 20)
        note_layout.addWidget(label("현재 가능한 작업", "badge"))
        note_layout.addWidget(label("프로젝트 생성 · 다시 열기 · 작업 DB 점검 · DB 백업"))
        note_layout.addSpacing(8)
        note_layout.addWidget(
            label(
                "데이터 가져오기, GPT 자동판정, 검수, JSON 내보내기는 후속 단계에서 추가됩니다. "
                "현재 앱 실행에는 API 키가 필요하지 않습니다.",
                "muted",
            )
        )
        main.addWidget(note)
        main.addStretch()
        main.addWidget(
            label(
                "원본 JSON 유지  ·  중앙 서버 없이 작업  ·  프로젝트 폴더는 로컬 디스크에", "muted"
            )
        )
        layout.addLayout(main, 1)
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self.new_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.diagnose_button.setEnabled(self.project is not None and not busy)
        self.backup_button.setEnabled(self.project is not None and not busy)

    def set_project(self, project: Project):
        self.project = project
        self.project_name.setText(project.name)
        self.project_details.setText(
            f"저장 위치  {project.root}\n프로젝트 ID  {project.project_id}\n생성 시각 (UTC)  {project.created_at}"
        )
        self.result.setText("프로젝트를 열었습니다. 점검으로 DB 상태를 확인할 수 있습니다.")
        self._set_busy(False)

    def _error(self, exc: Exception):
        QMessageBox.warning(self, "작업을 완료하지 못했습니다", str(exc))

    def _new_project(self):
        parent = QFileDialog.getExistingDirectory(self, "새 작업 폴더를 만들 로컬 위치 선택")
        if not parent:
            return
        name, ok = QInputDialog.getText(self, "새 프로젝트", "프로젝트 이름")
        if not ok:
            return
        try:
            # Human-readable project name stays in DB; folder name is portable.
            path = Path(parent) / f"llm-change-{uuid4().hex[:12]}"
            self.set_project(create_project(path, name))
        except Exception as exc:
            self._error(exc)

    def _open_project(self):
        path = QFileDialog.getExistingDirectory(self, "project.sqlite3가 있는 작업 폴더 선택")
        if path:
            try:
                self.set_project(open_project(Path(path)))
            except Exception as exc:
                self._error(exc)

    def _backup(self):
        if self.project is None:
            return
        try:
            destination = backup_project(self.project)
            self.result.setText(f"DB 백업 완료\n{destination}")
        except Exception as exc:
            self._error(exc)

    def start_diagnosis(self):
        if self.project is None or self.process is not None:
            return
        self._set_busy(True)
        self.result.setText("프로젝트 점검 중…")
        self.worker_timed_out = False
        self.process = QProcess(self)
        self.process.setProgram(sys.executable)
        self.process.setArguments(
            ["-m", "llm_change_tool.worker", "diagnose", "--project", str(self.project.root)]
        )
        self.process.finished.connect(self._worker_finished)
        self.process.errorOccurred.connect(self._worker_error)
        self.worker_timer.start(30_000)
        self.process.start()

    def _worker_timeout(self):
        if self.process:
            self.worker_timed_out = True
            self.process.kill()

    def _worker_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.result.setText("점검 프로세스를 시작할 수 없습니다. 설치 환경을 확인하세요.")
            self._cleanup_worker()

    def _worker_finished(self, exit_code, exit_status):
        if self.process is None:
            return
        try:
            if self.worker_timed_out:
                raise ValueError("점검 제한시간을 초과했습니다. 다시 시도하세요.")
            raw = bytes(self.process.readAllStandardOutput()).decode("utf-8")
            message = json.loads(raw)
            if exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
                raise ValueError(message.get("message", "프로젝트 점검에 실패했습니다."))
            if message.get("type") != "completed":
                raise ValueError("잘못된 점검 응답입니다.")
            self.result.setText(
                f"점검 완료 · DB 정상 · 스키마 v{message['result']['schema_version']}"
            )
        except (ValueError, KeyError, TypeError) as exc:
            self.result.setText(f"점검 실패: {exc}")
        finally:
            self._cleanup_worker()

    def _cleanup_worker(self):
        self.worker_timer.stop()
        if self.process:
            self.process.deleteLater()
        self.process = None
        self._set_busy(False)

    def closeEvent(self, event: QCloseEvent):
        if self.process is not None:
            # The Phase 0 diagnostic is read-only; stopping cannot lose edits.
            self.process.kill()
            self.process.waitForFinished(1000)
        event.accept()
