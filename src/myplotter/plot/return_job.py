import math
import threading
import traceback

from PySide6.QtCore import QObject, Signal, Slot

from myplotter.diagnostics.job_log import JobLog
from myplotter.motion.trajectory import plan_path
from myplotter.motion.stream import MotionQueue
from myplotter.pen.control import set_pen


class ReturnJob(QObject):
    position_changed = Signal(float, float, bool)
    finished = Signal(bool, str)

    def __init__(self, board, origin_steps, steps_per_mm, speed_mm_s, geometry,
                 source_filename=None):
        super().__init__()
        self.board = board
        self.origin_steps = origin_steps
        self.steps_per_mm = steps_per_mm
        self.speed_mm_s = speed_mm_s
        self.geometry = geometry
        self.source_filename = source_filename
        self.log = None
        self.last_steps = None
        self.stop_event = threading.Event()

    def stop(self):
        if self.log:
            self.log.event("stop_requested")
        self.stop_event.set()

    @Slot()
    def run(self):
        success = False
        message = "Stopped"
        try:
            if self.source_filename is not None:
                self.log = JobLog(self.source_filename, "return")
                self.log.event("job_started", source=self.source_filename,
                               origin_steps=self.origin_steps, geometry=self.geometry,
                               speed_mm_s=self.speed_mm_s, steps_per_mm=self.steps_per_mm,
                               port=getattr(getattr(self.board, "port", None), "port", None))
            set_pen(self.board, True)
            self.board.wait_idle(self.stop_event.is_set)
            current = self.board.query_steps()
            self.last_steps = current
            if self.log:
                self.log.event("initial_position", steps=current)
            resolution = self.steps_per_mm * (math.sqrt(2) if self.geometry == "mixed" else 1)
            points = [tuple(value / resolution for value in position)
                      for position in (current, self.origin_steps)]
            moves = list(plan_path(points, resolution, self.speed_mm_s))
            if self.log:
                self.log.event("preparation_finished", motion_count=len(moves))
            queue = MotionQueue(self.board, self.log)
            for move in moves:
                if self.stop_event.is_set():
                    break
                while len(queue) >= 2 and not self.stop_event.is_set():
                    self._drain(queue, feeding=True)
                if self.stop_event.is_set():
                    break
                queue.submit(move, move.command("cartesian"))
            while queue and not self.stop_event.is_set():
                self._drain(queue)
            if self.stop_event.is_set():
                self.board.stop_motion()
            if not self.stop_event.is_set():
                self.board.wait_idle()
                final_steps = self.board.query_steps()
                self.last_steps = final_steps
                if final_steps != self.origin_steps:
                    raise RuntimeError("Return did not reach the saved start point")
                self.position_changed.emit(0.0, 0.0, False)
                success = True
                message = "Back at start"
        except Exception as error:
            message = str(error)
            if self.log:
                self.log.event("job_error", message=message, traceback=traceback.format_exc())
        finally:
            if not success and self.board.connected:
                try:
                    self.board.stop_motion()
                except Exception:
                    pass
            if self.log:
                self.log.event("job_finished", success=success, message=message,
                               last_steps=self.last_steps)
                self.log.close()
            self.finished.emit(success, message)

    def _drain(self, queue, feeding=False):
        queue.poll()
        if feeding and len(queue) < 2:
            return
        queue.refresh_position(self._emit_position)
        queue.wait()

    def _emit_position(self):
        current = self.board.query_steps()
        self.last_steps = current
        first = current[0] - self.origin_steps[0]
        second = current[1] - self.origin_steps[1]
        if self.geometry == "mixed":
            x = (first + second) / (2 * self.steps_per_mm)
            y = (first - second) / (2 * self.steps_per_mm)
        else:
            x = first / self.steps_per_mm
            y = second / self.steps_per_mm
        self.position_changed.emit(x, y, False)
        if self.log:
            self.log.event("position", steps=current, x_mm=x, y_mm=y, pen_down=False)
