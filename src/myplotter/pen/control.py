PEN_SETTLE_MS = 180
SERVO_RATE = 1000


def configure_pen(board):
    board.command(f"SC,11,{SERVO_RATE}")
    board.command(f"SC,12,{SERVO_RATE}")


def set_pen(board, raised):
    board.command(f"SP,{1 if raised else 0},{PEN_SETTLE_MS}")
