from myplotter.svg.document import Drawing


def rotate_quarter_turn(drawing, clockwise):
    if clockwise:
        paths = [[(drawing.height_mm - y, x) for x, y in path]
                 for path in drawing.paths]
    else:
        paths = [[(y, drawing.width_mm - x) for x, y in path]
                 for path in drawing.paths]
    return Drawing(paths, drawing.height_mm, drawing.width_mm, drawing.skipped)
