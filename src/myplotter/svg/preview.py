from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class DrawingPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.drawing = None
        self.completed = 0
        self.setMinimumHeight(320)

    def set_drawing(self, drawing):
        self.drawing = drawing
        self.completed = 0
        self.update()

    def set_completed(self, count):
        self.completed = count
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        if self.drawing is None:
            painter.setPen(QColor("#777777"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Choose an SVG to preview")
            return
        bounds = self.rect().adjusted(20, 20, -20, -20)
        width = max(self.drawing.width_mm, 1)
        height = max(self.drawing.height_mm, 1)
        scale = min(bounds.width() / width, bounds.height() / height)
        left = bounds.center().x() - self.drawing.width_mm * scale / 2
        top = bounds.center().y() - self.drawing.height_mm * scale / 2
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#dddddd"), 1))
        painter.drawRect(QRectF(left - 5, top - 5,
                                self.drawing.width_mm * scale + 10,
                                self.drawing.height_mm * scale + 10))
        index = 0
        for path in self.drawing.paths:
            for start, end in zip(path, path[1:]):
                color = "#168449" if index < self.completed else "#333b48"
                painter.setPen(QPen(QColor(color), 2, Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap))
                painter.drawLine(left + start[0] * scale, top + start[1] * scale,
                                 left + end[0] * scale, top + end[1] * scale)
                index += 1
