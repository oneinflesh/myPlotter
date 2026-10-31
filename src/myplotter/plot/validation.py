import math


def validate_drawing(drawing):
    if (not math.isfinite(drawing.width_mm) or not math.isfinite(drawing.height_mm)
            or drawing.width_mm <= 0 or drawing.height_mm <= 0):
        raise ValueError("Drawing has invalid paper dimensions")
    if not drawing.paths or any(len(path) < 2 for path in drawing.paths):
        raise ValueError("Drawing has an empty or incomplete path")
    for path in drawing.paths:
        for x, y in path:
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Drawing contains invalid coordinates")
            if not (-1e-7 <= x <= drawing.width_mm + 1e-7
                    and -1e-7 <= y <= drawing.height_mm + 1e-7):
                raise ValueError("Artwork extends outside the selected paper")
