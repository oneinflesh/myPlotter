import math

from myplotter.svg.document import Drawing


def pen_up_distance(paths):
    position = (0.0, 0.0)
    distance = 0.0
    for path in paths:
        distance += math.dist(position, path[0])
        position = path[-1]
    return distance + math.dist(position, (0.0, 0.0))


def optimize_travel(drawing):
    """Reorder whole strokes without changing any drawn geometry."""
    remaining = list(range(len(drawing.paths)))
    position = (0.0, 0.0)
    paths = []
    # Large documents stay responsive: reverse individual strokes in file
    # order rather than running a quadratic nearest-stroke search.
    greedy = len(remaining) <= 1500
    for original_index in range(len(remaining)):
        if greedy:
            index = min(remaining, key=lambda number: min(
                math.dist(position, drawing.paths[number][0]),
                math.dist(position, drawing.paths[number][-1])))
            remaining.remove(index)
        else:
            index = original_index
        path = drawing.paths[index]
        if path[0] == path[-1] and len(path) > 2:
            vertices = path[:-1]
            seam = min(range(len(vertices)),
                       key=lambda point: math.dist(position, vertices[point]))
            path = vertices[seam:] + vertices[:seam] + [vertices[seam]]
        elif math.dist(position, path[-1]) < math.dist(position, path[0]):
            path = path[::-1]
        paths.append(path)
        position = path[-1]
    if pen_up_distance(paths) >= pen_up_distance(drawing.paths):
        return drawing
    return Drawing(paths, drawing.width_mm, drawing.height_mm, drawing.skipped)
