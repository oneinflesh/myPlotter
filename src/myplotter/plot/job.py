import threading
import time
from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from myplotter.motion.trajectory import plan_path
from myplotter.pen.control import pen_command, set_pen
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

    @Slot()
    def run(self):
        completed = 0
        pending = deque()
        motions = iter(self._motions())
        exhausted = False
        success = False
        message = "Stopped"
        last_position_update = 0.0
        try:
            self.position_changed.emit(0.0, 0.0, False)
            while not self.stop_event.is_set():
                active, queued = self.board.motion_status()
                in_board = int(active) + int(queued)
                if in_board > len(pending):
                    raise RuntimeError("Board motion queue changed unexpectedly")
                while len(pending) > in_board:
                    motion = pending.popleft()
                    self.pen_is_down = motion.pen_down
                    completed += motion.progress
                    if motion.progress:
                        self.progress.emit(completed)
                    self.position_changed.emit(*motion.position, self.pen_is_down)

                if self.pause_event.is_set() and not pending:
                    if not self._wait_while_paused():
                        break

                while (not exhausted and not self.pause_event.is_set()
                       and not self.stop_event.is_set() and len(pending) < 2):
                    try:
                        motion = next(motions)
                    except StopIteration:
                        exhausted = True
                        break
                    self.board.command(motion.command)
                    pending.append(motion)

                now = time.monotonic()
                if now - last_position_update >= 0.05:
                    self._emit_actual_position()
                    last_position_update = now

                if exhausted and not pending:
                    if self.board.query_steps() != self.origin_steps:
                        raise RuntimeError("Plot did not return to the saved start position")
                    self.progress.emit(completed)
                    success = True
                    message = "Complete"
                    break
                if pending:
                    time.sleep(0.004)
        except Exception as error:
            message = str(error)
        finally:
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
            self.finished.emit(success, message)

    def _wait_while_paused(self):
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
        first = motor_1 - self.origin_steps[0]
        second = motor_2 - self.origin_steps[1]
        if self.geometry == "mixed":
            x = (first + second) / (2 * self.steps_per_mm)
            y = (first - second) / (2 * self.steps_per_mm)
        else:
            x = first / self.steps_per_mm
            y = second / self.steps_per_mm
        self.position_changed.emit(x, y, self.pen_is_down)
