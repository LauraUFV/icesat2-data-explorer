from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsProviderRegistry,
    QgsVectorLayer,
)

from .ui_assets import (
    apply_dialog_theme,
    create_dialog_header,
    icon,
    set_button_icon,
)
from .model_tide_task import (
    MODEL_DISTRIBUTION,
    MODEL_ID,
    ModelTideComputeTask,
    TideModelDownloadTask,
    TideSupportInstallTask,
    engine_environment_exists,
    engine_health,
    engine_installed,
    model_files_present,
    models_directory,
    support_root,
    venv_python,
)


class ModelTideDialog(QDialog):
    """
    User interface for the managed GOT4.10c tide workflow.
    """

    REQUIRED_FIELDS = {
        "longitude",
        "latitude",
        "time_ns",
        "depth",
    }

    OUTPUT_LAYER_NAME = (
        "atl24_bathymetry_model_tide"
    )

    def __init__(
        self,
        iface,
        parent=None,
    ):
        super().__init__(
            parent or iface.mainWindow()
        )

        self.iface = iface
        self.current_task = None

        self.setWindowTitle(
            "ATL24 — Add Model Tide Values"
        )
        self.setWindowIcon(icon("tide.svg"))
        self.setMinimumWidth(740)
        apply_dialog_theme(self)

        self.layer_combo = QComboBox()

        self.engine_status_label = QLabel("—")
        self.engine_status_label.setWordWrap(True)

        self.model_status_label = QLabel("—")
        self.model_status_label.setWordWrap(True)

        self.storage_label = QLabel(
            str(support_root())
        )
        self.storage_label.setWordWrap(True)
        self.storage_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        self.model_label = QLabel(
            f"{MODEL_DISTRIBUTION} ({MODEL_ID})"
        )

        self.method_combo = QComboBox()
        self.method_combo.addItem(
            "Linear",
            "linear",
        )
        self.method_combo.addItem(
            "Nearest",
            "nearest",
        )

        self.extrapolate_check = QCheckBox(
            "Allow spatial extrapolation"
        )
        self.extrapolate_check.setChecked(
            False
        )

        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(
            5000,
            200000,
        )
        self.chunk_spin.setSingleStep(
            10000
        )
        self.chunk_spin.setValue(
            50000
        )
        self.chunk_spin.setSuffix(
            " photons"
        )

        self.output_label = QLabel("—")
        self.output_label.setWordWrap(True)
        self.output_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        self.install_button = QPushButton(
            "Install tide support"
        )
        self.download_button = QPushButton(
            "Download GOT4.10c"
        )
        self.check_button = QPushButton(
            "Check status"
        )
        self.open_storage_button = QPushButton(
            "Open support folder"
        )
        self.refresh_layers_button = QPushButton(
            "Refresh layers"
        )
        self.output_button = QPushButton(
            "Select output GeoPackage"
        )
        self.compute_button = QPushButton(
            "Add model tide values"
        )
        self.cancel_button = QPushButton(
            "Cancel"
        )
        self.close_button = QPushButton(
            "Close"
        )

        self.cancel_button.setEnabled(False)

        set_button_icon(self.install_button, "refresh.svg")
        set_button_icon(self.download_button, "data_explorer.svg")
        set_button_icon(self.check_button, "refresh.svg")
        set_button_icon(self.open_storage_button, "folder.svg")
        set_button_icon(self.refresh_layers_button, "refresh.svg")
        set_button_icon(self.output_button, "folder.svg")
        set_button_icon(self.compute_button, "tide.svg")
        set_button_icon(self.close_button, "close.svg")
        self.compute_button.setProperty("primary", True)

        self.status_label = QLabel(
            "The tide engine and model are managed automatically."
        )
        self.status_label.setWordWrap(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(
            0,
            100,
        )
        self.progress_bar.setValue(
            0
        )

        self._build_layout()
        self._connect_signals()

        self.refresh_layers()
        self.refresh_support_status()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)

        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(
            create_dialog_header(
                "Model Tide Values",
                "Evaluate GOT4.10c for each ATL24 photon coordinate and UTC timestamp.",
                "tide.svg",
            )
        )

        description = QLabel(
            "A new GeoPackage and an HTML report are created. "
            "The original ATL24 depth field is preserved, and "
            "depth_tide_corrected_m is calculated as "
            "depth - tide_ocean_model_m."
        )
        description.setWordWrap(True)
        description.setProperty("muted", True)
        layout.addWidget(description)

        form = QFormLayout()
        form.addRow(
            "ATL24 layer:",
            self.layer_combo,
        )
        form.addRow(
            "Tide engine:",
            self.engine_status_label,
        )
        form.addRow(
            "Tide model:",
            self.model_label,
        )
        form.addRow(
            "Model status:",
            self.model_status_label,
        )
        form.addRow(
            "Managed storage:",
            self.storage_label,
        )
        form.addRow(
            "Interpolation:",
            self.method_combo,
        )
        form.addRow(
            "",
            self.extrapolate_check,
        )
        form.addRow(
            "Processing chunk:",
            self.chunk_spin,
        )
        form.addRow(
            "Output:",
            self.output_label,
        )
        layout.addLayout(form)

        support_buttons = QHBoxLayout()
        support_buttons.addWidget(
            self.install_button
        )
        support_buttons.addWidget(
            self.download_button
        )
        support_buttons.addWidget(
            self.check_button
        )
        support_buttons.addWidget(
            self.open_storage_button
        )
        layout.addLayout(
            support_buttons
        )

        layer_buttons = QHBoxLayout()
        layer_buttons.addWidget(
            self.refresh_layers_button
        )
        layer_buttons.addWidget(
            self.output_button
        )
        layout.addLayout(
            layer_buttons
        )

        layout.addWidget(
            self.status_label
        )
        layout.addWidget(
            self.progress_bar
        )

        bottom = QHBoxLayout()
        bottom.addWidget(
            self.compute_button
        )
        bottom.addWidget(
            self.cancel_button
        )
        bottom.addStretch()
        bottom.addWidget(
            self.close_button
        )
        layout.addLayout(bottom)

    def _connect_signals(self) -> None:
        self.install_button.clicked.connect(
            self.install_support
        )
        self.download_button.clicked.connect(
            self.download_model
        )
        self.check_button.clicked.connect(
            self.refresh_support_status
        )
        self.open_storage_button.clicked.connect(
            self.open_storage
        )
        self.refresh_layers_button.clicked.connect(
            self.refresh_layers
        )
        self.output_button.clicked.connect(
            self.select_output
        )
        self.compute_button.clicked.connect(
            self.start_compute
        )
        self.cancel_button.clicked.connect(
            self.cancel_task
        )
        self.close_button.clicked.connect(
            self.close
        )
        self.layer_combo.currentIndexChanged.connect(
            self._layer_changed
        )

    @classmethod
    def missing_fields(
        cls,
        layer,
    ) -> list[str]:
        if not isinstance(
            layer,
            QgsVectorLayer,
        ):
            return sorted(
                cls.REQUIRED_FIELDS
            )

        fields = {
            field.name()
            for field in layer.fields()
        }

        return sorted(
            cls.REQUIRED_FIELDS.difference(
                fields
            )
        )

    def refresh_layers(self) -> None:
        previous = self.layer_combo.currentData()

        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()

        layers = [
            layer
            for layer in (
                QgsProject.instance()
                .mapLayers()
                .values()
            )
            if isinstance(
                layer,
                QgsVectorLayer,
            )
        ]

        layers.sort(
            key=lambda layer: layer.name().lower()
        )

        for layer in layers:
            missing = self.missing_fields(
                layer
            )

            label = (
                f"{layer.name()} — ready"
                if not missing
                else (
                    f"{layer.name()} — missing: "
                    + ", ".join(missing)
                )
            )

            self.layer_combo.addItem(
                label,
                layer.id(),
            )

        active = self.iface.activeLayer()
        target = -1

        for index in range(
            self.layer_combo.count()
        ):
            layer_id = self.layer_combo.itemData(
                index
            )

            if (
                isinstance(active, QgsVectorLayer)
                and active.id() == layer_id
            ):
                target = index
                break

            if previous == layer_id:
                target = index

        if target >= 0:
            self.layer_combo.setCurrentIndex(
                target
            )

        self.layer_combo.blockSignals(False)

        if self.current_task is None:
            self.progress_bar.setValue(0)

        if self.layer_combo.count() == 0:
            self.output_label.setText("—")
            self.status_label.setText(
                "No vector layer is loaded."
            )
            self._update_buttons()
            return

        self._layer_changed()

    def selected_layer(
        self,
    ) -> QgsVectorLayer | None:
        layer = QgsProject.instance().mapLayer(
            self.layer_combo.currentData()
        )

        if isinstance(
            layer,
            QgsVectorLayer,
        ):
            return layer

        return None

    @staticmethod
    def decode_source(
        layer: QgsVectorLayer,
    ) -> tuple[Path, str]:
        decoded = (
            QgsProviderRegistry.instance()
            .decodeUri(
                layer.providerType(),
                layer.source(),
            )
        )

        path_value = (
            decoded.get("path")
            or decoded.get("database")
        )

        layer_name = (
            decoded.get("layerName")
            or decoded.get("layername")
        )

        if not path_value:
            path_value = layer.source().split(
                "|",
                1,
            )[0]

        if not layer_name:
            for part in layer.source().split("|")[1:]:
                if part.lower().startswith(
                    "layername="
                ):
                    layer_name = part.split(
                        "=",
                        1,
                    )[1]
                    break

        if not path_value or not layer_name:
            raise ValueError(
                "The GeoPackage path or layer name "
                "could not be determined."
            )

        path = Path(
            str(path_value)
        ).expanduser().resolve()

        if path.suffix.lower() != ".gpkg":
            raise ValueError(
                "The source ATL24 layer must be "
                "stored in a GeoPackage."
            )

        return path, str(layer_name)

    def _layer_changed(
        self,
        _index=None,
    ) -> None:
        layer = self.selected_layer()

        if layer is None:
            self.output_label.setText("—")
            self._update_buttons()
            return

        missing = self.missing_fields(
            layer
        )

        if missing:
            self.output_label.setText("—")
            self.status_label.setText(
                "Selected layer is missing: "
                + ", ".join(missing)
            )
            self._update_buttons()
            return

        try:
            source_path, _ = self.decode_source(
                layer
            )

            output = source_path.with_name(
                source_path.stem
                + "_model_tide.gpkg"
            )

            self.output_label.setText(
                str(output)
            )

            self.status_label.setText(
                "Layer ready. The source GeoPackage "
                "will not be modified."
            )
        except Exception as error:
            self.output_label.setText("—")
            self.status_label.setText(
                f"{type(error).__name__}: {error}"
            )

        self._update_buttons()

    def refresh_support_status(self) -> None:
        engine_state, engine_details = engine_health()
        engine_ready = engine_state == "ready"
        model_ready = model_files_present()

        if engine_state == "ready":
            self.engine_status_label.setText(
                "Installed in isolated environment"
            )
            self.engine_status_label.setToolTip(
                engine_details
            )
            self.install_button.setText(
                "Repair tide support"
            )
        elif engine_state == "broken":
            self.engine_status_label.setText(
                "Repair required — linked QGIS Python is unavailable"
            )
            self.engine_status_label.setToolTip(
                engine_details
            )
            self.install_button.setText(
                "Repair tide support"
            )
        else:
            self.engine_status_label.setText(
                "Not installed"
            )
            self.engine_status_label.setToolTip(
                engine_details
            )
            self.install_button.setText(
                "Install tide support"
            )

        if model_ready:
            self.model_status_label.setText(
                "Installed — local files verified"
            )
        else:
            self.model_status_label.setText(
                "Not installed"
            )

        self.storage_label.setText(
            str(support_root())
        )

        self._update_buttons()

    def _update_buttons(self) -> None:
        running = (
            self.current_task is not None
        )

        engine_ready = engine_installed()
        model_ready = model_files_present()

        layer = self.selected_layer()

        layer_ready = (
            layer is not None
            and not self.missing_fields(layer)
            and self.output_label.text() != "—"
        )

        # Keep the button available after installation so the
        # isolated environment can be repaired when an optional binary
        # dependency such as h5py is missing.
        self.install_button.setEnabled(
            not running
        )

        self.download_button.setEnabled(
            not running
            and engine_ready
            and not model_ready
        )

        self.check_button.setEnabled(
            not running
        )
        self.open_storage_button.setEnabled(
            not running
        )
        self.refresh_layers_button.setEnabled(
            not running
        )
        self.output_button.setEnabled(
            not running
            and layer_ready
        )

        self.layer_combo.setEnabled(
            not running
        )
        self.method_combo.setEnabled(
            not running
        )
        self.extrapolate_check.setEnabled(
            not running
        )
        self.chunk_spin.setEnabled(
            not running
        )

        self.compute_button.setEnabled(
            not running
            and engine_ready
            and model_ready
            and layer_ready
        )

        self.cancel_button.setEnabled(
            running
        )
        self.close_button.setEnabled(
            not running
        )

    def install_support(self) -> None:
        if self.current_task is not None:
            return

        repairing = engine_environment_exists()

        title = (
            "Repair Tide Support"
            if repairing
            else "Install Tide Support"
        )

        message = (
            "The plugin will repair the isolated tide "
            "environment and install the required pyTMD, "
            "h5py, h5netcdf and Dask packages.\n\n"
            "The GOT4.10c model files will not be deleted.\n\n"
            "No terminal commands are required.\n\n"
            "Continue?"
            if repairing
            else
            "The plugin will create an isolated Python "
            "environment and install pyTMD, h5py, "
            "h5netcdf and Dask automatically.\n\n"
            "No terminal commands are required.\n\n"
            "Continue?"
        )

        response = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.Yes,
        )

        if response != QMessageBox.Yes:
            return

        task = TideSupportInstallTask()
        self._start_task(
            task,
            (
                "Repairing the isolated tide engine..."
                if engine_environment_exists()
                else "Installing the isolated tide engine..."
            ),
            self._support_completed,
        )

    def download_model(self) -> None:
        if self.current_task is not None:
            return

        response = QMessageBox.question(
            self,
            "Download GOT4.10c",
            "The plugin will download the GOT4.10c "
            "NetCDF model from NASA GSFC to its managed "
            "local storage. This is normally required "
            "only once.\n\nContinue?",
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.Yes,
        )

        if response != QMessageBox.Yes:
            return

        task = TideModelDownloadTask()
        self._start_task(
            task,
            "Downloading and verifying GOT4.10c...",
            self._model_completed,
        )

    def select_output(self) -> None:
        current = self.output_label.text()

        if current == "—":
            current = "ATL24_model_tide.gpkg"

        output, _ = QFileDialog.getSaveFileName(
            self,
            "Select output GeoPackage",
            current,
            "GeoPackage (*.gpkg)",
        )

        if not output:
            return

        if not output.lower().endswith(
            ".gpkg"
        ):
            output += ".gpkg"

        self.output_label.setText(output)
        self._update_buttons()

    def start_compute(self) -> None:
        if self.current_task is not None:
            return

        layer = self.selected_layer()

        if layer is None:
            self._show_error(
                "Select an ATL24 layer."
            )
            return

        missing = self.missing_fields(
            layer
        )

        if missing:
            self._show_error(
                "The selected layer is missing: "
                + ", ".join(missing)
            )
            return

        if layer.isEditable():
            self._show_error(
                "Save or discard layer edits before "
                "running the tide tool."
            )
            return

        try:
            source_path, source_table = (
                self.decode_source(layer)
            )

            output_path = Path(
                self.output_label.text()
            ).expanduser().resolve()

            if output_path == source_path:
                raise ValueError(
                    "Choose a different output file."
                )

            task = ModelTideComputeTask(
                source_path=str(source_path),
                source_table=source_table,
                output_path=str(output_path),
                output_table=self.OUTPUT_LAYER_NAME,
                method=str(
                    self.method_combo.currentData()
                ),
                extrapolate=(
                    self.extrapolate_check
                    .isChecked()
                ),
                chunk_size=(
                    self.chunk_spin.value()
                ),
            )

            self._start_task(
                task,
                "Computing GOT4.10c values...",
                self._compute_completed,
            )

        except Exception as error:
            self._show_error(
                f"{type(error).__name__}: {error}"
            )

    def _start_task(
        self,
        task,
        message: str,
        completed_callback,
    ) -> None:
        self.current_task = task

        task.progressChanged.connect(
            lambda value: (
                self.progress_bar.setValue(
                    int(round(value))
                )
            )
        )
        task.taskCompleted.connect(
            completed_callback
        )
        task.taskTerminated.connect(
            self._task_terminated
        )

        self.progress_bar.setValue(0)
        self.status_label.setText(message)
        self._update_buttons()

        QgsApplication.taskManager().addTask(
            task
        )

    def _support_completed(self) -> None:
        self.current_task = None
        self.progress_bar.setValue(100)
        self.refresh_support_status()

        model_ready = model_files_present()

        if model_ready:
            self.status_label.setText(
                "Tide support repaired. "
                "GOT4.10c remains installed."
            )

            completion_message = (
                "The isolated tide engine was repaired "
                "successfully.\n\n"
                "pyTMD, h5py, h5netcdf and Dask are available.\n\n"
                "GOT4.10c remains installed. You can now "
                "click Add model tide values."
            )
        else:
            self.status_label.setText(
                "Tide support installed. "
                "Download GOT4.10c next."
            )

            completion_message = (
                "The isolated tide engine was installed "
                "successfully.\n\n"
                "Next, click Download GOT4.10c."
            )

        QMessageBox.information(
            self,
            "Tide Support",
            completion_message,
        )

    def _model_completed(self) -> None:
        self.current_task = None
        self.progress_bar.setValue(100)
        self.refresh_support_status()

        self.status_label.setText(
            "GOT4.10c downloaded and verified."
        )

        QMessageBox.information(
            self,
            "GOT4.10c",
            "The tide model was downloaded and "
            "verified successfully.\n\n"
            "The model can now be reused offline.",
        )

    def _compute_completed(self) -> None:
        task = self.current_task
        self.current_task = None
        self.progress_bar.setValue(100)
        self._update_buttons()

        if not isinstance(
            task,
            ModelTideComputeTask,
        ):
            return

        try:
            uri = (
                f"{Path(task.output_path).as_posix()}"
                f"|layername={task.source_table}"
            )

            output_layer = QgsVectorLayer(
                uri,
                "ATL24 Bathymetry — Model Tide",
                "ogr",
            )

            if not output_layer.isValid():
                raise RuntimeError(
                    "The output was created, but QGIS "
                    "could not load the layer."
                )

            QgsProject.instance().addMapLayer(
                output_layer
            )

            self.iface.setActiveLayer(
                output_layer
            )

            self.iface.mapCanvas().setExtent(
                output_layer.extent()
            )
            self.iface.mapCanvas().refresh()

            self.status_label.setText(
                f"Completed: {task.valid_records:,} "
                "valid tide values and "
                f"{task.corrected_depth_records:,} "
                "tide-corrected depths. "
                f"Report: {Path(task.report_path).name}"
            )

            QMessageBox.information(
                self,
                "Model Tide Values",
                "Model tide processing completed.\n\n"
                f"ATL24 photons: {task.total_records:,}\n"
                f"Valid tide values: {task.valid_records:,}\n"
                f"Invalid/NULL: {task.invalid_records:,}\n"
                f"Tide-corrected depths: "
                f"{task.corrected_depth_records:,}\n\n"
                "Derived field:\n"
                "depth_tide_corrected_m = "
                "depth - tide_ocean_model_m\n\n"
                "Report exported to:\n"
                f"{task.report_path}\n\n"
                "The original depth field was not modified. "
                "The derived value is referenced to the modeled "
                "mean tide level and is not a chart-datum reduction.",
            )

        except Exception as error:
            self._show_error(
                f"{type(error).__name__}: {error}"
            )

    def _task_terminated(self) -> None:
        task = self.current_task
        self.current_task = None
        self._update_buttons()

        if task is None:
            return

        if task.isCanceled():
            self.progress_bar.setValue(0)
            self.status_label.setText(
                "Task cancelled."
            )
            return

        self.status_label.setText(
            "Task failed."
        )

        message = (
            getattr(
                task,
                "error_message",
                None,
            )
            or "Unknown task error."
        )

        technical = getattr(
            task,
            "error_traceback",
            None,
        )

        if technical:
            message += (
                "\n\nTechnical details:\n"
                + technical
            )

        self._show_error(message)

    def cancel_task(self) -> None:
        if self.current_task is None:
            return

        self.current_task.cancel()
        self.status_label.setText(
            "Cancelling..."
        )

    def open_storage(self) -> None:
        support_root().mkdir(
            parents=True,
            exist_ok=True,
        )

        QDesktopServices.openUrl(
            QUrl.fromLocalFile(
                str(support_root())
            )
        )

    def closeEvent(
        self,
        event,
    ) -> None:
        if self.current_task is not None:
            QMessageBox.warning(
                self,
                "Model Tide Values",
                "Cancel or wait for the current task "
                "before closing this window.",
            )
            event.ignore()
            return

        super().closeEvent(event)

    def _show_error(
        self,
        message: str,
    ) -> None:
        QMessageBox.critical(
            self,
            "Model Tide Values",
            message,
        )
