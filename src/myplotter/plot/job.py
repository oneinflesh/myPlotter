import threading
import time
import traceback
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from myplotter.diagnostics.job_log import JobLog
from myplotter.motion.trajectory import plan_path
from myplotter.motion.stream import MotionQueue
from myplotter.pen.control import pen_command, set_pen
from myplotter.plot.plan import PreparedPlot, PreparationCancelled
from myplotter.plot.validation import validate_drawing


@dataclass(frozen=True)
class Motion:
    command: str
    position: tuple[float, float]
    pen_down: bool
    progress: int = 0


class PlotJob(QObject):
    progress = Signal(int)
    position_changed = Signal(float, float, bool)
    paused = Signal(bool)
    prepared = Signal()
    finished = Signal(bool, str)

    def __init__(self, board, drawing, steps_per_mm, speed_mm_s, geometry,
                 origin_steps, source_filename=None):
        super().__init__()
        self.board = board
        self.drawing = drawing
        self.steps_per_mm = steps_per_mm
        self.speed_mm_s = speed_mm_s
        self.geometry = geometry
        self.origin_steps = origin_steps
        self.source_filename = source_filename
        self.log = None
        self.last_steps = None
        self.pen_is_down = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.resume_event = threading.Event()
        self.resume_event.set()

    def stop(self):
        if self.log:
            self.log.event("stop_requested")
        self.stop_event.set()
        self.resume_event.set()

    def pause(self):
        if self.log:
            self.log.event("pause_requested")
        self.pause_event.set()
        self.resume_event.clear()

    def resume(self):
        if self.log:
            self.log.event("resume_requested")
        self.pause_event.clear()
        self.resume_event.set()

    @Slot()
    def run(self):
        completed = 0
        if self.source_filename is not None:
            self.log = JobLog(self.source_filename, "plot")
        queue = MotionQueue(self.board, self.log)
        exhausted = False
        success = False
        message = "Stopped"
        last_progress_update = 0.0
        last_visual_update = 0.0
        plan = None
        try:
            if self.log:
                self.log.event("job_started", source=self.source_filename,
                               paths=len(self.drawing.paths), segments=self.drawing.segments,
                               origin_steps=self.origin_steps, geometry=self.geometry,
                               speed_mm_s=self.speed_mm_s, steps_per_mm=self.steps_per_mm,
                               port=getattr(getattr(self.board, "port", None), "port", None))
                self.log.event("preparation_started")
            plan = PreparedPlot(self._motions(), self.stop_event.is_set)
            plan.prepare()
            if self.log:
                self.log.event("preparation_finished", motion_count=plan.count)
            motions = iter(plan)
            self.prepared.emit()
            self.position_changed.emit(0.0, 0.0, False)
            while not self.stop_event.is_set():
                completed_motions = queue.poll()
                for motion in completed_motions:
                    self.pen_is_down = motion.pen_down
                    completed += motion.progress
                now = time.monotonic()
                if completed_motions and now - last_visual_update >= 0.05:
                    motion = completed_motions[-1]
                    self.position_changed.emit(*motion.position, self.pen_is_down)
                    last_visual_update = now
                if now - last_progress_update >= 0.05:
                    self.progress.emit(completed)
                    if self.log and completed_motions:
                        self.log.event("progress", completed=completed,
                                       total=self.drawing.segments)
                    last_progress_update = now

                if self.pause_event.is_set() and not queue:
                    if not self._wait_while_paused():
                        break

                while (not exhausted and not self.pause_event.is_set()
                       and not self.stop_event.is_set() and len(queue) < 2):
                    try:
                        motion = next(motions)
                    except StopIteration:
                        exhausted = True
                        break
                    queue.submit(motion, motion.command)

                queue.refresh_position(self._emit_actual_position)

                if exhausted and not queue:
                    final_steps = self.board.query_steps()
                    self.last_steps = final_steps
                    if final_steps != self.origin_steps:
                        raise RuntimeError("Plot did not return to the saved start position")
                    self.progress.emit(completed)
                    success = True
                    message = "Complete"
                    break
                queue.wait()
        except PreparationCancelled:
            message = "Stopped"
            if self.log:
                self.log.event("preparation_cancelled")
        except Exception as error:
            message = str(error)
            if self.log:
                self.log.event("job_error", message=message, traceback=traceback.format_exc())
        finally:
            if plan is not None:
                try:
                    plan.close()
                except OSError:
                    pass
            if not success and self.board.connected:
                try:
                    self.board.stop_motion()
                except Exception:
                    pass
            if self.board.connected:
                try:
                    set_pen(self.board, True)
                    self.board.wait_idle()
                    self.pen_is_down = False
                    self._emit_actual_position()
                except Exception:
                    pass
            if self.log:
                self.log.event("job_finished", success=success, message=message,
                               last_steps=self.last_steps, progress=completed)
                self.log.close()
            self.finished.emit(success, message)

    def _wait_while_paused(self):
        was_down = self.pen_is_down
        if was_down:
            set_pen(self.board, True)
            self.board.wait_idle(self.stop_event.is_set)
            self.pen_is_down = False
            self._emit_actual_position()
        self.paused.emit(True)
        if self.log:
            self.log.event("paused", position_steps=self.last_steps)
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
        if self.log:
            self.log.event("resumed", position_steps=self.last_steps)
        return not self.stop_event.is_set()

    def _motions(self):
        validate_drawing(self.drawing)
        position = (0.0, 0.0)
        yield Motion(pen_command(True), position, False)
        for path in self.drawing.paths:
            yield from self._move([position, path[0]], False)
            position = path[0]
            yield Motion(pen_command(False), position, True)
            completed = 0
            for motion in self._move(path, True):
                completed += motion.progress
                yield motion
            position = path[-1]
            yield Motion(pen_command(True), position, False,
                         len(path) - 1 - completed)
        yield from self._move([position, (0.0, 0.0)], False)

    def _move(self, points, pen_down):
        for move in plan_path(points, self.steps_per_mm, self.speed_mm_s):
            yield Motion(move.command(self.geometry), move.position,
                         pen_down, move.progress if pen_down else 0)

    def _emit_actual_position(self):
        motor_1, motor_2 = self.board.query_steps()
        self.last_steps = (motor_1, motor_2)
        first = motor_1 - self.origin_steps[0]
        second = motor_2 - self.origin_steps[1]
        if self.geometry == "mixed":
            x = (first + second) / (2 * self.steps_per_mm)
            y = (first - second) / (2 * self.steps_per_mm)
        else:
            x = first / self.steps_per_mm
            y = second / self.steps_per_mm
        self.position_changed.emit(x, y, self.pen_is_down)
        if self.log:
            self.log.event("position", steps=self.last_steps, x_mm=x, y_mm=y,
                           pen_down=self.pen_is_down)
