PEN_SETTLE_MS = 180
SERVO_RATE = 1000
DEFAULT_UP = 16000
DEFAULT_DOWN = 12000


def configure_pen(board):
    board.command(f"SC,11,{SERVO_RATE}")
    board.command(f"SC,12,{SERVO_RATE}")


def set_pen(board, raised):
    board.command(pen_command(raised))


def pen_command(raised):
    return f"SP,{0 if raised else 1},{PEN_SETTLE_MS}"


def set_height(board, raised, value):
    if not 6000 <= value <= 24000:
        raise ValueError("Pen height must be between 6000 and 24000")
    board.command(f"SC,{5 if raised else 4},{value}")


def migrate_pen_settings(settings):
    if settings.value("pen/direction_version", 1, type=int) >= 2:
        return
    if settings.contains("pen/up") or settings.contains("pen/down"):
        previous_up = int(settings.value("pen/up", 12000))
        previous_down = int(settings.value("pen/down", 16000))
        settings.setValue("pen/up", previous_down)
        settings.setValue("pen/down", previous_up)
    settings.setValue("pen/direction_version", 2)
