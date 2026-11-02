import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class QueuedMotion:
    value: object
    deadline: float


class MotionQueue:
    def __init__(self, board, log=None):
        self.board = board
        self.log = log
        self.pending = deque()
        self.last_position_update = 0.0

    def __len__(self):
        return len(self.pending)

    def submit(self, value, command):
        if len(self.pending) >= 2:
            raise RuntimeError("Board motion queue is full")
        fields = command.split(",")
        duration = int(fields[2] if fields[0] == "SP" else fields[1]) / 1000
        started = time.monotonic()
        end = max(started, self.pending[-1].deadline if self.pending else started) + duration
        self.board.command(command)
        self.pending.append(QueuedMotion(value, end))
        if self.log:
            self.log.event("command_sent", command=command, queue_depth=len(self.pending),
                           duration_ms=round(duration * 1000),
                           acknowledgement_ms=round((time.monotonic() - started) * 1000, 2),
                           target=getattr(value, "position", None),
                           pen_down=getattr(value, "pen_down", None))

    def poll(self):
        active, queued = self.board.motion_status()
        count = int(active) + int(queued)
        if count > len(self.pending):
            raise RuntimeError("Board motion queue changed unexpectedly")
        completed = []
        while len(self.pending) > count:
            completed.append(self.pending.popleft().value)
        if completed and self.log:
            self.log.event("commands_completed", count=len(completed), queue_depth=count,
                           active=bool(active), queued=bool(queued))
        return completed

    def refresh_position(self, callback):
        now = time.monotonic()
        budget = self.pending[-1].deadline - now if self.pending else float("inf")
        if now - self.last_position_update >= 0.1 and budget >= 0.06:
            callback()
            self.last_position_update = time.monotonic()

    def wait(self):
        if self.pending:
            budget = self.pending[-1].deadline - time.monotonic()
            # A short Windows sleep can last a scheduler tick. Yield only when
            # the queue is close to empty; serial reads already pace polling.
            time.sleep(0.002 if budget > 0.06 else 0)
