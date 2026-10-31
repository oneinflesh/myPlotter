def set_pen(board, raised):
    board.command("SP,1,500" if raised else "SP,0,500")
