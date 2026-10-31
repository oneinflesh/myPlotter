import math

from PySide6.QtCore import QObject, QTimer, Signal

from myplotter.machine.profile import JOG_SPEED_MM_S, STEPS_PER_MM


class JogControl(QObject):
    failed = Signal(str)
    moved = Signal()

    def __init__(self, board, geometry):
        super().__init__()
        self.board = board
        self.geometry = geometry
        self.direction = (0.0, 0.0)
        self.remainder = (0.0, 0.0)
        self.enabled = False
        self.timer = QTimer(self)
        self.timer.setInterval(45)
        self.timer.timeout.connect(self._tick)

    def set_direction(self, x, y):
        self.direction = (x, y)
        if (x or y) and not self.timer.isActive():
            self.timer.start()
            self._tick()
        elif not (x or y):
            self.timer.stop()

    def stop(self):
        self.direction = (0.0, 0.0)
        self.timer.stop()

    def _tick(self):
        if not self.board.connected or not any(self.direction):
            self.stop()
            return
        try:
            active, queued = self.board.motion_status()
            if active and queued:
                return
            if not self.enabled:
                self.board.command("EM,1,1")
                self.enabled = True
            x, y = self.direction
            magnitude = math.hypot(x, y)
            speed = JOG_SPEED_MM_S * min(magnitude, 1)
            duration = 80
            step_distance = speed * duration / 1000 * STEPS_PER_MM
            exact_x = self.remainder[0] + x / magnitude * step_distance
            exact_y = self.remainder[1] + y / magnitude * step_distance
            dx, dy = round(exact_x), round(exact_y)
            self.remainder = (exact_x - dx, exact_y - dy)
            if dx or dy:
                command = (f"XM,{duration},{dx},{dy}"
                           if self.geometry() == "mixed" else
                           f"SM,{duration},{dx},{dy}")
                self.board.command(command)
                self.moved.emit()
        except Exception as error:
            self.stop()
            self.failed.emit(str(error))
