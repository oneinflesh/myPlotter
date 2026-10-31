def jog(board, axis, steps, duration_ms):
    if axis not in (1, 2):
        raise ValueError("Axis must be 1 or 2")
    if not 1 <= abs(steps) <= 2000:
        raise ValueError("Jog distance must be 1–2000 steps")
    if not 100 <= duration_ms <= 10000:
        raise ValueError("Jog time must be 100–10000 ms")
    first, second = (steps, 0) if axis == 1 else (0, steps)
    board.command(f"SM,{duration_ms},{first},{second}")


def release_motors(board):
    board.command("EM,0,0")
