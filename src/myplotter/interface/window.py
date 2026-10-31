from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QProgressDialog, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from myplotter.connection.board import Board, discover_boards
from myplotter.motion.control import jog, release_motors
from myplotter.pen.control import set_pen
from myplotter.paper.layout import fit_to_paper
from myplotter.plot.job import PlotJob
from myplotter.svg.loader import SvgLoader
from myplotter.svg.preview import DrawingPreview


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.board = Board()
        self.drawing = None
        self.source_drawing = None
        self.filename = None
        self.loading_filename = None
        self.job = None
        self.thread = None
        self.load_thread = None
        self.loader = None
        self.load_dialog = None
        self.close_pending = False
        self.setWindowTitle("My Plotter")
        self.setMinimumSize(760, 500)

        root = QHBoxLayout()
        sidebar = QVBoxLayout()
        sidebar_widget = QWidget()
        sidebar_widget.setLayout(sidebar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(350)
        scroll.setMaximumWidth(460)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(sidebar_widget)
        root.addWidget(scroll)
        canvas = QVBoxLayout()
        root.addLayout(canvas, 1)
        self.ports = QComboBox()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        row = QHBoxLayout()
        row.addWidget(self.ports)
        row.addWidget(self.refresh_button)
        row.addWidget(self.connect_button)
        sidebar.addLayout(row)
        self.status = QLabel("Disconnected")
        sidebar.addWidget(self.status)

        self.choose_button = QPushButton("Choose SVG…")
        self.choose_button.clicked.connect(self.choose_svg)
        sidebar.addWidget(self.choose_button)
        self.file_label = QLabel("No SVG selected")
        canvas.addWidget(self.file_label)
        self.preview = DrawingPreview()
        canvas.addWidget(self.preview, 1)

        self.plot_group = QGroupBox("Plot settings")
        plot_settings = QFormLayout(self.plot_group)
        self.paper = QComboBox()
        self.paper.addItems(("A4", "A3", "A2"))
        self.paper.currentTextChanged.connect(self.apply_page)
        plot_settings.addRow("Paper", self.paper)
        self.geometry = QComboBox()
        self.geometry.addItem("CoreXY / AxiDraw", "mixed")
        self.geometry.addItem("Independent X/Y motors", "cartesian")
        self.geometry.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
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
        sidebar.addWidget(self.plot_group)

        plot_row = QHBoxLayout()
        self.plot_button = QPushButton("Start plot")
        self.plot_button.clicked.connect(self.start_plot)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_plot)
        plot_row.addWidget(self.plot_button)
        plot_row.addWidget(self.stop_button)
        sidebar.addLayout(plot_row)
        self.progress = QProgressBar()
        canvas.addWidget(self.progress)
        self.plot_status = QLabel("Ready")
        canvas.addWidget(self.plot_status)

        self.pen_group = QGroupBox("Pen")
        pen_row = QHBoxLayout(self.pen_group)
        for label, raised in (("Up", True), ("Down", False)):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, up=raised: self.run(
                lambda: set_pen(self.board, up)))
            pen_row.addWidget(button)
        sidebar.addWidget(self.pen_group)

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
        sidebar.addWidget(self.motion_group)

        self.release_button = QPushButton("Release motors")
        self.release_button.clicked.connect(lambda: self.run(lambda: release_motors(self.board)))
        sidebar.addWidget(self.release_button)
        sidebar.addStretch()
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
        self.loading_filename = filename
        self.choose_button.setEnabled(False)
        self.load_dialog = QProgressDialog("Loading SVG…", "", 0, 0, self)
        self.load_dialog.setCancelButton(None)
        self.load_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.load_dialog.setMinimumDuration(0)
        self.load_dialog.show()
        self.load_thread = QThread(self)
        self.loader = SvgLoader(filename)
        self.loader.moveToThread(self.load_thread)
        self.load_thread.started.connect(self.loader.run)
        self.loader.loaded.connect(self._svg_loaded)
        self.loader.loaded.connect(self.load_thread.quit)
        self.load_thread.finished.connect(self.loader.deleteLater)
        self.load_thread.finished.connect(self.load_thread.deleteLater)
        self.load_thread.finished.connect(self._svg_thread_finished)
        self.load_thread.start()

    def _svg_loaded(self, drawing, error):
        self.load_dialog.close()
        self.load_dialog = None
        if error:
            self.loading_filename = None
            QMessageBox.critical(self, "SVG error", error)
            return
        self.filename = self.loading_filename
        self.loading_filename = None
        self.source_drawing = drawing
        self.apply_page()

    def _svg_thread_finished(self):
        self.loader = None
        self.load_thread = None
        self.choose_button.setEnabled(True)
        if self.close_pending:
            self.close()

    def apply_page(self):
        if self.source_drawing is None:
            return
        self.drawing, factor = fit_to_paper(self.source_drawing, self.paper.currentText())
        orientation = "portrait" if self.drawing.height_mm > self.drawing.width_mm else "landscape"
        self.file_label.setText(
            f"{Path(self.filename).name} | {self.paper.currentText()} {orientation} "
            f"({self.drawing.width_mm:.0f} x {self.drawing.height_mm:.0f} mm) | "
            f"{self.drawing.segments} segments")
        self.preview.set_drawing(self.drawing)
        self.progress.setMaximum(self.drawing.segments)
        self.progress.setValue(0)
        notes = [f"Ready | artwork at {factor:.0%} scale | 10 mm margin"]
        if self.drawing.skipped:
            notes.append(f"{self.drawing.skipped} text/image elements skipped")
        self.plot_status.setText(" | ".join(notes))

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
        if self.thread is not None or self.load_thread is not None:
            self.stop_plot()
            self.close_pending = True
            event.ignore()
            return
        self.board.disconnect()
        super().closeEvent(event)
