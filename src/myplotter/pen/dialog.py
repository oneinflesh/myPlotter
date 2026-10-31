from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QSpinBox, QVBoxLayout)

from myplotter.pen.control import DEFAULT_DOWN, DEFAULT_UP, set_height, set_pen


class PenDialog(QDialog):
    def __init__(self, board, parent=None):
        super().__init__(parent)
        self.board = board
        self.settings = QSettings("MyPlotter", "MyPlotter")
        self.setWindowTitle("Pen Controllers")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Adjust servo positions, then test each height."))
        form = QFormLayout()
        self.up = self._spin("pen/up", DEFAULT_UP)
        self.down = self._spin("pen/down", DEFAULT_DOWN)
        form.addRow("Pen up height", self.up)
        form.addRow("Pen down height", self.down)
        layout.addLayout(form)
        row = QHBoxLayout()
        up_button = QPushButton("Test Up")
        up_button.clicked.connect(lambda: self._test(True))
        down_button = QPushButton("Test Down")
        down_button.clicked.connect(lambda: self._test(False))
        row.addWidget(up_button)
        row.addWidget(down_button)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _spin(self, key, default):
        spin = QSpinBox()
        spin.setRange(6000, 24000)
        spin.setSingleStep(100)
        spin.setValue(int(self.settings.value(key, default)))
        return spin

    def _test(self, raised):
        try:
            self.board.wait_idle()
            set_height(self.board, raised, self.up.value() if raised else self.down.value())
            set_pen(self.board, raised)
            self.board.wait_idle()
        except Exception as error:
            QMessageBox.critical(self, "Pen test failed", str(error))

    def _save(self):
        try:
            self.board.wait_idle()
            set_height(self.board, True, self.up.value())
            set_height(self.board, False, self.down.value())
            self.settings.setValue("pen/up", self.up.value())
            self.settings.setValue("pen/down", self.down.value())
            self.accept()
        except Exception as error:
            QMessageBox.critical(self, "Pen settings failed", str(error))
