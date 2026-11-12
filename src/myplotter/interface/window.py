from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QProgressDialog, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from myplotter.connection.board import Board, discover_boards
from myplotter.machine.profile import SPEED_PRESETS, STEPS_PER_MM
from myplotter.motion.control import release_motors
from myplotter.motion.jog import JogControl
from myplotter.motion.joystick import Joystick
from myplotter.pen.control import (configure_pen, migrate_pen_settings,
                                   set_height, set_pen)
from myplotter.pen.dialog import PenDialog
from myplotter.paper.layout import fit_to_paper, place_on_paper
from myplotter.plot.job import PlotJob
from myplotter.plot.estimate import estimate_seconds
from myplotter.plot.return_job import ReturnJob
from myplotter.position.origin import StartPoint
from myplotter.svg.loader import SvgLoader
from myplotter.svg.preview import DrawingPreview


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.board = Board()
        self.jog = JogControl(self.board, lambda: self.geometry.currentData())
        self.jog.moved.connect(self._jog_moved)
        self.jog.failed.connect(lambda message: QMessageBox.critical(
            self, "Joystick error", message))
        self.start_point = StartPoint()
        self.drawing = None
        self.placement = None
        self.drag_placement = None
        self.source_drawing = None
        self.filename = None
        self.loading_filename = None
        self.job = None
        self.job_kind = None
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
        canvas.addWidget(QLabel("Drag artwork to move; drag its blue corner to resize proportionally."))
        self.preview = DrawingPreview()
        self.preview.interaction_started.connect(self._begin_transform)
        self.preview.transform_requested.connect(self._transform_drawing)
        self.preview.interaction_finished.connect(self._finish_transform)
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
        self.speed = QComboBox()
        self.speed.addItems(SPEED_PRESETS)
        self.speed.setCurrentText("Medium")
        self.speed.currentTextChanged.connect(self.update_estimate)
        plot_settings.addRow("Speed", self.speed)
        sidebar.addWidget(self.plot_group)

        self.joystick_group = QGroupBox("Position joystick")
        joystick_layout = QVBoxLayout(self.joystick_group)
        self.joystick = Joystick()
        self.joystick.direction_changed.connect(self._jog_direction)
        joystick_layout.addWidget(self.joystick, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.joystick_group.setEnabled(False)
        sidebar.addWidget(self.joystick_group)
        self.release_button = QPushButton("Release motors")
        self.release_button.clicked.connect(lambda: self.run(self.release_motors))
        sidebar.addWidget(self.release_button)
        self.pen_button = QPushButton("Pen Controllers")
        self.pen_button.clicked.connect(self.open_pen_dialog)
        self.pen_button.setEnabled(False)
        self.pen_up_button = QPushButton("Pen Up")
        self.pen_up_button.clicked.connect(lambda: self.run(lambda: self.move_pen(True)))
        self.pen_down_button = QPushButton("Pen Down")
        self.pen_down_button.clicked.connect(lambda: self.run(lambda: self.move_pen(False)))
        pen_row = QHBoxLayout()
        pen_row.addWidget(self.pen_button)
        pen_row.addWidget(self.pen_up_button)
        pen_row.addWidget(self.pen_down_button)
        sidebar.addLayout(pen_row)
        self.pen_up_button.setEnabled(False)
        self.pen_down_button.setEnabled(False)

        self.start_button = QPushButton("Set current pen position as page start")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.set_start_point)
        sidebar.addWidget(self.start_button)
        self.start_label = QLabel("Use the joystick or place the pen at the paper's top-left corner, then set start.")
        self.start_label.setWordWrap(True)
        sidebar.addWidget(self.start_label)

        plot_row = QHBoxLayout()
        self.plot_button = QPushButton("Start plot")
        self.plot_button.clicked.connect(self.start_plot)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_plot)
        plot_row.addWidget(self.plot_button)
        plot_row.addWidget(self.pause_button)
        plot_row.addWidget(self.stop_button)
        sidebar.addLayout(plot_row)
        self.return_button = QPushButton("Back to Start")
        self.return_button.setEnabled(False)
        self.return_button.clicked.connect(self.back_to_start)
        sidebar.addWidget(self.return_button)
        self.progress = QProgressBar()
        canvas.addWidget(self.progress)
        self.plot_status = QLabel("Ready")
        canvas.addWidget(self.plot_status)

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
        fitted, factor = fit_to_paper(self.source_drawing, self.paper.currentText())
        x = (fitted.width_mm - self.source_drawing.width_mm * factor) / 2
        y = (fitted.height_mm - self.source_drawing.height_mm * factor) / 2
        self.placement = (x, y, factor)
        self.drawing = fitted
        orientation = "portrait" if self.drawing.height_mm > self.drawing.width_mm else "landscape"
        self.file_label.setText(
            f"{Path(self.filename).name} | {self.paper.currentText()} {orientation} "
            f"({self.drawing.width_mm:.0f} x {self.drawing.height_mm:.0f} mm) | "
            f"{self.drawing.segments} segments")
        self.preview.set_drawing(self.drawing)
        self.update_estimate()
        self.preview.set_start_ready(self.start_point.is_set)
        self.progress.setMaximum(self.drawing.segments)
        self.progress.setValue(0)
        notes = [f"Ready | artwork at {factor:.0%} scale | 10 mm margin"]
        if self.drawing.skipped:
            notes.append(f"{self.drawing.skipped} text/image elements skipped")
        self.plot_status.setText(" | ".join(notes))

    def _begin_transform(self):
        if self.job is None and self.placement is not None:
            self.drag_placement = self.placement

    def _transform_drawing(self, mode, dx, dy):
        if self.job is not None or self.drag_placement is None:
            return
        x, y, scale = self.drag_placement
        source = self.source_drawing
        page_width, page_height = self.drawing.width_mm, self.drawing.height_mm
        if mode == "move":
            x = max(0, min(page_width - source.width_mm * scale, x + dx))
            y = max(0, min(page_height - source.height_mm * scale, y + dy))
        else:
            width_fraction = dx / source.width_mm if source.width_mm else 0
            height_fraction = dy / source.height_mm if source.height_mm else 0
            change = (width_fraction if abs(width_fraction) >= abs(height_fraction)
                      else height_fraction)
            maximum = min((page_width - x) / source.width_mm
                          if source.width_mm else float("inf"),
                          (page_height - y) / source.height_mm
                          if source.height_mm else float("inf"))
            scale = max(min(0.01, maximum), min(maximum, scale + change))
        self.placement = (x, y, scale)
        self.drawing = place_on_paper(source, page_width, page_height, scale, x, y)
        self.preview.set_drawing(self.drawing)

    def _finish_transform(self):
        if self.drag_placement is None:
            return
        self.drag_placement = None
        self.update_estimate()
        x, y, scale = self.placement
        self.plot_status.setText(f"Artwork placed at {x:.1f}, {y:.1f} mm | "
                                 f"scale {scale:.0%}")

    def toggle_connection(self):
        if self.board.connected:
            self.jog.stop()
            self.board.disconnect()
            self.jog.enabled = False
            self.clear_start()
            self.start_button.setEnabled(False)
            self.joystick_group.setEnabled(False)
            self.pen_button.setEnabled(False)
            self.pen_up_button.setEnabled(False)
            self.pen_down_button.setEnabled(False)
            self.status.setText("Disconnected")
            self.connect_button.setText("Connect")
            return
        if not self.ports.currentText():
            QMessageBox.warning(self, "Plotter", "No EiBotBoard found. Refresh after connecting it.")
            return
        try:
            version = self.board.connect(self.ports.currentText())
            configure_pen(self.board)
            settings = QSettings("MyPlotter", "MyPlotter")
            migrate_pen_settings(settings)
            if settings.contains("pen/up"):
                set_height(self.board, True, int(settings.value("pen/up")))
            if settings.contains("pen/down"):
                set_height(self.board, False, int(settings.value("pen/down")))
        except Exception as error:
            self.board.disconnect()
            QMessageBox.critical(self, "Connection failed", str(error))
            return
        self.status.setText(f"Connected: {version}")
        self.connect_button.setText("Disconnect")
        self.start_button.setEnabled(True)
        self.joystick_group.setEnabled(True)
        self.pen_button.setEnabled(True)
        self.pen_up_button.setEnabled(True)
        self.pen_down_button.setEnabled(True)

    def update_estimate(self):
        if self.drawing is None:
            return
        seconds = estimate_seconds(self.drawing, STEPS_PER_MM,
                                   SPEED_PRESETS[self.speed.currentText()],
                                   self.geometry.currentData())
        self.preview.set_estimate(seconds)

    def clear_start(self):
        self.start_point.clear()
        self.start_label.setText("Use the joystick or place the pen at the paper's top-left corner, then set start.")
        self.preview.set_start_ready(False)
        self.return_button.setEnabled(False)

    def set_start_point(self):
        try:
            self.jog.stop()
            self.start_point.capture(self.board)
        except Exception as error:
            QMessageBox.critical(self, "Start point", str(error))
            return
        self.start_label.setText("Page start set at the pen's current position.")
        self.preview.set_start_ready(True)
        self.preview.set_head(0, 0, False)
        self.return_button.setEnabled(True)

    def release_motors(self):
        self.jog.stop()
        self.board.wait_idle()
        self.clear_start()
        release_motors(self.board)
        self.jog.enabled = False

    def _jog_direction(self, x, y):
        if self.board.connected and self.job is None:
            self.jog.set_direction(x, y)

    def _jog_moved(self):
        if self.start_point.is_set:
            self.clear_start()

    def open_pen_dialog(self):
        if not self.board.connected:
            QMessageBox.warning(self, "Pen Controllers", "Connect the plotter first.")
            return
        self.jog.stop()
        PenDialog(self.board, self).exec()

    def move_pen(self, raised):
        self.jog.stop()
        self.board.wait_idle()
        set_pen(self.board, raised)
        self.board.wait_idle()

    def start_plot(self):
        if self.drawing is None:
            QMessageBox.warning(self, "Plotter", "Choose an SVG first.")
            return
        if not self.board.connected:
            QMessageBox.warning(self, "Plotter", "Connect the EiBotBoard first.")
            return
        try:
            self.start_point.verify(self.board)
        except Exception as error:
            self.clear_start()
            QMessageBox.warning(self, "Start point", str(error))
            return
        self.preview.set_completed(0)
        self.preview.set_head(0, 0, False)
        self.progress.setValue(0)
        self.progress.setRange(0, 0)
        self.plot_status.setText("Preparing drawing segments…")
        self.job_kind = "plot"
        self.job = PlotJob(self.board, self.drawing, STEPS_PER_MM,
                           SPEED_PRESETS[self.speed.currentText()], self.geometry.currentData(),
                           self.start_point.steps, source_filename=self.filename or "manual")
        self.job.progress.connect(self._plot_progress)
        self.job.prepared.connect(self._plot_prepared)
        self.job.paused.connect(self._pause_changed)
        self._start_worker()

    def back_to_start(self):
        if self.job is not None or not self.start_point.is_set or not self.board.connected:
            return
        self.plot_status.setText("Returning to start…")
        self.job_kind = "return"
        self.job = ReturnJob(self.board, self.start_point.steps, STEPS_PER_MM,
                             SPEED_PRESETS[self.speed.currentText()], self.geometry.currentData(),
                             source_filename=self.filename or "manual")
        self._start_worker()

    def _start_worker(self):
        self.jog.stop()
        self.board.wait_idle()
        self._set_plotting(True)
        self.thread = QThread(self)
        self.job.moveToThread(self.thread)
        self.thread.started.connect(self.job.run)
        self.job.position_changed.connect(self.preview.set_head)
        self.job.finished.connect(self._plot_finished)
        self.job.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.job.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._plot_thread_finished)
        self.thread.start()

    def toggle_pause(self):
        if self.job_kind != "plot" or self.job is None:
            return
        if self.job.pause_event.is_set():
            self.job.resume()
            self.pause_button.setText("Pause")
            self.plot_status.setText("Resuming…")
        else:
            self.job.pause()
            self.pause_button.setText("Resume")
            self.plot_status.setText("Pausing after current move…")

    def _pause_changed(self, paused):
        if self.job is None or self.job.stop_event.is_set():
            return
        self.pause_button.setText("Resume" if paused else "Pause")
        self.plot_status.setText("Paused" if paused else "Plotting…")

    def stop_plot(self):
        if self.job is not None:
            self.job.stop()
            self.pause_button.setEnabled(False)
            self.plot_status.setText("Stopping…")

    def _plot_prepared(self):
        self.progress.setRange(0, self.drawing.segments)
        self.progress.setValue(0)
        self.plot_status.setText("Plotting…")

    def _plot_progress(self, count):
        self.progress.setValue(count)
        self.preview.set_completed(count)
        if self.job is not None and not self.job.stop_event.is_set():
            self.plot_status.setText(f"Plotting | {count} / {self.drawing.segments} segments "
                                     f"({count / self.drawing.segments:.0%})")

    def _plot_finished(self, success, message):
        if self.job_kind == "plot" and self.drawing is not None:
            self.progress.setRange(0, self.drawing.segments)
        if message == "Stopped":
            self.plot_status.setText("Stopped | Back to Start is available")
        else:
            self.plot_status.setText(message)
        if not success and message != "Stopped":
            self.clear_start()
            QMessageBox.critical(self, "Plot failed", message)

    def _plot_thread_finished(self):
        self.job = None
        self.thread = None
        self.job_kind = None
        self._set_plotting(False)
        if self.close_pending:
            self.close()

    def _set_plotting(self, active):
        self.preview.set_editable(not active)
        self.ports.setEnabled(not active)
        self.refresh_button.setEnabled(not active)
        self.connect_button.setEnabled(not active)
        self.choose_button.setEnabled(not active)
        self.start_button.setEnabled(not active and self.board.connected)
        self.plot_group.setEnabled(not active)
        self.plot_button.setEnabled(not active)
        self.pause_button.setEnabled(active and self.job_kind == "plot")
        if not active:
            self.pause_button.setText("Pause")
        self.stop_button.setEnabled(active)
        self.return_button.setEnabled(not active and self.start_point.is_set and self.board.connected)
        self.joystick_group.setEnabled(not active and self.board.connected)
        self.pen_button.setEnabled(not active and self.board.connected)
        self.pen_up_button.setEnabled(not active and self.board.connected)
        self.pen_down_button.setEnabled(not active and self.board.connected)
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
