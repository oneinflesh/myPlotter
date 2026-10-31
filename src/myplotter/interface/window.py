from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from myplotter.connection.board import Board, discover_boards
from myplotter.motion.control import jog, release_motors
from myplotter.pen.control import set_pen
from myplotter.plot.job import PlotJob
from myplotter.svg.document import load_svg
from myplotter.svg.preview import DrawingPreview


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.board = Board()
        self.drawing = None
        self.job = None
        self.thread = None
        self.close_pending = False
        self.setWindowTitle("My Plotter")
        self.setMinimumWidth(560)

        root = QVBoxLayout()
        self.ports = QComboBox()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        row = QHBoxLayout()
        row.addWidget(self.ports)
        row.addWidget(self.refresh_button)
        row.addWidget(self.connect_button)
        root.addLayout(row)
        self.status = QLabel("Disconnected")
        root.addWidget(self.status)

        self.choose_button = QPushButton("Choose SVG…")
        self.choose_button.clicked.connect(self.choose_svg)
        root.addWidget(self.choose_button)
        self.file_label = QLabel("No SVG selected")
        root.addWidget(self.file_label)
        self.preview = DrawingPreview()
        root.addWidget(self.preview, 1)

        self.plot_group = QGroupBox("Plot settings")
        plot_settings = QFormLayout(self.plot_group)
        self.geometry = QComboBox()
        self.geometry.addItem("Select motor layout…", None)
        self.geometry.addItem("Independent X/Y motors", "cartesian")
        self.geometry.addItem("AxiDraw / CoreXY mixed axes", "mixed")
        plot_settings.addRow("Motor layout", self.geometry)
        self.steps_per_mm = QDoubleSpinBox()
        self.steps_per_mm.setRange(1, 1000)
        self.steps_per_mm.setValue(80)
        self.steps_per_mm.setSuffix(" steps/mm")
        plot_settings.addRow("Calibration", self.steps_per_mm)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(1, 50)
        self.speed.setValue(10)
        self.speed.setSuffix(" mm/s")
        plot_settings.addRow("Speed", self.speed)
        self.max_width = QSpinBox()
        self.max_width.setRange(1, 1000)
        self.max_width.setValue(200)
        self.max_width.setSuffix(" mm")
        plot_settings.addRow("Max width", self.max_width)
        self.max_height = QSpinBox()
        self.max_height.setRange(1, 1000)
        self.max_height.setValue(200)
        self.max_height.setSuffix(" mm")
        plot_settings.addRow("Max height", self.max_height)
        root.addWidget(self.plot_group)

        plot_row = QHBoxLayout()
        self.plot_button = QPushButton("Start plot")
        self.plot_button.clicked.connect(self.start_plot)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_plot)
        plot_row.addWidget(self.plot_button)
        plot_row.addWidget(self.stop_button)
        root.addLayout(plot_row)
        self.progress = QProgressBar()
        root.addWidget(self.progress)
        self.plot_status = QLabel("Ready")
        root.addWidget(self.plot_status)

        self.pen_group = QGroupBox("Pen")
        pen_row = QHBoxLayout(self.pen_group)
        for label, raised in (("Up", True), ("Down", False)):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, up=raised: self.run(
                lambda: set_pen(self.board, up)))
            pen_row.addWidget(button)
        root.addWidget(self.pen_group)

        self.motion_group = QGroupBox("Manual movement")
        motion_layout = QVBoxLayout(self.motion_group)
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
        root.addWidget(self.motion_group)

        self.release_button = QPushButton("Release motors")
        self.release_button.clicked.connect(lambda: self.run(lambda: release_motors(self.board)))
        root.addWidget(self.release_button)
        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)
        self.refresh_ports()

    def refresh_ports(self):
        self.ports.clear()
        self.ports.addItems(discover_boards())

    def choose_svg(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Choose SVG", "", "SVG files (*.svg)")
        if not filename:
            return
        try:
            drawing = load_svg(filename)
        except Exception as error:
            QMessageBox.critical(self, "SVG error", str(error))
            return
        self.drawing = drawing
        self.file_label.setText(f"{Path(filename).name} · {drawing.width_mm:.1f} × "
                                f"{drawing.height_mm:.1f} mm · {drawing.segments} segments")
        self.preview.set_drawing(drawing)
        self.progress.setMaximum(drawing.segments)
        self.progress.setValue(0)
        self.plot_status.setText(f"Ready · {drawing.skipped} text/image elements skipped"
                                 if drawing.skipped else "Ready")

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

    def start_plot(self):
        if self.drawing is None:
            QMessageBox.warning(self, "Plotter", "Choose an SVG first.")
            return
        if not self.board.connected:
            QMessageBox.warning(self, "Plotter", "Connect the EiBotBoard first.")
            return
        if self.geometry.currentData() is None:
            QMessageBox.warning(self, "Plotter", "Select the motor layout before plotting.")
            return
        if (self.drawing.width_mm > self.max_width.value() or
                self.drawing.height_mm > self.max_height.value()):
            QMessageBox.warning(self, "Plotter", "SVG exceeds the configured travel area.")
            return
        self.preview.set_completed(0)
        self.progress.setValue(0)
        self.plot_status.setText("Plotting…")
        self._set_plotting(True)
        self.thread = QThread(self)
        self.job = PlotJob(self.board, self.drawing, self.steps_per_mm.value(),
                           self.speed.value(), self.geometry.currentData())
        self.job.moveToThread(self.thread)
        self.thread.started.connect(self.job.run)
        self.job.progress.connect(self._plot_progress)
        self.job.finished.connect(self._plot_finished)
        self.job.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.job.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._plot_thread_finished)
        self.thread.start()

    def stop_plot(self):
        if self.job is not None:
            self.job.stop()
            self.plot_status.setText("Stopping…")

    def _plot_progress(self, count):
        self.progress.setValue(count)
        self.preview.set_completed(count)

    def _plot_finished(self, success, message):
        self.plot_status.setText(message)
        if not success and message != "Stopped":
            QMessageBox.critical(self, "Plot failed", message)

    def _plot_thread_finished(self):
        self.job = None
        self.thread = None
        self._set_plotting(False)
        if self.close_pending:
            self.close()

    def _set_plotting(self, active):
        self.ports.setEnabled(not active)
        self.refresh_button.setEnabled(not active)
        self.connect_button.setEnabled(not active)
        self.choose_button.setEnabled(not active)
        self.plot_group.setEnabled(not active)
        self.plot_button.setEnabled(not active)
        self.stop_button.setEnabled(active)
        self.pen_group.setEnabled(not active)
        self.motion_group.setEnabled(not active)
        self.release_button.setEnabled(not active)

    def run(self, action):
        try:
            action()
        except Exception as error:
            QMessageBox.critical(self, "Plotter error", str(error))

    def closeEvent(self, event):
        if self.thread is not None:
            self.stop_plot()
            self.close_pending = True
            event.ignore()
            return
        self.board.disconnect()
        super().closeEvent(event)
