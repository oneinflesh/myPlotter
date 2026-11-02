from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from myplotter.plot.estimate import format_duration
from myplotter.svg.render import PreviewPaths


class DrawingPreview(QWidget):
    interaction_started = Signal()
    transform_requested = Signal(str, float, float)
    interaction_finished = Signal()

    def __init__(self):
        super().__init__()
        self.drawing = None
        self.paths = None
        self.completed = 0
        self.head = None
        self.pen_down = False
        self.start_ready = False
        self.estimated_seconds = None
        self.editable = True
        self.drag_mode = None
        self.drag_start = None
        self.setMinimumHeight(320)

    def set_drawing(self, drawing):
        self.drawing = drawing
        self.paths = PreviewPaths(drawing)
        self.completed = 0
        self.head = None
        self.update()

    def set_start_ready(self, ready):
        self.start_ready = ready
        if not ready:
            self.head = None
        self.update()

    def set_completed(self, count):
        if self.paths is not None:
            self.paths.set_completed(count)
            self.completed = self.paths.completed
        self.update()

    def set_estimate(self, seconds):
        self.estimated_seconds = seconds
        self.update()

    def set_editable(self, editable):
        self.editable = editable
        self.drag_mode = None
        self.update()

    def _page_rect(self):
        bounds = self.rect().adjusted(28, 28, -28, -28)
        width = max(self.drawing.width_mm, 1)
        height = max(self.drawing.height_mm, 1)
        scale = min(bounds.width() / width, bounds.height() / height)
        left = bounds.center().x() - self.drawing.width_mm * scale / 2
        top = bounds.center().y() - self.drawing.height_mm * scale / 2
        return QRectF(left, top, self.drawing.width_mm * scale,
                      self.drawing.height_mm * scale), scale

    def _art_rect(self, page, scale):
        bounds = self.paths.bounds
        return QRectF(page.left() + bounds.left() * scale,
                      page.top() + bounds.top() * scale,
                      bounds.width() * scale, bounds.height() * scale)

    def mousePressEvent(self, event):
        if not self.editable or self.drawing is None or event.button() != Qt.MouseButton.LeftButton:
            return
        page, scale = self._page_rect()
        art = self._art_rect(page, scale)
        handle = QRectF(art.right() - 12, art.bottom() - 12, 24, 24)
        if handle.contains(event.position()):
            self.drag_mode = "resize"
        elif art.adjusted(-6, -6, 6, 6).contains(event.position()):
            self.drag_mode = "move"
        else:
            return
        self.drag_start = event.position()
        self.interaction_started.emit()

    def mouseMoveEvent(self, event):
        if self.drag_mode is None or self.drawing is None:
            return
        _, scale = self._page_rect()
        delta = event.position() - self.drag_start
        self.transform_requested.emit(self.drag_mode, delta.x() / scale,
                                      delta.y() / scale)

    def mouseReleaseEvent(self, event):
        if self.drag_mode is not None:
            self.drag_mode = None
            self.interaction_finished.emit()

    def leaveEvent(self, event):
        if self.drag_mode is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

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

        page, scale = self._page_rect()
        left, top = page.left(), page.top()
        painter.fillRect(page, QColor("#ffffff"))
        painter.setPen(QPen(QColor("#b8c1cc"), 1))
        painter.drawRect(page)

        def screen(point):
            return QPointF(left + point[0] * scale, top + point[1] * scale)

        for layer in self.paths.images(self.size(), left, top, scale):
            painter.drawImage(0, 0, layer)

        if self.editable:
            art = self._art_rect(page, scale)
            painter.setPen(QPen(QColor("#3973a5"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(art)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#3973a5"))
            painter.drawRect(QRectF(art.right() - 6, art.bottom() - 6, 12, 12))

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

        percent = round(100 * self.completed / self.paths.total)
        estimate = (f"  |  Estimated time: {format_duration(self.estimated_seconds)}"
                    if self.estimated_seconds is not None else "")
        painter.setPen(QColor("#152238"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(self.rect().adjusted(16, 8, -16, -8),
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                         f"{percent}% complete{estimate}")
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(self.rect().adjusted(16, 8, -16, -8),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                         "Blue cross: page start  |  Red dot: pen down  |  Orange dot: pen up"
                         if self.start_ready else "Set the current pen position as page start before plotting")
