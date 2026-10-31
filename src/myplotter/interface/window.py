from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from myplotter.connection.board import Board, discover_boards
from myplotter.motion.control import jog, release_motors
from myplotter.pen.control import set_pen


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.board = Board()
        self.setWindowTitle("My Plotter")
        self.setMinimumWidth(380)

        root = QVBoxLayout()
        self.ports = QComboBox()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_ports)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        row = QHBoxLayout()
        row.addWidget(self.ports)
        row.addWidget(refresh)
        row.addWidget(self.connect_button)
        root.addLayout(row)

        self.status = QLabel("Disconnected")
        root.addWidget(self.status)

        pen_group = QGroupBox("Pen")
        pen_row = QHBoxLayout(pen_group)
        for label, raised in (("Up", True), ("Down", False)):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, up=raised: self.run(lambda: set_pen(self.board, up)))
            pen_row.addWidget(button)
        root.addWidget(pen_group)

        motion_group = QGroupBox("Manual movement")
        motion_layout = QVBoxLayout(motion_group)
        settings = QFormLayout()
        self.steps = QSpinBox()
        self.steps.setRange(1, 2000)
        self.steps.setValue(100)
        self.duration = QSpinBox()
        self.duration.setRange(100, 10000)
        self.duration.setValue(1000)
        self.duration.setSuffix(" ms")
        settings.addRow("Steps", self.steps)
        settings.addRow("Time", self.duration)
        motion_layout.addLayout(settings)
        for axis in (1, 2):
            axis_row = QHBoxLayout()
            for direction, sign in (("−", -1), ("+", 1)):
                button = QPushButton(f"Axis {axis} {direction}")
                button.clicked.connect(lambda _checked=False, a=axis, s=sign: self.run(
                    lambda: jog(self.board, a, s * self.steps.value(), self.duration.value())))
                axis_row.addWidget(button)
            motion_layout.addLayout(axis_row)
        root.addWidget(motion_group)

        release = QPushButton("Release motors")
        release.clicked.connect(lambda: self.run(lambda: release_motors(self.board)))
        root.addWidget(release)
        root.addStretch()
        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)
        self.refresh_ports()

    def refresh_ports(self):
        self.ports.clear()
        self.ports.addItems(discover_boards())

    def toggle_connection(self):
        if self.board.connected:
            self.board.disconnect()
            self.status.setText("Disconnected")
            self.connect_button.setText("Connect")
            return
        if not self.ports.currentText():
            QMessageBox.warning(self, "Plotter", "No EiBotBoard found. Refresh after connecting it.")
            return
        try:
            version = self.board.connect(self.ports.currentText())
        except Exception as error:
            QMessageBox.critical(self, "Connection failed", str(error))
            return
        self.status.setText(f"Connected: {version}")
        self.connect_button.setText("Disconnect")

    def run(self, action):
        try:
            action()
        except Exception as error:
            QMessageBox.critical(self, "Plotter error", str(error))

    def closeEvent(self, event):
        self.board.disconnect()
        super().closeEvent(event)
