import math
import threading
import time
from collections import deque

from PySide6.QtCore import QObject, Signal, Slot

from myplotter.motion.trajectory import plan_path
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
            resolution = self.steps_per_mm * (math.sqrt(2) if self.geometry == "mixed" else 1)
            points = [tuple(value / resolution for value in position)
                      for position in (current, self.origin_steps)]
            pending = deque()
            for move in plan_path(points, resolution, self.speed_mm_s):
                if self.stop_event.is_set():
                    break
                while len(pending) >= 2 and not self.stop_event.is_set():
                    self._drain(pending)
                if self.stop_event.is_set():
                    break
                self.board.command(move.command("cartesian"))
                pending.append(move.position)
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
