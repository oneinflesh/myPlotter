import math
import threading
import time
from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from myplotter.pen.control import pen_command, set_pen


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

                now = time.monotonic()
                if now - last_position_update >= 0.05:
                    self._emit_actual_position()
                    last_position_update = now

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

                if exhausted and not pending:
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
        position = (0.0, 0.0)
        deferred_progress = 0
        yield Motion(pen_command(True), position, False)
        for path in self.drawing.paths:
            yield from self._move(position, path[0], False)
            position = path[0]
            yield Motion(pen_command(False), position, True)
            for point in path[1:]:
                pieces = list(self._move(position, point, True))
                if pieces:
                    pieces[-1] = Motion(pieces[-1].command, pieces[-1].position,
                                        True, deferred_progress + 1)
                    deferred_progress = 0
                    yield from pieces
                else:
                    deferred_progress += 1
                position = point
            yield Motion(pen_command(True), position, False,
                         deferred_progress)
            deferred_progress = 0
        yield from self._move(position, (0.0, 0.0), False)

    def _move(self, position, target, pen_down):
        distance = math.hypot(target[0] - position[0], target[1] - position[1])
        pieces = max(1, math.ceil(distance / 5))
        origin = position
        for index in range(1, pieces + 1):
            fraction = index / pieces
            next_point = (origin[0] + (target[0] - origin[0]) * fraction,
                          origin[1] + (target[1] - origin[1]) * fraction)
            old = tuple(round(value * self.steps_per_mm) for value in position)
            new = tuple(round(value * self.steps_per_mm) for value in next_point)
            dx, dy = new[0] - old[0], new[1] - old[1]
            if dx or dy:
                duration = max(10, math.ceil(1000 * math.hypot(
                    next_point[0] - position[0], next_point[1] - position[1])
                    / self.speed_mm_s))
                motor_steps = ((dx + dy, dx - dy) if self.geometry == "mixed"
                               else (dx, dy))
                if any(abs(value) / duration > 25 for value in motor_steps):
                    raise ValueError("Move exceeds board step rate; lower the speed")
                command = (f"XM,{duration},{dx},{dy}" if self.geometry == "mixed"
                           else f"SM,{duration},{dx},{dy}")
                yield Motion(command, next_point, pen_down)
            position = next_point

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
