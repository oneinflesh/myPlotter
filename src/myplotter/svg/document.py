import math
from dataclasses import dataclass

from svgelements import Close, Line, Move, Path, SVG, Shape


Point = tuple[float, float]


@dataclass(frozen=True)
class Drawing:
    paths: list[list[Point]]
    width_mm: float
    height_mm: float
    skipped: int

    @property
    def segments(self):
        return sum(len(path) - 1 for path in self.paths)


def load_svg(filename):
    svg = SVG.parse(filename, reify=True)
    paths = []
    skipped = 0
    for element in svg.elements():
        if getattr(element, "values", {}).get("visibility") == "hidden":
            continue
        if not isinstance(element, Shape):
            if type(element).__name__ in ("SVGText", "SVGImage"):
                skipped += 1
            continue
        path = Path(element) if not isinstance(element, Path) else element
        path.reify()
        current = []
        for segment in path:
            if isinstance(segment, Move):
                if len(current) > 1:
                    paths.append(current)
                current = [_point(segment.end)]
                continue
            if not current:
                current = [_point(segment.start)]
            length = segment.length(error=1e-3)
            samples = (1 if isinstance(segment, (Line, Close)) else
                       max(1, math.ceil(length)))
            if samples > 10000:
                raise ValueError("SVG curve is too complex")
            for index in range(1, samples + 1):
                current.append(_point(segment.point(index / samples)))
            if isinstance(segment, Close):
                if len(current) > 1:
                    paths.append(current)
                current = []
        if len(current) > 1:
            paths.append(current)
    paths = [[p for i, p in enumerate(path) if i == 0 or p != path[i - 1]] for path in paths]
    paths = [path for path in paths if len(path) > 1]
    if not paths:
        raise ValueError("SVG has no plottable vector paths")
    if sum(len(path) - 1 for path in paths) > 50000:
        raise ValueError("SVG has too many segments (limit: 50,000)")
    xs = [p[0] for path in paths for p in path]
    ys = [p[1] for path in paths for p in path]
    minimum_x, minimum_y = min(xs), min(ys)
    scale = 25.4 / 96
    normalized = [[((x - minimum_x) * scale, (y - minimum_y) * scale)
                   for x, y in path] for path in paths]
    return Drawing(normalized, (max(xs) - minimum_x) * scale,
                   (max(ys) - minimum_y) * scale, skipped)


def _point(value):
    point = (float(value.x), float(value.y))
    if not all(math.isfinite(n) for n in point):
        raise ValueError("SVG contains invalid coordinates")
    return point
