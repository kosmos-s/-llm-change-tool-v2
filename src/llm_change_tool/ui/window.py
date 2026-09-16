import json
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from llm_change_tool.core.datasets import import_dataset
from llm_change_tool.core.exporting import export_run, final_gate
from llm_change_tool.core.jobs import (
    RunConfig,
    control_job,
    create_job,
    job_info,
    recover_jobs,
    run_job,
)
from llm_change_tool.core.labels import prompt_text
from llm_change_tool.core.plans import create_plan
from llm_change_tool.core.reviews import compare_run
from llm_change_tool.storage.store import one, rows, transaction
from llm_change_tool.ui.project_window import MainWindow as ProjectWindow
from llm_change_tool.ui.reviewer import ReviewWidget
from llm_change_tool.ui.tasks import Task


class MainWindow(ProjectWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LLM Change Tool v2")
        self.resize(1440, 900)
        self.active_task = None
        self.job_id = None
        self.run_id = None
        self.pipeline_buttons = []
        project_page = self.takeCentralWidget()
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(project_page, "프로젝트")
        self.build_pipeline()
        self.review_widget = ReviewWidget()
        self.tabs.addTab(self.review_widget, "이미지 검수")
        self.build_results()
        from llm_change_tool.ui.analysis_pages import add_pages

        add_pages(self)

    def button(self, title, fn, layout):
        button = QPushButton(title)
        button.clicked.connect(fn)
        layout.addWidget(button)
        self.pipeline_buttons.append(button)
        return button

    def build_pipeline(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel("1. 데이터 가져오기 → 2. 작업 계획/AI 실행 → 3. Compare → 이미지 검수")
        )
        bar = QHBoxLayout()
        self.button("데이터 폴더 Import", self.choose_import, bar)
        self.button(
            "중단 작업 복구", lambda: self.background(lambda p: recover_jobs(self.project)), bar
        )
        layout.addLayout(bar)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("시험용 (Mock 가능)", "pilot")
        self.mode.addItem("본작업 errors 각 1,000건", "production")
        self.provider = QComboBox()
        self.provider.addItems(["mock", "openai"])
        self.model = QLineEdit("gpt-4o-mini")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("메모리에만 유지 / OPENAI_API_KEY 환경변수 지원")
        self.price_in = QDoubleSpinBox()
        self.price_out = QDoubleSpinBox()
        self.budget = QDoubleSpinBox()
        for spin in (self.price_in, self.price_out, self.budget):
            spin.setRange(0, 1000)
            spin.setDecimals(4)
        self.budget.setValue(5)
        for title, widget in [
            ("작업 계획", self.mode),
            ("AI Provider", self.provider),
            ("모델", self.model),
            ("API Key", self.key),
            ("입력 토큰 단가 USD / 1M", self.price_in),
            ("출력 토큰 단가 USD / 1M", self.price_out),
            ("Run 예상 비용 한도 USD", self.budget),
        ]:
            form.addRow(title, widget)
        self.policy = QComboBox()
        self.policy.addItem("core: 낮은 신뢰도만으로 필수 검수 제외", "core")
        self.policy.addItem("detailed: 낮은 신뢰도도 필수 검수", "detailed")
        form.addRow("Compare 정책", self.policy)
        layout.addLayout(form)
        self.prompt = QTextEdit()
        self.prompt.setPlainText(prompt_text())
        self.prompt.setMaximumHeight(150)
        layout.addWidget(QLabel("프롬프트 (Run 생성 시 내용과 SHA256 고정)"))
        layout.addWidget(self.prompt)
        self.approve_api = QCheckBox("선택한 이미지 쌍을 OpenAI로 전송하고 유료 API를 호출합니다.")
        layout.addWidget(self.approve_api)
        bar = QHBoxLayout()
        self.button("계획 고정 + Job 생성", self.new_job, bar)
        self.jobs = QComboBox()
        self.jobs.currentIndexChanged.connect(self.select_job)
        bar.addWidget(self.jobs, 1)
        self.button("Run 목록 새로고침", self.refresh_jobs, bar)
        layout.addLayout(bar)
        bar = QHBoxLayout()
        self.button("실행 / Resume", self.start_job, bar)
        self.pause = QPushButton("일시정지")
        self.pause.clicked.connect(lambda: self.control("pause"))
        bar.addWidget(self.pause)
        self.cancel = QPushButton("취소")
        self.cancel.clicked.connect(lambda: self.control("cancel"))
        bar.addWidget(self.cancel)
        self.button("실패 항목 Retry 준비", lambda: self.control("retry"), bar)
        self.button("Compare + 검수 목록", self.compare, bar)
        layout.addLayout(bar)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self.tabs.addTab(page, "데이터 · AI 작업")

    def build_results(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        bar = QHBoxLayout()
        self.button(
            "Final Gate",
            lambda: self.background(lambda p: final_gate(self.project, self.run_id)),
            bar,
        )
        self.button(
            "JSON + JPG Export",
            lambda: self.background(lambda p: export_run(self.project, self.run_id)),
            bar,
        )
        layout.addLayout(bar)
        layout.addWidget(
            QLabel(
                "시험용 Export는 manifest에 pilot로 표시됩니다. 본작업은 실제 OpenAI와 3,000건 Gate를 통과해야 합니다."
            )
        )
        self.results = QTextEdit()
        self.results.setReadOnly(True)
        layout.addWidget(self.results)
        self.tabs.addTab(page, "품질 · Export")

    def set_project(self, project):
        if hasattr(self, "review_widget") and not self.review_widget.bind(None, None):
            return
        super().set_project(project)
        if hasattr(self, "jobs"):
            self.job_id = None
            self.run_id = None
            self.refresh_jobs()

    def background(self, function, after=None):
        if not self.project:
            return self._error(ValueError("프로젝트를 먼저 여세요."))
        if self.active_task and self.active_task.isRunning():
            return
        if not self.review_widget.flush():
            return
        self.active_task = Task(function, self)
        for button in self.pipeline_buttons:
            button.setEnabled(False)
        self.tabs.setTabEnabled(2, False)
        self.new_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.jobs.setEnabled(False)
        self.active_task.progress.connect(self.show_progress)
        self.active_task.done.connect(lambda value: self.task_done(value, after))
        self.active_task.failed.connect(lambda message: self.task_done({"error": message}, None))
        self.active_task.finished.connect(self.task_finished)
        self.active_task.start()

    def show_progress(self, value):
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        self.log.setPlainText(text)

    def task_done(self, value, after):
        self.show_progress(value)
        self.results.setPlainText(json.dumps(value, ensure_ascii=False, indent=2, default=str))
        if after:
            after(value)

    def task_finished(self):
        for button in self.pipeline_buttons:
            button.setEnabled(True)
        self.tabs.setTabEnabled(2, True)
        self.new_button.setEnabled(True)
        self.open_button.setEnabled(True)
        self.jobs.setEnabled(True)

    def choose_import(self):
        path = QFileDialog.getExistingDirectory(self, "train/val/test를 포함하는 데이터 루트 선택")
        if path:
            self.background(lambda p: import_dataset(self.project, Path(path), p))

    def new_job(self):
        try:
            config = RunConfig(
                provider=self.provider.currentText(),
                model=self.model.text().strip(),
                input_price=self.price_in.value(),
                output_price=self.price_out.value(),
                cost_limit=self.budget.value(),
                review_policy=self.policy.currentData(),
            )
            mode = self.mode.currentData()
            prompt = self.prompt.toPlainText()
            self.background(
                lambda p: create_job(self.project, create_plan(self.project, mode), config, prompt),
                lambda value: self.refresh_jobs(value),
            )
        except Exception as exc:
            self._error(exc)

    def refresh_jobs(self, select=None):
        if not self.project:
            return
        with transaction(self.project) as con:
            jobs = rows(
                con,
                "SELECT j.*,r.created_at,r.config FROM jobs j JOIN llm_runs r ON r.id=j.run_id ORDER BY r.created_at DESC",
            )
        current = select or self.job_id
        self.jobs.blockSignals(True)
        self.jobs.clear()
        for job in jobs:
            config = json.loads(job["config"])
            self.jobs.addItem(f"{job['state']} · {config['provider']} · {job['id'][:8]}", job["id"])
        index = self.jobs.findData(current)
        if index >= 0:
            self.jobs.setCurrentIndex(index)
        self.jobs.blockSignals(False)
        self.select_job()

    def select_job(self, *args):
        if not self.project:
            return
        candidate = self.jobs.currentData()
        if candidate:
            with transaction(self.project) as con:
                run_id = one(con, "SELECT run_id FROM jobs WHERE id=:id", id=candidate)["run_id"]
            if not self.review_widget.bind(self.project, run_id):
                self.jobs.blockSignals(True)
                self.jobs.setCurrentIndex(self.jobs.findData(self.job_id))
                self.jobs.blockSignals(False)
                return
            self.job_id, self.run_id = candidate, run_id
            self.show_progress(job_info(self.project, self.job_id))
        else:
            self.job_id = self.run_id = None
            self.review_widget.bind(None, None)

    def start_job(self):
        if not self.job_id:
            return
        with transaction(self.project) as con:
            run = one(con, "SELECT config FROM llm_runs WHERE id=:id", id=self.run_id)
        if json.loads(run["config"])["provider"] == "openai" and not self.approve_api.isChecked():
            return self._error(ValueError("API 전송/유료 호출 체크를 확인하세요."))
        key = self.key.text().strip() or os.environ.get("OPENAI_API_KEY", "")
        self.background(lambda p: run_job(self.project, self.job_id, key, progress=p))

    def control(self, action):
        if self.job_id:
            try:
                control_job(self.project, self.job_id, action)
            except Exception as exc:
                self._error(exc)

    def compare(self):
        if self.run_id:
            self.background(
                lambda p: compare_run(self.project, self.run_id),
                lambda v: self.review_widget.bind(self.project, self.run_id),
            )

    def closeEvent(self, event):
        if self.active_task and self.active_task.isRunning():
            if self.job_id:
                self.control("pause")
            QMessageBox.information(
                self,
                "작업 정리 중",
                "작업이 안전하게 멈춘 뒤 닫아 주세요. AI 호출 중이면 현재 요청이 끝날 때까지 기다립니다.",
            )
            event.ignore()
            return
        if self.review_widget.task and self.review_widget.task.isRunning():
            event.ignore()
            return
        if not self.review_widget.flush():
            event.ignore()
            return
        super().closeEvent(event)
