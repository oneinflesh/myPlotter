from PySide6.QtCore import QObject, Signal, Slot

from myplotter.svg.document import load_svg


class SvgLoader(QObject):
    loaded = Signal(object, str)

    def __init__(self, filename):
        super().__init__()
        self.filename = filename

    @Slot()
    def run(self):
        try:
            self.loaded.emit(load_svg(self.filename), "")
        except Exception as error:
            self.loaded.emit(None, str(error))
