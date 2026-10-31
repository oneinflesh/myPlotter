import math
import threading
import time
from collections import deque

from PySide6.QtCore import QObject, Signal, Slot

from myplotter.pen.control import set_pen


class ReturnJob(QObject):
    position_changed = Signal(float, float, bool)
    finished = Signal(bool, str)

    def __init__(self, board, origin_steps, steps_per_mm, speed_mm_s, geometry):
        super().__init__()
        self.board = board
        self.origin_steps = origin_steps
        self.steps_per_mm = steps_per_mm
        self.speed_mm_s = speed_mm_s
        self.geometry = geometry
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    @Slot()
    def run(self):
        success = False
        message = "Stopped"
        try:
            set_pen(self.board, True)
            self.board.wait_idle(self.stop_event.is_set)
            current = self.board.query_steps()
            delta = (self.origin_steps[0] - current[0],
                     self.origin_steps[1] - current[1])
            distance = self._distance(*delta)
            pieces = max(1, math.ceil(distance / 5))
            previous = (0, 0)
            pending = deque()
            for index in range(1, pieces + 1):
                if self.stop_event.is_set():
                    break
                target = (round(delta[0] * index / pieces),
                          round(delta[1] * index / pieces))
                first = target[0] - previous[0]
                second = target[1] - previous[1]
                previous = target
                if first == 0 and second == 0:
                    continue
                duration = max(10, math.ceil(1000 * self._distance(first, second)
                                             / self.speed_mm_s))
                if max(abs(first), abs(second)) / duration > 25:
                    raise ValueError("Return move exceeds board step rate")
                while len(pending) >= 2 and not self.stop_event.is_set():
                    self._drain(pending)
                if self.stop_event.is_set():
                    break
                self.board.command(f"SM,{duration},{first},{second}")
                pending.append(target)
            while pending and not self.stop_event.is_set():
                self._drain(pending)
            if self.stop_event.is_set():
                self.board.stop_motion()
            if not self.stop_event.is_set():
                self.board.wait_idle()
                if self.board.query_steps() != self.origin_steps:
                    raise RuntimeError("Return did not reach the saved start point")
                self.position_changed.emit(0.0, 0.0, False)
                success = True
                message = "Back at start"
        except Exception as error:
            message = str(error)
        finally:
            self.finished.emit(success, message)

    def _drain(self, pending):
        active, queued = self.board.motion_status()
        while len(pending) > int(active) + int(queued):
            pending.popleft()
        self._emit_position()
        if pending:
            time.sleep(0.004)

    def _distance(self, motor_1, motor_2):
        if self.geometry == "mixed":
            x = (motor_1 + motor_2) / (2 * self.steps_per_mm)
            y = (motor_1 - motor_2) / (2 * self.steps_per_mm)
        else:
            x = motor_1 / self.steps_per_mm
            y = motor_2 / self.steps_per_mm
        return math.hypot(x, y)

    def _emit_position(self):
        current = self.board.query_steps()
        first = current[0] - self.origin_steps[0]
        second = current[1] - self.origin_steps[1]
        if self.geometry == "mixed":
            x = (first + second) / (2 * self.steps_per_mm)
            y = (first - second) / (2 * self.steps_per_mm)
        else:
            x = first / self.steps_per_mm
            y = second / self.steps_per_mm
        self.position_changed.emit(x, y, False)
