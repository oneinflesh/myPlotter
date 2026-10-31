import math
import threading
import time

from PySide6.QtCore import QObject, Signal, Slot


class PlotJob(QObject):
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, board, drawing, steps_per_mm, speed_mm_s, geometry):
        super().__init__()
        self.board = board
        self.drawing = drawing
        self.steps_per_mm = steps_per_mm
        self.speed_mm_s = speed_mm_s
        self.geometry = geometry
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    @Slot()
    def run(self):
        completed = 0
        position = (0, 0)
        pen_down = False
        last_update = 0.0
        success = False
        message = "Stopped"
        try:
            self.board.command("SP,1,500")
            self.board.wait_idle(self.stop_event.is_set)
            for path in self.drawing.paths:
                if self.stop_event.is_set():
                    break
                position = self._move(position, path[0])
                self.board.command("SP,0,500")
                pen_down = True
                self.board.wait_idle(self.stop_event.is_set)
                for point in path[1:]:
                    if self.stop_event.is_set():
                        break
                    position = self._move(position, point)
                    if self.stop_event.is_set():
                        break
                    completed += 1
                    now = time.monotonic()
                    if now - last_update >= 0.05 or completed == self.drawing.segments:
                        self.progress.emit(completed)
                        last_update = now
                self.board.command("SP,1,500")
                pen_down = False
                self.board.wait_idle(self.stop_event.is_set)
            if not self.stop_event.is_set():
                position = self._move(position, (0, 0))
            self.progress.emit(completed)
            success = not self.stop_event.is_set()
            message = "Complete" if success else "Stopped"
        except Exception as error:
            message = str(error)
        finally:
            if pen_down and self.board.connected:
                try:
                    self.board.command("SP,1,500")
                except Exception:
                    pass
            self.finished.emit(success, message)

    def _move(self, position, target):
        distance = math.hypot(target[0] - position[0], target[1] - position[1])
        pieces = max(1, math.ceil(distance / 5))
        origin = position
        for index in range(1, pieces + 1):
            if self.stop_event.is_set():
                break
            fraction = index / pieces
            next_point = (origin[0] + (target[0] - origin[0]) * fraction,
                          origin[1] + (target[1] - origin[1]) * fraction)
            self._move_piece(position, next_point)
            position = next_point
        return position

    def _move_piece(self, position, target):
        old = tuple(round(value * self.steps_per_mm) for value in position)
        new = tuple(round(value * self.steps_per_mm) for value in target)
        dx, dy = new[0] - old[0], new[1] - old[1]
        if dx == 0 and dy == 0:
            return
        distance = math.hypot(target[0] - position[0], target[1] - position[1])
        duration = max(10, math.ceil(1000 * distance / self.speed_mm_s))
        if self.geometry == "mixed":
            motor_steps = (dx + dy, dx - dy)
            command = f"XM,{duration},{dx},{dy}"
        else:
            motor_steps = (dx, dy)
            command = f"SM,{duration},{dx},{dy}"
        if any(abs(value) / duration > 25 for value in motor_steps):
            raise ValueError("Move exceeds board step rate; lower the speed")
        self.board.command(command)
        self.board.wait_idle(self.stop_event.is_set)
