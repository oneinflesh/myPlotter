import math
from dataclasses import dataclass

from svgelements import Close, Move, Path, SVG, Shape

from myplotter.machine.profile import MAX_PAPER_DIMENSION_MM
from myplotter.svg.curves import CURVE_TOLERANCE_MM, flatten_segment, point


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
    vectors = []
    boxes = []
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
        segment_boxes = [segment.bbox() for segment in path
                         if not isinstance(segment, Move)]
        segment_boxes = [box for box in segment_boxes if box is not None]
        if not segment_boxes:
            continue
        box = (min(box[0] for box in segment_boxes), min(box[1] for box in segment_boxes),
               max(box[2] for box in segment_boxes), max(box[3] for box in segment_boxes))
        if not all(math.isfinite(value) for value in box):
            raise ValueError("SVG contains invalid coordinates")
        vectors.append(path)
        boxes.append(box)
    if not boxes:
        raise ValueError("SVG has no plottable vector paths")
    minimum_x, minimum_y = min(box[0] for box in boxes), min(box[1] for box in boxes)
    maximum_x, maximum_y = max(box[2] for box in boxes), max(box[3] for box in boxes)
    extent = max(maximum_x - minimum_x, maximum_y - minimum_y)
    if not math.isfinite(extent) or extent <= 0:
        raise ValueError("SVG has no plottable vector paths")
    tolerance = CURVE_TOLERANCE_MM * extent / MAX_PAPER_DIMENSION_MM
    for path in vectors:
        current = []
        for segment in path:
            if isinstance(segment, Move):
                if len(current) > 1:
                    paths.append(current)
                current = [point(segment.end)]
                continue
            if not current:
                current = [point(segment.start)]
            current.extend(flatten_segment(segment, tolerance))
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
    scale = 25.4 / 96
    normalized = [[((x - minimum_x) * scale, (y - minimum_y) * scale)
                   for x, y in path] for path in paths]
    return Drawing(normalized, (maximum_x - minimum_x) * scale,
                   (maximum_y - minimum_y) * scale, skipped)
