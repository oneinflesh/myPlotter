import math
import threading
import time

from PySide6.QtCore import QObject, Signal, Slot

from myplotter.pen.control import set_pen


class PlotJob(QObject):
    progress = Signal(int)
    position_changed = Signal(float, float, bool)
    paused = Signal(bool)
    finished = Signal(bool, str)

    def __init__(self, board, drawing, steps_per_mm, speed_mm_s, geometry,
                 origin_steps):
        super().__init__()
        self.board = board
        self.drawing = drawing
        self.steps_per_mm = steps_per_mm
        self.speed_mm_s = speed_mm_s
        self.geometry = geometry
        self.origin_steps = origin_steps
        self.pen_is_down = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.resume_event = threading.Event()
        self.resume_event.set()

    def stop(self):
        self.stop_event.set()
        self.resume_event.set()

    def pause(self):
        self.pause_event.set()
        self.resume_event.clear()

    def resume(self):
        self.pause_event.clear()
        self.resume_event.set()

    def _checkpoint(self):
        if self.stop_event.is_set():
            return False
        if not self.pause_event.is_set():
            return True
        was_down = self.pen_is_down
        if was_down:
            set_pen(self.board, True)
            self.board.wait_idle(self.stop_event.is_set)
            self.pen_is_down = False
            self._emit_actual_position()
        self.paused.emit(True)
        while self.pause_event.is_set() and not self.stop_event.is_set():
            self.resume_event.wait(0.05)
        if self.stop_event.is_set():
            return False
        if was_down:
            set_pen(self.board, False)
            self.board.wait_idle(self.stop_event.is_set)
            self.pen_is_down = True
            self._emit_actual_position()
        self.paused.emit(False)
        return not self.stop_event.is_set()

    @Slot()
    def run(self):
        completed = 0
        position = (0, 0)
        pen_down = False
        last_update = 0.0
        success = False
        message = "Stopped"
        try:
            self.position_changed.emit(0.0, 0.0, False)
            set_pen(self.board, True)
            self.board.wait_idle(self.stop_event.is_set)
            for path in self.drawing.paths:
                if not self._checkpoint():
                    break
                position = self._move(position, path[0])
                if not self._checkpoint():
                    break
                set_pen(self.board, False)
                pen_down = True
                self.pen_is_down = True
                self.position_changed.emit(position[0], position[1], True)
                self.board.wait_idle(self.stop_event.is_set)
                for point in path[1:]:
                    if not self._checkpoint():
                        break
                    position = self._move(position, point)
                    if self.stop_event.is_set():
                        break
                    completed += 1
                    now = time.monotonic()
                    if now - last_update >= 0.05 or completed == self.drawing.segments:
                        self.progress.emit(completed)
                        last_update = now
                if not self.stop_event.is_set():
                    set_pen(self.board, True)
                    pen_down = False
                    self.pen_is_down = False
                    self.position_changed.emit(position[0], position[1], False)
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
                    set_pen(self.board, True)
                    self.pen_is_down = False
                except Exception:
                    pass
            self.finished.emit(success, message)

    def _move(self, position, target):
        distance = math.hypot(target[0] - position[0], target[1] - position[1])
        pieces = max(1, math.ceil(distance / 5))
        origin = position
        for index in range(1, pieces + 1):
            if not self._checkpoint():
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
        self.board.wait_idle(self.stop_event.is_set, self._emit_actual_position)
        if not self.stop_event.is_set():
            self.position_changed.emit(target[0], target[1], self.pen_is_down)

    def _emit_actual_position(self):
        motor_1, motor_2 = self.board.query_steps()
        first = motor_1 - self.origin_steps[0]
        second = motor_2 - self.origin_steps[1]
        if self.geometry == "mixed":
            x = (first + second) / (2 * self.steps_per_mm)
            y = (first - second) / (2 * self.steps_per_mm)
        else:
            x = first / self.steps_per_mm
            y = second / self.steps_per_mm
        self.position_changed.emit(x, y, self.pen_is_down)
