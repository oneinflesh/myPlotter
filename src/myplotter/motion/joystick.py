import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Joystick(QWidget):
    direction_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.direction = (0.0, 0.0)
        self.setFixedSize(160, 160)
        self.setToolTip("Drag the handle or hold an arrow key to move the pen")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _set_direction(self, x, y):
        length = math.hypot(x, y)
        if length > 1:
            x, y = x / length, y / length
        self.direction = (x, y)
        self.direction_changed.emit(x, y)
        self.update()

    def mousePressEvent(self, event):
        self.setFocus()
        self._from_mouse(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._from_mouse(event.position())

    def mouseReleaseEvent(self, event):
        self._set_direction(0.0, 0.0)

    def keyPressEvent(self, event):
        keys = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if event.key() in keys:
            self._set_direction(*keys[event.key()])
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                           Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._set_direction(0.0, 0.0)
        else:
            super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._set_direction(0.0, 0.0)
        super().focusOutEvent(event)

    def _from_mouse(self, point):
        self._set_direction((point.x() - 80) / 58, (point.y() - 80) / 58)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#718096"), 2))
        painter.setBrush(QColor("#e7ebf0"))
        painter.drawEllipse(QPointF(80, 80), 72, 72)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#3973a5"))
        painter.drawEllipse(QPointF(80 + 48 * self.direction[0],
                                    80 + 48 * self.direction[1]), 22, 22)
