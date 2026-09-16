from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


class ImageView(QGraphicsView):
    changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._syncing = False
        self.peer = None
        self.horizontalScrollBar().valueChanged.connect(self.sync)
        self.verticalScrollBar().valueChanged.connect(self.sync)

    def display(self, image):
        self.scene().clear()
        self.scene().addPixmap(QPixmap.fromImage(image))
        self.setSceneRect(self.scene().itemsBoundingRect())

    def wheelEvent(self, event):
        scale = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        proposed = self.transform().m11() * scale
        if 0.03 <= proposed <= 30:
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
        from PySide6.QtCore import Qt

        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.sync()

    def actual(self):
        self.resetTransform()
        self.sync()
