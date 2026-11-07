from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    paths: list
    first_segment: int
    last_segment: int


def split_sections(drawing, limit=100):
    total = drawing.segments
    count = min(limit, total)
    if not count:
        return []
    boundaries = [(index * total) // count for index in range(1, count + 1)]
    sections = []
    paths = []
    segment = 0
    first = 0
    current = []
    for path in drawing.paths:
        for start, end in zip(path, path[1:]):
            if not current:
                current = [start]
            current.append(end)
            segment += 1
            if segment == boundaries[len(sections)]:
                paths.append(current)
                sections.append(Section(paths, first, segment))
                paths = []
                current = []
                first = segment
        if current:
            paths.append(current)
            current = []
    return sections
