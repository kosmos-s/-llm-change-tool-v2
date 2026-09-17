from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


class ImageView(QGraphicsView):
    changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.setObjectName("imageCanvas")
        self.placeholder = "검수 이미지를 불러오세요"
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.auto_fit = True
        self._syncing = False
        self.peer = None
        self.horizontalScrollBar().valueChanged.connect(self.sync)
        self.verticalScrollBar().valueChanged.connect(self.sync)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.scene().items():
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#b4c7d2"))
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder)
            painter.end()

    def display(self, image):
        self.scene().clear()
        self.scene().addPixmap(QPixmap.fromImage(image))
        self.setSceneRect(self.scene().itemsBoundingRect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit:
            QTimer.singleShot(0, self.fit)

    def showEvent(self, event):
        super().showEvent(event)
        if self.auto_fit:
            QTimer.singleShot(0, self.fit)

    def wheelEvent(self, event):
        scale = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        proposed = self.transform().m11() * scale
        if 0.03 <= proposed <= 30:
            self.auto_fit = False
            if self.peer:
                self.peer.auto_fit = False
            self.scale(scale, scale)
            self.sync()
        event.accept()

    def sync(self, *args):
        if self._syncing or self.peer is None:
            return
        self.peer._syncing = True
        self.peer.setTransform(self.transform())
        self.peer.centerOn(self.mapToScene(self.viewport().rect().center()))
        self.peer._syncing = False

    def fit(self):
        self.auto_fit = True
        if self.peer:
            self.peer.auto_fit = True
        if not self.scene().items():
            return
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.sync()

    def actual(self):
        self.auto_fit = False
        if self.peer:
            self.peer.auto_fit = False
        self.resetTransform()
        self.sync()
