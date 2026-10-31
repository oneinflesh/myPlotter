def jog(board, axis, steps, duration_ms, geometry):
    if axis not in ("X", "Y"):
        raise ValueError("Axis must be X or Y")
    if not 1 <= abs(steps) <= 2000:
        raise ValueError("Jog distance must be 1–2000 steps")
    if not 100 <= duration_ms <= 10000:
        raise ValueError("Jog time must be 100–10000 ms")
    first, second = (steps, 0) if axis == "X" else (0, steps)
    command = "XM" if geometry == "mixed" else "SM"
    board.command(f"{command},{duration_ms},{first},{second}")


def release_motors(board):
    board.command("EM,0,0")
