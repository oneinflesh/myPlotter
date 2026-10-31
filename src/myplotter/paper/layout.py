from myplotter.svg.document import Drawing


PAPER_SIZES = {"A4": (210.0, 297.0), "A3": (297.0, 420.0),
               "A2": (420.0, 594.0)}


def fit_to_paper(drawing, size, margin_mm=10.0):
    if size not in PAPER_SIZES:
        raise ValueError(f"Unknown paper size: {size}")
    short, long = PAPER_SIZES[size]
    portrait = (short, long)
    landscape = (long, short)

    def scale_for(page):
        available_width = page[0] - 2 * margin_mm
        available_height = page[1] - 2 * margin_mm
        if available_width <= 0 or available_height <= 0:
            raise ValueError("Paper margin leaves no drawing area")
        width_scale = (available_width / drawing.width_mm
                       if drawing.width_mm else float("inf"))
        height_scale = (available_height / drawing.height_mm
                        if drawing.height_mm else float("inf"))
        return min(width_scale, height_scale, 1.0)

    page = max((portrait, landscape), key=scale_for)
    factor = scale_for(page)
    x_offset = (page[0] - drawing.width_mm * factor) / 2
    y_offset = (page[1] - drawing.height_mm * factor) / 2
    paths = [[(x_offset + x * factor, y_offset + y * factor)
              for x, y in path] for path in drawing.paths]
    return Drawing(paths, page[0], page[1], drawing.skipped), factor


def place_on_paper(source, page_width, page_height, scale, x, y):
    paths = [[(x + px * scale, y + py * scale) for px, py in path]
             for path in source.paths]
    return Drawing(paths, page_width, page_height, source.skipped)
