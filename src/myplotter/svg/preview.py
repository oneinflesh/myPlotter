from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class DrawingPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.drawing = None
        self.completed = 0
        self.head = None
        self.pen_down = False
        self.start_ready = False
        self.setMinimumHeight(320)

    def set_drawing(self, drawing):
        self.drawing = drawing
        self.completed = 0
        self.head = None
        self.update()

    def set_start_ready(self, ready):
        self.start_ready = ready
        if not ready:
            self.head = None
        self.update()

    def set_completed(self, count):
        self.completed = count
        self.update()

    def set_head(self, x, y, pen_down):
        self.head = (x, y)
        self.pen_down = pen_down
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#eef2f5"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.drawing is None:
            painter.setPen(QColor("#667085"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Choose an SVG to preview")
            return

        bounds = self.rect().adjusted(28, 28, -28, -28)
        width = max(self.drawing.width_mm, 1)
        height = max(self.drawing.height_mm, 1)
        scale = min(bounds.width() / width, bounds.height() / height)
        left = bounds.center().x() - self.drawing.width_mm * scale / 2
        top = bounds.center().y() - self.drawing.height_mm * scale / 2
        page = QRectF(left, top, self.drawing.width_mm * scale,
                      self.drawing.height_mm * scale)
        painter.fillRect(page, QColor("#ffffff"))
        painter.setPen(QPen(QColor("#b8c1cc"), 1))
        painter.drawRect(page)

        def screen(point):
            return QPointF(left + point[0] * scale, top + point[1] * scale)

        painter.setPen(QPen(QColor("#aeb7c2"), 2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        for path in self.drawing.paths:
            for start, end in zip(path, path[1:]):
                painter.drawLine(screen(start), screen(end))

        painter.setPen(QPen(QColor("#09a66d"), 4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        remaining = self.completed
        for path in self.drawing.paths:
            for start, end in zip(path, path[1:]):
                if remaining <= 0:
                    break
                painter.drawLine(screen(start), screen(end))
                remaining -= 1
            if remaining <= 0:
                break

        origin = screen((0, 0))
        painter.setPen(QPen(QColor("#2563eb"), 2))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(origin, 6, 6)
        painter.drawLine(origin + QPointF(-11, 0), origin + QPointF(11, 0))
        painter.drawLine(origin + QPointF(0, -11), origin + QPointF(0, 11))

        if self.head is not None:
            head = screen(self.head)
            painter.setPen(QPen(QColor("#ffffff"), 3))
            painter.setBrush(QColor("#e5484d") if self.pen_down else QColor("#ff9f1a"))
            painter.drawEllipse(head, 9, 9)

        percent = round(100 * self.completed / self.drawing.segments)
        painter.setPen(QColor("#152238"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(self.rect().adjusted(16, 8, -16, -8),
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                         f"{percent}% complete  |  green: drawn  |  gray: remaining")
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(self.rect().adjusted(16, 8, -16, -8),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                         "Blue cross: page start  |  Red dot: pen down  |  Orange dot: pen up"
                         if self.start_ready else "Set the current pen position as page start before plotting")
