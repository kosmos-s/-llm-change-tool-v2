import json

from PIL import ImageChops
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from llm_change_tool.core.datasets import sample_images
from llm_change_tool.core.labels import FIELDS
from llm_change_tool.core.reviews import review_history, review_queue, save_review, undo_review
from llm_change_tool.ui.image_view import ImageView
from llm_change_tool.ui.tasks import Task


class ReviewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.project = None
        self.run_id = None
        self.items = []
        self.index = 0
        self.dirty = False
        self.loading = False
        self.task = None
        self.images = None
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.filter = QComboBox()
        for title, value in [
            ("전체", "all"),
            ("미검수", "unreviewed"),
            ("보류", "deferred"),
            ("필수 검수", "required"),
        ]:
            self.filter.addItem(title, value)
        self.filter.currentIndexChanged.connect(self.reload)
        top.addWidget(self.filter)
        self.reviewer = QLineEdit()
        self.reviewer.setPlaceholderText("검수자 이름 (필수)")
        top.addWidget(self.reviewer)
        self.auto = QCheckBox("자동 임시 저장")
        self.auto.setChecked(True)
        top.addWidget(self.auto)
        self.progress = QLabel("Compare 후 검수 목록이 표시됩니다.")
        top.addWidget(self.progress, 1)
        layout.addLayout(top)
        self.identity = QLabel()
        self.identity.setWordWrap(True)
        layout.addWidget(self.identity)
        splitter = QSplitter()
        viewer = QWidget()
        vl = QVBoxLayout(viewer)
        titles = QHBoxLayout()
        titles.addWidget(QLabel("T1 · 과거"))
        titles.addWidget(QLabel("T2 · 현재"))
        vl.addLayout(titles)
        pair = QHBoxLayout()
        self.left = ImageView()
        self.right = ImageView()
        self.left.peer = self.right
        self.right.peer = self.left
        pair.addWidget(self.left)
        pair.addWidget(self.right)
        vl.addLayout(pair)
        controls = QHBoxLayout()
        for name, fn in [("화면 맞춤", self.left.fit), ("100%", self.left.actual)]:
            button = QPushButton(name)
            button.clicked.connect(fn)
            controls.addWidget(button)
        self.diff = QCheckBox("차이 영상")
        self.diff.toggled.connect(self.show_images)
        controls.addWidget(self.diff)
        self.flicker = QCheckBox("깜박임")
        self.flicker.toggled.connect(self.toggle_flicker)
        controls.addWidget(self.flicker)
        vl.addLayout(controls)
        splitter.addWidget(viewer)
        panel = QWidget()
        pl = QVBoxLayout(panel)
        self.labels = QTableWidget(len(FIELDS), 4)
        self.labels.setHorizontalHeaderLabels(["라벨", "원본", "AI", "최종"])
        self.boxes = {}
        for i, f in enumerate(FIELDS):
            self.labels.setItem(i, 0, QTableWidgetItem(f["title"]))
            box = QCheckBox()
            box.setEnabled("fixed" not in f)
            box.toggled.connect(self.changed)
            self.labels.setCellWidget(i, 3, box)
            self.boxes[f["key"]] = box
        self.labels.setColumnWidth(0, 155)
        for i in (1, 2, 3):
            self.labels.setColumnWidth(i, 45)
        self.labels.setMinimumWidth(340)
        self.labels.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pl.addWidget(self.labels)
        self.ai_reason = QLabel()
        self.ai_reason.setWordWrap(True)
        pl.addWidget(self.ai_reason)
        self.reason = QTextEdit()
        self.reason.setPlaceholderText("검수 근거")
        self.reason.setMaximumHeight(90)
        self.reason.textChanged.connect(self.changed)
        pl.addWidget(self.reason)
        history = QPushButton("검수 이력")
        history.clicked.connect(self.history)
        pl.addWidget(history)
        splitter.addWidget(panel)
        splitter.setSizes([850, 360])
        layout.addWidget(splitter, 1)
        nav = QHBoxLayout()
        self.buttons = []
        for title, fn in [
            ("이전", lambda: self.move(-1)),
            ("다음", lambda: self.move(1)),
            ("보류", lambda: self.save("DEFERRED", True)),
            ("저장", lambda: self.save()),
            ("저장 후 다음", lambda: self.save("DONE", True)),
            ("Undo", self.undo),
        ]:
            button = QPushButton(title)
            button.clicked.connect(fn)
            nav.addWidget(button)
            self.buttons.append(button)
        layout.addLayout(nav)
        self.status = QLabel("")
        layout.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(1200)
        self.timer.timeout.connect(self.autosave)
        self.flash = QTimer(self)
        self.flash.setInterval(500)
        self.flash.timeout.connect(self.flash_frame)
        self.flash_index = 0
        for key, fn in [
            ("Ctrl+S", lambda: self.save()),
            ("Ctrl+Return", lambda: self.save("DONE", True)),
            ("Alt+Left", lambda: self.move(-1)),
            ("Alt+Right", lambda: self.move(1)),
            ("Ctrl+Z", self.undo),
            ("F", self.left.fit),
        ]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(fn)

    def bind(self, project, run_id):
        if self.task and self.task.isRunning():
            return
        self.project = project
        self.run_id = run_id
        self.reload()

    def flush(self):
        if self.dirty:
            return self.save("DRAFT")
        return True

    def reload(self, *args):
        if not self.project or not self.run_id or not self.flush():
            return
        if self.task and self.task.isRunning():
            return
        self.items = review_queue(self.project, self.run_id, self.filter.currentData())
        self.index = min(self.index, max(0, len(self.items) - 1))
        self.load_current()

    def changed(self, *args):
        if self.loading:
            return
        self.dirty = True
        if self.auto.isChecked():
            self.timer.start()

    def autosave(self):
        if self.dirty and self.reviewer.text().strip():
            self.save("DRAFT")

    def load_current(self):
        self.timer.stop()
        self.flash.stop()
        self.flicker.setChecked(False)
        self.loading = True
        for button in self.buttons:
            button.setEnabled(bool(self.items))
        if not self.items:
            self.identity.setText("해당 조건의 검수 항목이 없습니다.")
            self.progress.setText("0 / 0")
            self.loading = False
            self.dirty = False
            return
        sample = self.items[self.index]
        self.identity.setText(sample["logical_key"])
        self.progress.setText(
            f"{self.index + 1} / {len(self.items)} · {sample['review_state'] or '미검수'}"
        )
        original = json.loads(sample["original_labels"])
        prediction = json.loads(sample["prediction"]) if sample["prediction"] else None
        final = json.loads(sample["reviewed_labels"]) if sample["reviewed_labels"] else original
        for i, f in enumerate(FIELDS):
            self.labels.setItem(i, 1, QTableWidgetItem(str(original[f["key"]])))
            self.labels.setItem(
                i, 2, QTableWidgetItem(str(prediction["labels"][f["key"]]) if prediction else "—")
            )
            self.boxes[f["key"]].setChecked(bool(f.get("fixed", final[f["key"]])))
        self.reason.setPlainText(sample["reviewed_reason"] or "")
        self.ai_reason.setText(
            f"AI 신뢰도 {prediction['confidence']:.2f}\n{prediction['reason']}"
            if prediction
            else "AI 결과 없음"
        )
        self.status.setText("신호: " + sample["signals"])
        self.dirty = False
        self.loading = False
        self.setEnabled(False)

        def load(progress):
            left, right = sample_images(self.project, sample)
            diff = ImageChops.difference(left, right)
            return [(im.tobytes(), im.width, im.height) for im in (left, right, diff)]

        self.task = Task(load, self)
        self.task.done.connect(self.images_loaded)
        self.task.failed.connect(lambda message: self.status.setText("이미지 오류: " + message))
        self.task.finished.connect(lambda: self.setEnabled(True))
        self.task.start()

    def images_loaded(self, frames):
        self.images = [
            QImage(data, w, h, w * 3, QImage.Format.Format_RGB888).copy() for data, w, h in frames
        ]
        self.show_images()
        self.left.fit()

    def show_images(self, *args):
        if self.images:
            self.left.display(self.images[0])
            self.right.display(self.images[2 if self.diff.isChecked() else 1])

    def toggle_flicker(self, enabled):
        if enabled:
            self.flash.start()
        else:
            self.flash.stop()
            self.show_images()

    def flash_frame(self):
        if self.images:
            self.flash_index = 1 - self.flash_index
            self.right.display(self.images[self.flash_index])

    def move(self, offset):
        if self.items and self.flush():
            self.index = max(0, min(len(self.items) - 1, self.index + offset))
            self.load_current()

    def save(self, state="DONE", advance=False):
        if not self.items or self.loading:
            return False
        sample = self.items[self.index]
        labels = {k: int(box.isChecked()) for k, box in self.boxes.items()}
        for f in FIELDS:
            if f.get("parent") and labels[f["key"]]:
                labels[f["parent"]] = 1
        try:
            revision = save_review(
                self.project,
                self.run_id,
                sample["id"],
                labels,
                self.reason.toPlainText(),
                self.reviewer.text(),
                state,
                sample["revision"],
            )
            sample.update(
                revision=revision,
                reviewed_labels=json.dumps(labels),
                reviewed_reason=self.reason.toPlainText(),
                review_state=state,
            )
            self.dirty = False
            self.timer.stop()
            self.status.setText(f"{state} 저장 완료 · revision {revision}")
            if advance:
                self.move(1)
            return True
        except Exception as exc:
            self.status.setText(str(exc))
            return False

    def undo(self):
        if not self.items:
            return
        try:
            sample = self.items[self.index]
            undo_review(self.project, self.run_id, sample["id"], self.reviewer.text())
            self.dirty = False
            self.reload()
        except Exception as exc:
            self.status.setText(str(exc))

    def history(self):
        if self.items:
            history = review_history(self.project, self.run_id, self.items[self.index]["id"])
            QMessageBox.information(
                self,
                "검수 이력",
                "\n\n".join(
                    f"r{r['revision']} · {r['state']} · {r['reviewer']} · {r['created_at']}\n{r['reason']}"
                    for r in history
                )
                or "검수 이력 없음",
            )
