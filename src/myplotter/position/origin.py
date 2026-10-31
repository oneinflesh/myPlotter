class StartPoint:
    def __init__(self):
        self.steps = None

    @property
    def is_set(self):
        return self.steps is not None

    def clear(self):
        self.steps = None

    def capture(self, board):
        board.wait_idle()
        self.steps = board.query_steps()

    def verify(self, board):
        if self.steps is None:
            raise RuntimeError("Set the current pen position as the page start first")
        board.wait_idle()
        if board.query_steps() != self.steps:
            self.clear()
            raise RuntimeError("Pen position changed. Set the start point again")
