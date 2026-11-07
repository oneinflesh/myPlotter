from myplotter.motion.trajectory import plan_path
from myplotter.pen.control import set_pen


def mark_start(board, steps_per_mm, speed_mm_s, geometry):
    # The center of the X is the saved page start. Allow 3 mm of clear travel
    # around that point before using this command.
    strokes = [[(-2, -2), (2, 2)], [(-2, 2), (2, -2)]]
    position = (0.0, 0.0)
    set_pen(board, True)
    board.wait_idle()
    try:
        for stroke in strokes:
            for move in plan_path([position, stroke[0]], steps_per_mm, speed_mm_s):
                board.command(move.command(geometry))
                board.wait_idle()
            set_pen(board, False)
            board.wait_idle()
            for move in plan_path(stroke, steps_per_mm, speed_mm_s):
                board.command(move.command(geometry))
                board.wait_idle()
            set_pen(board, True)
            board.wait_idle()
            position = stroke[-1]
        for move in plan_path([position, (0.0, 0.0)], steps_per_mm, speed_mm_s):
            board.command(move.command(geometry))
            board.wait_idle()
    finally:
        set_pen(board, True)
        board.wait_idle()
