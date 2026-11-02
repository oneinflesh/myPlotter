from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen


class PreviewPaths:
    def __init__(self, drawing):
        self.drawing = drawing
        self.total = drawing.segments
        self.full = QPainterPath()
        for path in drawing.paths:
            self.full.moveTo(*path[0])
            for point in path[1:]:
                self.full.lineTo(*point)
        self.bounds = self.full.boundingRect()
        self.image_key = None
        self.full_image = None
        self.drawn_image = None
        self._reset_progress()

    def _reset_progress(self):
        self.drawn = QPainterPath()
        self.delta = QPainterPath()
        self.reset_image = True
        self.completed = 0
        self.segments = ((index == 0, start, end) for path in self.drawing.paths
                         for index, (start, end) in enumerate(zip(path, path[1:])))

    def set_completed(self, count):
        count = max(0, min(count, self.total))
        if count < self.completed:
            self._reset_progress()
        while self.completed < count:
            new_path, start, end = next(self.segments)
            if new_path:
                self.drawn.moveTo(*start)
            if new_path or self.delta.isEmpty():
                self.delta.moveTo(*start)
            self.drawn.lineTo(*end)
            self.delta.lineTo(*end)
            self.completed += 1

    def images(self, size, left, top, scale):
        key = (size.width(), size.height(), left, top, scale)
        if self.image_key != key:
            self.full_image = self._blank(size)
            self._paint(self.full_image, self.full, left, top, scale, "#aeb7c2", 2)
            self.drawn_image = self._blank(size)
            self._paint(self.drawn_image, self.drawn, left, top, scale, "#09a66d", 4)
            self.image_key = key
        elif self.reset_image:
            self.drawn_image = self._blank(size)
            self._paint(self.drawn_image, self.drawn, left, top, scale, "#09a66d", 4)
        elif not self.delta.isEmpty():
            self._paint(self.drawn_image, self.delta, left, top, scale, "#09a66d", 4)
        self.delta = QPainterPath()
        self.reset_image = False
        return self.full_image, self.drawn_image

    @staticmethod
    def _blank(size):
        image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        return image

    @staticmethod
    def _paint(image, path, left, top, scale, color, width):
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(left, top)
        painter.scale(scale, scale)
        pen = QPen(QColor(color), width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()
