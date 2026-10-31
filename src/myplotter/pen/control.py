PEN_SETTLE_MS = 180
SERVO_RATE = 1000
DEFAULT_UP = 12000
DEFAULT_DOWN = 16000


def configure_pen(board):
    board.command(f"SC,11,{SERVO_RATE}")
    board.command(f"SC,12,{SERVO_RATE}")


def set_pen(board, raised):
    board.command(f"SP,{1 if raised else 0},{PEN_SETTLE_MS}")


def set_height(board, raised, value):
    if not 6000 <= value <= 24000:
        raise ValueError("Pen height must be between 6000 and 24000")
    board.command(f"SC,{4 if raised else 5},{value}")
