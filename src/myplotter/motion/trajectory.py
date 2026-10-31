import math
from dataclasses import dataclass, replace

from myplotter.machine.profile import ACCELERATION_MM_S2, PLOT_SPEED_MM_S


JUNCTION_TOLERANCE_MM = 0.005
MIN_COMMAND_SECONDS = 0.02
SLICE_SECONDS = 0.03


@dataclass(frozen=True)
class Move:
    duration_ms: int
    delta_steps: tuple[int, int]
    position: tuple[float, float]
    progress: int = 0

    def command(self, geometry):
        dx, dy = self.delta_steps
        motors = (dx + dy, dx - dy) if geometry == "mixed" else (dx, dy)
        if any(abs(value) / self.duration_ms > 25 for value in motors):
            raise ValueError("Move exceeds the board step rate")
        name = "XM" if geometry == "mixed" else "SM"
        return f"{name},{self.duration_ms},{dx},{dy}"


def plan_path(points, steps_per_mm, speed_mm_s):
    """Keep the path coordinates while limiting speed changes at its vertices."""
    if steps_per_mm <= 0 or speed_mm_s <= 0:
        raise ValueError("Steps per mm and speed must be positive")
    speed_mm_s = min(speed_mm_s, PLOT_SPEED_MM_S)
    vertices = [tuple(round(value * steps_per_mm) for value in point)
                for point in points]
    segments = []
    skipped = 0
    for start, end in zip(vertices, vertices[1:]):
        skipped += 1
        if start == end:
            continue
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy) / steps_per_mm
        segments.append((start, end, length, skipped))
        skipped = 0
    if not segments:
        return
    if skipped:
        start, end, length, count = segments[-1]
        segments[-1] = (start, end, length, count + skipped)

    caps = [min(speed_mm_s, segment[2] / MIN_COMMAND_SECONDS)
            for segment in segments]
    speeds = [0.0] * (len(segments) + 1)
    for index in range(1, len(segments)):
        before, after = segments[index - 1], segments[index]
        first = (before[1][0] - before[0][0], before[1][1] - before[0][1])
        second = (after[1][0] - after[0][0], after[1][1] - after[0][1])
        cosine = max(-1.0, min(1.0, (first[0] * second[0] + first[1] * second[1])
                              / (math.hypot(*first) * math.hypot(*second))))
        half_angle = math.sqrt((1 + cosine) / 2)
        corner_speed = (float("inf") if half_angle > 1 - 1e-9 else
                        math.sqrt(ACCELERATION_MM_S2 * JUNCTION_TOLERANCE_MM
                                  * half_angle / (1 - half_angle)))
        speeds[index] = min(caps[index - 1], caps[index], corner_speed)

    # Look ahead in both directions so short lines have room to brake.
    for index, segment in enumerate(segments):
        speeds[index + 1] = min(speeds[index + 1],
                                math.sqrt(speeds[index] ** 2
                                          + 2 * ACCELERATION_MM_S2 * segment[2]))
    for index in range(len(segments) - 1, -1, -1):
        speeds[index] = min(speeds[index],
                            math.sqrt(speeds[index + 1] ** 2
                                      + 2 * ACCELERATION_MM_S2 * segments[index][2]))

    for index, (start, end, length, count) in enumerate(segments):
        moves = list(_segment_moves(start, end, length, steps_per_mm,
                                    caps[index], speeds[index], speeds[index + 1]))
        moves[-1] = replace(moves[-1], progress=count)
        yield from moves


def _segment_moves(start, end, length, steps_per_mm, maximum, entry, exit_speed):
    acceleration = ACCELERATION_MM_S2
    peak = min(maximum, math.sqrt(acceleration * length
                                  + (entry ** 2 + exit_speed ** 2) / 2))
    accelerate_distance = max(0.0, (peak ** 2 - entry ** 2) / (2 * acceleration))
    decelerate_distance = max(0.0, (peak ** 2 - exit_speed ** 2) / (2 * acceleration))
    cruise_distance = max(0.0, length - accelerate_distance - decelerate_distance)
    accelerate_time = (peak - entry) / acceleration
    cruise_time = cruise_distance / peak
    decelerate_time = (peak - exit_speed) / acceleration
    duration = accelerate_time + cruise_time + decelerate_time
    slices = max(1, math.ceil(duration / SLICE_SECONDS))
    previous = start
    previous_time_ms = 0
    moves = []
    for index in range(1, slices + 1):
        elapsed = duration * index / slices
        if elapsed < accelerate_time:
            distance = entry * elapsed + acceleration * elapsed ** 2 / 2
        elif elapsed < accelerate_time + cruise_time:
            distance = accelerate_distance + peak * (elapsed - accelerate_time)
        else:
            time_left = max(0.0, duration - elapsed)
            distance = length - exit_speed * time_left - acceleration * time_left ** 2 / 2
        fraction = min(1.0, max(0.0, distance / length))
        target = (end if index == slices else
                  tuple(round(a + (b - a) * fraction) for a, b in zip(start, end)))
        time_ms = round(elapsed * 1000)
        if target == previous:
            continue
        delta = (target[0] - previous[0], target[1] - previous[1])
        minimum_ms = math.ceil(1000 * math.hypot(*delta) / (steps_per_mm * maximum))
        moves.append(Move(max(round(MIN_COMMAND_SECONDS * 1000), minimum_ms,
                              time_ms - previous_time_ms), delta,
                          (target[0] / steps_per_mm, target[1] / steps_per_mm)))
        previous, previous_time_ms = target, time_ms
    trailing_ms = round(duration * 1000) - previous_time_ms
    if trailing_ms:
        moves[-1] = replace(moves[-1], duration_ms=moves[-1].duration_ms + trailing_ms)
    yield from moves
