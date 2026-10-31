import math

from svgelements import Arc, Close, CubicBezier, Line, QuadraticBezier


CURVE_TOLERANCE_MM = 0.005
MAX_CURVE_SEGMENTS = 10000


def flatten_segment(segment, tolerance):
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("SVG curve has an invalid accuracy limit")
    if isinstance(segment, (Line, Close)):
        yield point(segment.end)
    elif isinstance(segment, CubicBezier):
        yield from _bezier(tuple(point(p) for p in
                                 (segment.start, segment.control1,
                                  segment.control2, segment.end)), tolerance)
    elif isinstance(segment, QuadraticBezier):
        yield from _bezier(tuple(point(p) for p in
                                 (segment.start, segment.control, segment.end)), tolerance)
    elif isinstance(segment, Arc):
        # The second derivative bounds the chord error for an elliptical arc.
        radius_bound = (math.dist(point(segment.center), point(segment.prx))
                        + math.dist(point(segment.center), point(segment.pry)))
        samples = max(1, math.ceil(abs(segment.sweep)
                                  * math.sqrt(radius_bound / (8 * tolerance))))
        if samples > MAX_CURVE_SEGMENTS:
            raise ValueError("SVG curve is too complex")
        for index in range(1, samples + 1):
            yield point(segment.point(index / samples))
    else:
        raise ValueError(f"Unsupported SVG segment: {type(segment).__name__}")


def point(value):
    result = (float(value.x), float(value.y))
    if not all(math.isfinite(number) for number in result):
        raise ValueError("SVG contains invalid coordinates")
    return result


def _bezier(controls, tolerance):
    stack = [(controls, 0)]
    emitted = 0
    while stack:
        points, depth = stack.pop()
        if all(_distance_squared(p, points[0], points[-1]) <= tolerance ** 2
               for p in points[1:-1]):
            emitted += 1
            if emitted > MAX_CURVE_SEGMENTS:
                raise ValueError("SVG curve is too complex")
            yield points[-1]
            continue
        if depth >= 24:
            raise ValueError("SVG curve cannot meet the accuracy limit")
        left, right = [points[0]], [points[-1]]
        level = points
        while len(level) > 1:
            level = tuple(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                          for a, b in zip(level, level[1:]))
            left.append(level[0])
            right.append(level[-1])
        stack.append((tuple(reversed(right)), depth + 1))
        stack.append((tuple(left), depth + 1))


def _distance_squared(p, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    fraction = (max(0.0, min(1.0, ((p[0] - start[0]) * dx
                                  + (p[1] - start[1]) * dy) / length_squared))
                if length_squared else 0.0)
    return (p[0] - start[0] - fraction * dx) ** 2 + (p[1] - start[1] - fraction * dy) ** 2
