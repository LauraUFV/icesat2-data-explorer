from __future__ import annotations

import re
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsCoordinateTransform,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtGui import QCloseEvent
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from .hdf5_converter_task import HDF5ConverterTask
from .hdf5_support import (
    HDF5InstallTask,
    activate_managed_hdf5,
    hdf5_health,
)
from .ui_assets import (
    apply_dialog_theme,
    create_dialog_header,
    icon,
    set_button_icon,
)


class HDF5ConverterDialog(QDialog):
    """Read an ICESat-2 HDF5 granule and export its primary records."""

    PRODUCT_PATTERN = re.compile(r"ATL(?:03|08|13|24)", re.IGNORECASE)
    LARGE_LAYER_RENDER_THRESHOLD = 500_000

    def __init__(self, iface, parent=None):
        super().__init__(parent)

        self.iface = iface
        self.current_task: HDF5ConverterTask | None = None
        self.hdf5_install_task: HDF5InstallTask | None = None
        self.resume_conversion_after_install = False

        self.setWindowTitle("ICESat-2 HDF5 Converter")
        self.setWindowIcon(icon("converter.svg"))
        self.setMinimumSize(720, 540)
        self.resize(900, 650)
        apply_dialog_theme(self)

        self.input_edit = QLineEdit()
        self.input_edit.setReadOnly(True)
        self.input_button = QPushButton("Select HDF5 file")
        set_button_icon(self.input_button, "folder.svg")
        self.input_button.clicked.connect(self.select_input)

        self.product_label = QLabel("Not selected")

        self.hdf5_support_status_label = QLabel("Checking HDF5 support...")
        self.hdf5_support_button = QPushButton("Install HDF5 support")
        set_button_icon(self.hdf5_support_button, "refresh.svg")
        self.hdf5_support_button.clicked.connect(
            self.install_or_repair_hdf5_support
        )
        self.hdf5_support_note = QLabel(
            "Required only once for each QGIS installation/profile. "
            "The installer adds h5py to plugin-managed storage and runs it in an "
            "isolated QGIS-Python process; the source HDF5 file is never changed."
        )
        self.hdf5_support_note.setWordWrap(True)
        self.hdf5_support_note.setProperty("muted", True)

        self.format_combo = QComboBox()
        self.format_combo.addItem(
            "GeoPackage - WGS 84 point layer (recommended)",
            "gpkg",
        )
        self.format_combo.addItem("CSV - coordinate columns", "csv")
        self.format_combo.currentIndexChanged.connect(self.format_changed)

        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_button = QPushButton("Select output")
        set_button_icon(self.output_button, "folder.svg")
        self.output_button.clicked.connect(self.select_output)

        self.add_to_project_check = QCheckBox(
            "Add the converted GeoPackage layer to the current QGIS project"
        )
        self.add_to_project_check.setChecked(True)

        self.scope_note = QLabel(
            "The converter reads the primary per-photon or per-segment table "
            "from ATL03, ATL08, ATL13 or ATL24. The source HDF5 file is never "
            "modified. Scientific record fields, coordinates, source/orbit "
            "context and compatible ATL03 segment values are preserved; large "
            "multidimensional arrays are skipped. Very large GeoPackage layers "
            "are added with rendering disabled so QGIS remains responsive; the "
            "full converted dataset is preserved."
        )
        self.scope_note.setWordWrap(True)
        self.scope_note.setProperty("muted", True)

        self.status_label = QLabel("Select an ICESat-2 HDF5 file.")
        self.status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.run_button = QPushButton("Convert HDF5")
        self.run_button.setProperty("primary", True)
        set_button_icon(self.run_button, "run.svg")
        self.run_button.clicked.connect(self.start_conversion)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_conversion)

        self.close_button = QPushButton("Close")
        set_button_icon(self.close_button, "close.svg")
        self.close_button.clicked.connect(self.close)

        self._build_layout()
        self.refresh_hdf5_support_status()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        layout.addWidget(
            create_dialog_header(
                "HDF5 Converter",
                "Open local ICESat-2 granules and export their records.",
                "converter.svg",
                "v0.10.3",
            )
        )

        support_group = QGroupBox("HDF5 support")
        support_layout = QGridLayout(support_group)
        support_layout.setColumnStretch(0, 1)
        support_layout.addWidget(
            self.hdf5_support_status_label,
            0,
            0,
        )
        support_layout.addWidget(
            self.hdf5_support_button,
            0,
            1,
        )
        support_layout.addWidget(
            self.hdf5_support_note,
            1,
            0,
            1,
            2,
        )
        layout.addWidget(support_group)

        form = QFormLayout()

        input_row = QHBoxLayout()
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(self.input_button)
        form.addRow("Input HDF5:", input_row)
        form.addRow("Detected product:", self.product_label)
        form.addRow("Output format:", self.format_combo)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.output_button)
        form.addRow("Output file:", output_row)
        form.addRow("", self.add_to_project_check)

        layout.addLayout(form)
        layout.addWidget(self.scope_note)
        layout.addStretch(1)

        status_panel = QFrame()
        status_panel.setObjectName("ICESat2StatusPanel")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(10, 8, 10, 8)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        layout.addWidget(status_panel)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def output_format(self) -> str:
        return str(self.format_combo.currentData() or "gpkg")

    def detected_product(self) -> str:
        match = self.PRODUCT_PATTERN.search(
            Path(self.input_edit.text()).name
        )
        return match.group(0).upper() if match else "Unknown"

    def select_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ICESat-2 HDF5 file",
            "",
            "HDF5 files (*.h5 *.hdf5);;All files (*)",
        )
        if not path:
            return

        self.input_edit.setText(path)
        product = self.detected_product()
        self.product_label.setText(product)
        self.status_label.setText(
            "Ready to convert." if product != "Unknown" else
            "The product will be detected from the HDF5 metadata."
        )
        self._suggest_output_path()

    def _suggest_output_path(self) -> None:
        input_text = self.input_edit.text().strip()
        if not input_text:
            return

        suffix = ".gpkg" if self.output_format() == "gpkg" else ".csv"
        input_path = Path(input_text)
        self.output_edit.setText(
            str(input_path.with_name(input_path.stem + "_converted" + suffix))
        )

    def format_changed(self) -> None:
        self.add_to_project_check.setEnabled(
            self.output_format() == "gpkg"
        )
        self._suggest_output_path()

    def select_output(self) -> None:
        output_format = self.output_format()
        suffix = ".gpkg" if output_format == "gpkg" else ".csv"
        filter_text = (
            "GeoPackage (*.gpkg)" if output_format == "gpkg"
            else "CSV (*.csv)"
        )

        default_path = self.output_edit.text().strip()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select converted output",
            default_path,
            filter_text,
        )
        if not path:
            return

        if not path.lower().endswith(suffix):
            path += suffix
        self.output_edit.setText(path)

    def set_running(self, running: bool) -> None:
        for widget in (
            self.input_button,
            self.format_combo,
            self.output_button,
            self.add_to_project_check,
            self.run_button,
            self.close_button,
            self.hdf5_support_button,
        ):
            widget.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        if not running:
            self.add_to_project_check.setEnabled(
                self.output_format() == "gpkg"
            )

    def refresh_hdf5_support_status(
        self,
    ) -> tuple[str, str, str | None]:
        state, details, version = hdf5_health()

        if state == "ready":
            version_text = f" {version}" if version else ""
            self.hdf5_support_status_label.setText(
                f"Installed - h5py{version_text}"
            )
            self.hdf5_support_button.setText("Repair HDF5 support")
        elif state == "broken":
            self.hdf5_support_status_label.setText("Repair required")
            self.hdf5_support_button.setText("Repair HDF5 support")
        else:
            self.hdf5_support_status_label.setText("Not installed")
            self.hdf5_support_button.setText("Install HDF5 support")

        self.hdf5_support_status_label.setToolTip(details)
        return state, details, version

    def install_or_repair_hdf5_support(self) -> None:
        self._begin_hdf5_support_install(False)

    def _begin_hdf5_support_install(
        self,
        resume_conversion: bool,
        confirmed: bool = False,
    ) -> None:
        if self.hdf5_install_task is not None:
            QMessageBox.information(
                self,
                "HDF5 Converter",
                "HDF5-support installation is already running.",
            )
            return

        state, details, version = self.refresh_hdf5_support_status()
        action = "repair" if state in {"ready", "broken"} else "install"
        version_note = f"\n\nDetected version: {version}" if version else ""
        if not confirmed:
            response = QMessageBox.question(
                self,
                "Install HDF5 support",
                (
                    f"The converter will {action} h5py for the active QGIS "
                    "installation/profile. This requires an internet connection "
                    "and normally needs to be done only once.\n\n"
                    f"Current status: {details}{version_note}\n\nContinue?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if response != QMessageBox.StandardButton.Yes:
                return

        task = HDF5InstallTask()
        self.hdf5_install_task = task
        self.resume_conversion_after_install = resume_conversion

        for widget in (
            self.input_button,
            self.format_combo,
            self.output_button,
            self.add_to_project_check,
            self.run_button,
            self.close_button,
            self.hdf5_support_button,
        ):
            widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Installing HDF5 support...")
        self.hdf5_support_status_label.setText("Installing h5py...")

        task.progressChanged.connect(
            lambda value: self.progress_bar.setValue(round(value))
        )
        task.taskCompleted.connect(
            lambda: self.hdf5_support_install_finished(task, True)
        )
        task.taskTerminated.connect(
            lambda: self.hdf5_support_install_finished(task, False)
        )
        QgsApplication.taskManager().addTask(task)

    def hdf5_support_install_finished(
        self,
        task: HDF5InstallTask,
        completed: bool,
    ) -> None:
        if task is not self.hdf5_install_task:
            return

        self.hdf5_install_task = None
        resume_conversion = self.resume_conversion_after_install
        self.resume_conversion_after_install = False
        self.set_running(False)
        self.progress_bar.setValue(0)

        if not completed or task.error_message:
            self.status_label.setText("HDF5-support installation failed.")
            self.refresh_hdf5_support_status()
            details = task.error_message or "Installation was canceled."
            if task.error_traceback:
                details += "\n\nTechnical details:\n" + task.error_traceback
            QMessageBox.critical(self, "HDF5 Converter", details)
            return

        state, details, version = activate_managed_hdf5()
        self.refresh_hdf5_support_status()
        if state != "ready":
            self.status_label.setText("HDF5 support requires repair.")
            QMessageBox.critical(
                self,
                "HDF5 Converter",
                "h5py was installed but could not be loaded.\n\n" + details,
            )
            return

        self.status_label.setText(
            f"HDF5 support installed - h5py {version or 'ready'}."
        )
        QMessageBox.information(
            self,
            "HDF5 support installed",
            "The converter is ready to read ATL03, ATL08, ATL13 and ATL24 files.",
        )

        if resume_conversion:
            self.start_conversion()

    def start_conversion(self) -> None:
        if self.current_task is not None:
            return

        input_path = self.input_edit.text().strip()
        output_path = self.output_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, "HDF5 Converter", "Select an input HDF5 file.")
            return
        if not output_path:
            QMessageBox.warning(self, "HDF5 Converter", "Select an output file.")
            return

        state, details, _ = self.refresh_hdf5_support_status()
        if state != "ready":
            response = QMessageBox.question(
                self,
                "HDF5 support required",
                (
                    "This QGIS installation/profile needs HDF5 support before "
                    "the file can be converted. Install it automatically now?"
                    f"\n\nCurrent status: {details}"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if response == QMessageBox.StandardButton.Yes:
                self._begin_hdf5_support_install(True, confirmed=True)
            return

        task = HDF5ConverterTask(
            input_path=input_path,
            output_path=output_path,
            output_format=self.output_format(),
        )
        self.current_task = task
        self.set_running(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Reading and converting HDF5 records...")

        task.progressChanged.connect(
            lambda value: self.progress_bar.setValue(round(value))
        )
        task.taskCompleted.connect(
            lambda: self.conversion_finished(task, True)
        )
        task.taskTerminated.connect(
            lambda: self.conversion_finished(task, False)
        )
        QgsApplication.taskManager().addTask(task)

    def conversion_finished(
        self,
        task: HDF5ConverterTask,
        completed: bool,
    ) -> None:
        if task is not self.current_task:
            return

        self.current_task = None
        self.set_running(False)

        if not completed or task.error_message:
            self.progress_bar.setValue(0)
            self.status_label.setText("Conversion failed or was canceled.")
            if task.error_message:
                details = task.error_message
                if task.error_traceback:
                    details += "\n\nTechnical details:\n" + task.error_traceback
                QMessageBox.critical(self, "HDF5 Converter", details)
            return

        self.product_label.setText(task.product)
        self.progress_bar.setValue(100)

        large_layer = False
        if (
            task.output_format == "gpkg"
            and self.add_to_project_check.isChecked()
        ):
            layer = QgsVectorLayer(
                f"{Path(task.output_path).as_posix()}|layername={task.layer_name}",
                f"{task.product} HDF5 - {Path(task.input_path).stem}",
                "ogr",
            )
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                layer.updateExtents()

                canvas = self.iface.mapCanvas()
                extent = layer.extent()
                if not extent.isNull() and not extent.isEmpty():
                    canvas_crs = canvas.mapSettings().destinationCrs()
                    layer_crs = layer.crs()

                    if (
                        layer_crs.isValid()
                        and canvas_crs.isValid()
                        and layer_crs != canvas_crs
                    ):
                        try:
                            transform = QgsCoordinateTransform(
                                layer_crs,
                                canvas_crs,
                                QgsProject.instance(),
                            )
                            extent = transform.transformBoundingBox(extent)
                        except Exception:
                            extent = layer.extent()

                    if not extent.isNull() and not extent.isEmpty():
                        padding = max(
                            extent.width(),
                            extent.height(),
                        ) * 0.05
                        extent.grow(
                            padding if padding > 0 else 0.001
                        )
                        canvas.setExtent(extent)

                if task.row_count >= self.LARGE_LAYER_RENDER_THRESHOLD:
                    layer.setItemVisibilityChecked(False)
                    large_layer = True

                canvas.refresh()

        skipped_note = ""
        if task.skipped_datasets:
            skipped_note = (
                f" {len(set(task.skipped_datasets))} large multidimensional "
                "dataset(s) were skipped."
            )

        if large_layer:
            skipped_note += (
                " Rendering was disabled for the converted layer because it "
                f"contains {task.row_count:,} records. Enable the layer in "
                "the Layers panel when you are ready to visualize it."
            )

        self.status_label.setText(
            f"Converted {task.row_count:,} {task.product} records from "
            f"{task.beam_count} beam(s).{skipped_note}"
        )
        QMessageBox.information(
            self,
            "HDF5 conversion completed",
            (
                f"Product: {task.product}\n"
                f"Records: {task.row_count:,}\n"
                f"Output: {task.output_path}"
                + (
                    "\n\nThe converted layer was added with rendering disabled "
                    "because it is very large. The full dataset is preserved."
                    if large_layer
                    else ""
                )
            ),
        )

    def cancel_conversion(self) -> None:
        if self.current_task is not None:
            self.current_task.cancel()
            self.status_label.setText("Canceling conversion...")
        elif self.hdf5_install_task is not None:
            self.hdf5_install_task.cancel()
            self.status_label.setText("Canceling HDF5-support installation...")

    def shutdown(self) -> None:
        """Cancel local conversion safely when the plugin is unloaded."""
        if self.current_task is not None:
            self.current_task.cancel()
        if self.hdf5_install_task is not None:
            self.hdf5_install_task.cancel()
        self.hide()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.current_task is not None or self.hdf5_install_task is not None:
            QMessageBox.information(
                self,
                "HDF5 Converter",
                "Cancel the running conversion or installation before "
                "closing this window.",
            )
            event.ignore()
            return
        event.accept()
