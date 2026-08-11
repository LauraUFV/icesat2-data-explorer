from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import numpy as np

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)

from matplotlib.figure import Figure
from matplotlib.widgets import RectangleSelector

from .field_definitions import get_field_definition
from .ui_assets import (
    apply_dialog_theme,
    create_dialog_header,
    icon,
    set_button_icon,
)

try:
    from matplotlib.backends.backend_qtagg import (
        FigureCanvasQTAgg as FigureCanvas,
        NavigationToolbar2QT as NavigationToolbar,
    )
except ImportError:
    from matplotlib.backends.backend_qt5agg import (
        FigureCanvasQTAgg as FigureCanvas,
        NavigationToolbar2QT as NavigationToolbar,
    )


class ICESat2ProfileDialog(QDialog):
    """
    Optimized interactive profile viewer for ATL24, ATL08, ATL03 and ATL13.

    ATL24:
        X = latitude
        Y = depth

    ATL08:
        X = latitude
        Y = h_te_median

    ATL13:
        X = latitude
        Y = ht_ortho

    Performance strategy:
        - The graph is rebuilt only when Create profile is clicked.
        - Only required attributes are read.
        - Feature geometries are not read while building the graph.
        - NumPy arrays are used for filtering and selection.
        - The display is limited to a user-defined maximum.
        - The full filtered dataset is preserved for rectangle selection.
    """

    ALL_VALUE = "<All>"

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())

        self.iface = iface
        self.layer: QgsVectorLayer | None = None
        self.product: str | None = None
        self.x_field: str | None = "latitude"
        self.y_field: str | None = None

        self.full_fids = np.array([], dtype=np.int64)
        self.full_lon = np.array([], dtype=float)
        self.full_lat = np.array([], dtype=float)
        self.full_x = np.array([], dtype=float)
        self.full_y = np.array([], dtype=float)

        self.display_fids = np.array([], dtype=np.int64)
        self.display_x = np.array([], dtype=float)
        self.display_y = np.array([], dtype=float)

        # Session-only, non-destructive exclusions. The source layer and
        # GeoPackage are not modified.
        self.rejected_fids: set[int] = set()

        self._updating_layer_selection = False

        self.scatter = None
        self.selected_scatter = None
        self.rectangle_selector = None

        self.setWindowTitle("ICESat-2 Interactive Profile")
        self.setWindowIcon(icon("profile.svg"))
        self.resize(1000, 700)
        apply_dialog_theme(self)

        self.layer_combo = QComboBox()
        self.pass_combo = QComboBox()
        self.rgt_combo = QComboBox()
        self.cycle_combo = QComboBox()
        self.track_combo = QComboBox()
        self.x_axis_combo = QComboBox()
        self.y_axis_combo = QComboBox()

        self.acquisition_date_label = QLabel("—")
        self.acquisition_date_label.setWordWrap(True)

        self.pass_summary_label = QLabel(
            "Available RGT, cycle and beam combinations will appear "
            "after a layer is selected."
        )
        self.pass_summary_label.setWordWrap(True)
        self.pass_summary_label.setProperty(
            "muted",
            True,
        )

        self._filter_combinations: list[
            dict[str, Any]
        ] = []
        self._updating_filter_controls = False

        self.maximum_points_spin = QSpinBox()
        self.maximum_points_spin.setRange(1000, 100000)
        self.maximum_points_spin.setSingleStep(5000)
        self.maximum_points_spin.setValue(20000)
        self.maximum_points_spin.setSuffix(" points")

        self.product_label = QLabel("—")

        self.status_label = QLabel(
            "Select an ATL24, ATL08, ATL03 or ATL13 layer."
        )
        self.status_label.setWordWrap(True)

        self.refresh_layers_button = QPushButton(
            "Refresh layers"
        )
        self.create_profile_button = QPushButton(
            "Create profile"
        )
        self.clear_selection_button = QPushButton(
            "Clear selection"
        )
        self.zoom_profile_button = QPushButton(
            "Zoom to profile extent"
        )
        self.zoom_selection_button = QPushButton(
            "Zoom to selected points"
        )
        self.reject_selection_button = QPushButton(
            "Exclude selected from profile"
        )
        self.restore_rejected_button = QPushButton(
            "Restore excluded points"
        )
        self.close_button = QPushButton("Close")

        set_button_icon(self.refresh_layers_button, "refresh.svg")
        set_button_icon(self.create_profile_button, "profile.svg")
        set_button_icon(self.zoom_profile_button, "zoom.svg")
        set_button_icon(self.zoom_selection_button, "zoom.svg")
        set_button_icon(self.close_button, "close.svg")
        self.create_profile_button.setProperty("primary", True)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(
            self.canvas,
            self,
        )
        self.axes = self.figure.add_subplot(111)

        self._build_layout()
        self._connect_signals()
        self.refresh_layers()

    def _build_layout(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)
        main_layout.addWidget(
            create_dialog_header(
                "Interactive Profile",
                "Filter, inspect, select and temporarily exclude ICESat-2 observations.",
                "profile.svg",
            )
        )

        form = QFormLayout()
        form.addRow("ICESat-2 layer:", self.layer_combo)
        form.addRow("Product:", self.product_label)
        form.addRow(
            "Available pass / beam:",
            self.pass_combo,
        )
        form.addRow("", self.pass_summary_label)
        form.addRow("Acquisition date:", self.acquisition_date_label)
        form.addRow("RGT:", self.rgt_combo)
        form.addRow("Cycle:", self.cycle_combo)
        form.addRow("Beam (gt):", self.track_combo)
        form.addRow("X axis:", self.x_axis_combo)
        form.addRow("Y axis:", self.y_axis_combo)
        form.addRow(
            "Maximum displayed:",
            self.maximum_points_spin,
        )
        main_layout.addLayout(form)

        top_buttons = QHBoxLayout()
        top_buttons.addWidget(self.refresh_layers_button)
        top_buttons.addWidget(self.create_profile_button)
        top_buttons.addStretch()
        main_layout.addLayout(top_buttons)

        main_layout.addWidget(self.toolbar)
        main_layout.addWidget(self.canvas, 1)

        bottom_buttons = QHBoxLayout()
        bottom_buttons.addWidget(self.clear_selection_button)
        bottom_buttons.addWidget(self.zoom_profile_button)
        bottom_buttons.addWidget(self.zoom_selection_button)
        bottom_buttons.addWidget(self.reject_selection_button)
        bottom_buttons.addWidget(self.restore_rejected_button)
        bottom_buttons.addStretch()
        bottom_buttons.addWidget(self.close_button)
        main_layout.addLayout(bottom_buttons)

        main_layout.addWidget(self.status_label)

    def _connect_signals(self) -> None:
        self.refresh_layers_button.clicked.connect(
            self.refresh_layers
        )
        self.create_profile_button.clicked.connect(
            self.create_profile
        )
        self.clear_selection_button.clicked.connect(
            self.clear_selection
        )
        self.zoom_profile_button.clicked.connect(
            self.zoom_to_profile_extent
        )
        self.zoom_selection_button.clicked.connect(
            self.zoom_to_selected_points
        )
        self.reject_selection_button.clicked.connect(
            self.exclude_selected_from_profile
        )
        self.restore_rejected_button.clicked.connect(
            self.restore_excluded_points
        )
        self.close_button.clicked.connect(self.close)

        self.layer_combo.currentIndexChanged.connect(
            self._layer_changed
        )

        # Keep only valid RGT-cycle-beam combinations visible. The graph
        # itself is still rebuilt only after Create profile is clicked.
        self.pass_combo.currentIndexChanged.connect(
            self._pass_combination_changed
        )
        self.rgt_combo.currentIndexChanged.connect(
            self._individual_filter_changed
        )
        self.cycle_combo.currentIndexChanged.connect(
            self._individual_filter_changed
        )
        self.track_combo.currentIndexChanged.connect(
            self._individual_filter_changed
        )
        self.x_axis_combo.currentIndexChanged.connect(
            self._axis_changed
        )
        self.y_axis_combo.currentIndexChanged.connect(
            self._axis_changed
        )
        self.maximum_points_spin.valueChanged.connect(
            self._mark_profile_stale
        )

        self.canvas.mpl_connect(
            "pick_event",
            self._point_picked,
        )

    @staticmethod
    def _field_names(layer: QgsVectorLayer) -> set[str]:
        return {
            field.name()
            for field in layer.fields()
        }

    @classmethod
    def identify_product(
        cls,
        layer: QgsVectorLayer,
    ) -> tuple[str, str] | None:
        fields = cls._field_names(layer)

        if "latitude" not in fields or "longitude" not in fields:
            return None

        if "depth" in fields:
            return "ATL24", "depth"

        if "h_te_median" in fields:
            return "ATL08", "h_te_median"

        if "height" in fields and "ph_index" in fields:
            return "ATL03", "height"

        if "ht_ortho" in fields:
            return "ATL13", "ht_ortho"

        return None

    def refresh_layers(self) -> None:
        previous_layer_id = (
            self.layer_combo.currentData()
        )

        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()

        eligible_layers = []

        for layer in (
            QgsProject.instance()
            .mapLayers()
            .values()
        ):
            if not isinstance(
                layer,
                QgsVectorLayer,
            ):
                continue

            if (
                layer.geometryType()
                != Qgis.GeometryType.Point
            ):
                continue

            identification = self.identify_product(
                layer
            )

            if identification is None:
                continue

            eligible_layers.append(layer)

        eligible_layers.sort(
            key=lambda item: item.name().lower()
        )

        for layer in eligible_layers:
            product, _ = self.identify_product(layer)

            self.layer_combo.addItem(
                f"{layer.name()} ({product})",
                layer.id(),
            )

        active_layer = self.iface.activeLayer()
        target_index = -1

        for index in range(
            self.layer_combo.count()
        ):
            layer_id = self.layer_combo.itemData(
                index
            )

            if (
                isinstance(
                    active_layer,
                    QgsVectorLayer,
                )
                and active_layer.id() == layer_id
            ):
                target_index = index
                break

            if (
                previous_layer_id
                and previous_layer_id == layer_id
            ):
                target_index = index

        if target_index >= 0:
            self.layer_combo.setCurrentIndex(
                target_index
            )

        self.layer_combo.blockSignals(False)

        if self.layer_combo.count() == 0:
            self._disconnect_layer()
            self.product_label.setText("—")
            self.acquisition_date_label.setText("—")
            self.x_axis_combo.clear()
            self.y_axis_combo.clear()
            self.create_profile_button.setEnabled(
                False
            )
            self.status_label.setText(
                "No supported layer was found. "
                "Load an ATL24 point layer containing "
                "'latitude' and 'depth', an ATL08 point layer "
                "containing 'latitude' and 'h_te_median', an ATL03 "
                "point layer containing 'latitude', 'height' and "
                "'ph_index', or an ATL13 point layer containing "
                "'latitude' and 'ht_ortho'."
            )
            self._clear_plot()
            return

        self.create_profile_button.setEnabled(True)
        self._layer_changed()

    def _disconnect_layer(self) -> None:
        if self.layer is None:
            return

        try:
            self.layer.selectionChanged.disconnect(
                self._layer_selection_changed
            )
        except (TypeError, RuntimeError):
            pass

        self.layer = None

    def _layer_changed(
        self,
        _index: int | None = None,
    ) -> None:
        self._disconnect_layer()

        layer_id = self.layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(
            layer_id
        )

        if not isinstance(layer, QgsVectorLayer):
            return

        identification = self.identify_product(
            layer
        )

        if identification is None:
            return

        self.layer = layer
        self.product, default_y_field = (
            identification
        )
        self.rejected_fids.clear()

        self.product_label.setText(
            self.product
        )

        self._populate_axis_combos(
            default_y_field=default_y_field
        )

        self.layer.selectionChanged.connect(
            self._layer_selection_changed
        )

        self._populate_filter_combos()
        self._clear_plot()

        self.status_label.setText(
            "Choose the filters and click "
            "Create profile."
        )

    @staticmethod
    def _field_is_numeric(
        field,
    ) -> bool:
        try:
            return bool(field.isNumeric())
        except Exception:
            type_name = str(field.typeName()).strip().lower()
            return any(
                token in type_name
                for token in (
                    "int", "integer", "real", "double", "float",
                    "numeric", "decimal",
                )
            )

    @staticmethod
    def _axis_friendly_name(
        field_name: str,
    ) -> str:
        names = {
            "latitude": "Latitude",
            "longitude": "Longitude",
            "x_atc": "Along-track distance",
            "y_atc": "Across-track distance",
            "depth": "Depth",
            "depth_tide_corrected_m": "Tide-reduced depth",
            "ellipse_h": "Ellipsoidal height",
            "ortho_h": "Orthometric height",
            "surface_h": "Water-surface height",
            "height": "Photon height",
            "height_ortho": "Orthometric photon height",
            "geoid": "Geoid height",
            "geoid_free2mean": "Geoid free-to-mean correction",
            "geoid_mean_tide": "Mean-tide geoid height",
            "tide_ocean": "ATL03 ocean tide",
            "tide_ocean_model_m": "Modeled ocean tide",
            "h_te_median": "Terrain elevation",
            "h_te_uncertainty": "Terrain uncertainty",
            "terrain_slope": "Terrain slope",
            "h_canopy": "Canopy height",
            "h_canopy_uncertainty": "Canopy uncertainty",
            "h_max_canopy": "Maximum canopy height",
            "h_min_canopy": "Minimum canopy height",
            "h_mean_canopy": "Mean canopy height",
            "canopy_openness": "Canopy openness",
            "ht_ortho": "Orthometric water-surface height",
            "ht_water_surf": "Water-surface height",
            "stdev_water_surf": "Water-surface standard deviation",
            "water_depth": "Water depth",
            "solar_elevation": "Solar elevation",
            "background_rate": "Background rate",
            "spacecraft_velocity": "Spacecraft velocity",
            "confidence": "Confidence",
            "sigma_thu": "Horizontal uncertainty",
            "sigma_tvu": "Vertical uncertainty",
        }
        return names.get(
            field_name,
            field_name.replace("_", " ").strip().title(),
        )

    def _axis_option_label(
        self,
        field_name: str,
    ) -> str:
        definition = get_field_definition(
            self.product or "", field_name
        )
        units = str(definition.get("units", "—") or "—")
        friendly = self._axis_friendly_name(field_name)
        if units in ("", "—", "See source documentation"):
            return f"{friendly} [{field_name}]"
        return f"{friendly} ({units}) [{field_name}]"

    def _numeric_axis_fields(self) -> list[str]:
        if self.layer is None:
            return []
        fields = [
            field.name()
            for field in self.layer.fields()
            if field.name() != "fid" and self._field_is_numeric(field)
        ]
        preferred = [
            "latitude", "longitude", "x_atc", "y_atc",
            "depth", "depth_tide_corrected_m",
            "height", "height_ortho", "h_te_median", "h_canopy",
            "ht_ortho", "water_depth", "surface_h", "ortho_h",
            "ellipse_h", "tide_ocean", "tide_ocean_model_m",
            "geoid", "geoid_mean_tide",
        ]
        rank = {name:index for index,name in enumerate(preferred)}
        return sorted(
            dict.fromkeys(fields),
            key=lambda name:(rank.get(name, len(preferred)), name.lower()),
        )

    def _set_axis_combo_value(
        self,
        combo: QComboBox,
        field_name: str | None,
    ) -> None:
        if not field_name:
            return
        for index in range(combo.count()):
            if str(combo.itemData(index)) == str(field_name):
                combo.setCurrentIndex(index)
                return

    def _populate_axis_combos(
        self,
        default_y_field: str,
    ) -> None:
        numeric_fields = self._numeric_axis_fields()
        self.x_axis_combo.blockSignals(True)
        self.y_axis_combo.blockSignals(True)
        try:
            self.x_axis_combo.clear()
            self.y_axis_combo.clear()
            for field_name in numeric_fields:
                label = self._axis_option_label(field_name)
                self.x_axis_combo.addItem(label, field_name)
                self.y_axis_combo.addItem(label, field_name)
            default_x = (
                "latitude" if "latitude" in numeric_fields
                else (numeric_fields[0] if numeric_fields else None)
            )
            default_y = (
                default_y_field if default_y_field in numeric_fields
                else (numeric_fields[0] if numeric_fields else None)
            )
            self._set_axis_combo_value(self.x_axis_combo, default_x)
            self._set_axis_combo_value(self.y_axis_combo, default_y)
            self.x_field = default_x
            self.y_field = default_y
            enabled = bool(numeric_fields)
            self.x_axis_combo.setEnabled(enabled)
            self.y_axis_combo.setEnabled(enabled)
        finally:
            self.x_axis_combo.blockSignals(False)
            self.y_axis_combo.blockSignals(False)

    def _axis_changed(self, _index: int) -> None:
        x_data = self.x_axis_combo.currentData()
        y_data = self.y_axis_combo.currentData()
        self.x_field = str(x_data) if x_data is not None else None
        self.y_field = str(y_data) if y_data is not None else None
        self._mark_profile_stale()

    @staticmethod
    def _observation_date(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "toPyDateTime"):
            try:
                return value.toPyDateTime().date().isoformat()
            except Exception:
                pass
        if hasattr(value, "date"):
            try:
                return value.date().isoformat()
            except Exception:
                pass
        text = str(value).strip()
        match = re.search(r"\d{4}-\d{2}-\d{2}", text)
        if match:
            return match.group(0)
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        absolute = abs(numeric)
        if absolute >= 1.0e17:
            seconds = numeric / 1.0e9
        elif absolute >= 1.0e14:
            seconds = numeric / 1.0e6
        elif absolute >= 1.0e11:
            seconds = numeric / 1.0e3
        else:
            seconds = numeric
        try:
            return datetime.fromtimestamp(
                seconds, tz=timezone.utc
            ).date().isoformat()
        except (OSError, OverflowError, ValueError):
            return None

    @staticmethod
    def _date_range_label(
        start_date: str | None,
        end_date: str | None,
    ) -> str:
        if not start_date:
            return "Date unavailable"
        if not end_date or start_date == end_date:
            return start_date
        return f"{start_date} to {end_date}"

    def _mark_profile_stale(
        self,
        _value=None,
    ) -> None:
        if self.layer is not None:
            self.status_label.setText(
                "Filters changed. Click Create profile "
                "to update the graph."
            )

    @staticmethod
    def _clean_filter_value(
        value: Any,
    ) -> Any:
        if value is None:
            return None

        text = str(value).strip()

        if not text:
            return None

        return value

    @staticmethod
    def _natural_filter_sort(
        value: Any,
    ) -> tuple[int, Any]:
        try:
            return (
                0,
                int(value),
            )
        except (TypeError, ValueError):
            return (
                1,
                str(value).lower(),
            )

    @staticmethod
    def _format_filter_value(
        field_name: str,
        value: Any,
    ) -> str:
        if value is None:
            return "—"

        try:
            integer_value = int(value)
        except (TypeError, ValueError):
            return str(value)

        if field_name == "rgt":
            return f"{integer_value:04d}"

        if field_name == "cycle":
            return f"{integer_value:02d}"

        return str(value)

    def _read_filter_combinations(self) -> None:
        self._filter_combinations = []

        if self.layer is None:
            return

        available_fields = self._field_names(self.layer)
        filter_fields = [
            field_name
            for field_name in ("rgt", "cycle", "gt", "time_ns")
            if field_name in available_fields
        ]

        if not any(
            field_name in available_fields
            for field_name in ("rgt", "cycle", "gt")
        ):
            return

        request = QgsFeatureRequest()
        request.setSubsetOfAttributes(filter_fields, self.layer.fields())
        request.setFlags(QgsFeatureRequest.NoGeometry)

        combinations: dict[
            tuple[Any, Any, Any], dict[str, Any]
        ] = {}

        for feature in self.layer.getFeatures(request):
            key = (
                self._clean_filter_value(feature["rgt"])
                if "rgt" in available_fields else None,
                self._clean_filter_value(feature["cycle"])
                if "cycle" in available_fields else None,
                self._clean_filter_value(feature["gt"])
                if "gt" in available_fields else None,
            )
            item = combinations.setdefault(
                key,
                {"count": 0, "date_start": None, "date_end": None},
            )
            item["count"] += 1

            if "time_ns" in available_fields:
                observation_date = self._observation_date(feature["time_ns"])
                if observation_date:
                    if (
                        item["date_start"] is None
                        or observation_date < item["date_start"]
                    ):
                        item["date_start"] = observation_date
                    if (
                        item["date_end"] is None
                        or observation_date > item["date_end"]
                    ):
                        item["date_end"] = observation_date

        sorted_items = sorted(
            combinations.items(),
            key=lambda item:(
                item[1].get("date_start") or "9999-99-99",
                self._natural_filter_sort(item[0][0]),
                self._natural_filter_sort(item[0][1]),
                self._natural_filter_sort(item[0][2]),
            ),
        )

        self._filter_combinations = [
            {
                "rgt": key[0],
                "cycle": key[1],
                "gt": key[2],
                "count": int(metadata["count"]),
                "date_start": metadata.get("date_start"),
                "date_end": metadata.get("date_end"),
            }
            for key, metadata in sorted_items
        ]

    def _populate_filter_combos(self) -> None:
        if self.layer is None:
            return

        self.status_label.setText(
            "Reading available RGT, cycle and beam combinations..."
        )

        self._read_filter_combinations()

        self._updating_filter_controls = True

        try:
            for combo in (
                self.pass_combo,
                self.rgt_combo,
                self.cycle_combo,
                self.track_combo,
            ):
                combo.blockSignals(True)

            self._populate_pass_combo()
            self._refresh_individual_filter_combos(
                preserve_values=False
            )

        finally:
            for combo in (
                self.pass_combo,
                self.rgt_combo,
                self.cycle_combo,
                self.track_combo,
            ):
                combo.blockSignals(False)

            self._updating_filter_controls = False

        self._update_pass_summary()

    def _populate_pass_combo(self) -> None:
        self.pass_combo.clear()

        total_records = sum(
            item["count"]
            for item in self._filter_combinations
        )

        self.pass_combo.addItem(
            (
                f"All valid combinations "
                f"({len(self._filter_combinations):,}; "
                f"{total_records:,} points)"
            ),
            None,
        )

        for item in self._filter_combinations:
            date_label = self._date_range_label(
                item.get("date_start"),
                item.get("date_end"),
            )
            label = (
                date_label
                + " · RGT "
                + self._format_filter_value("rgt", item["rgt"])
                + " · Cycle "
                + self._format_filter_value("cycle", item["cycle"])
                + " · "
                + self._format_filter_value("gt", item["gt"])
                + f" · {item['count']:,} points"
            )

            self.pass_combo.addItem(
                label,
                (
                    item["rgt"],
                    item["cycle"],
                    item["gt"],
                ),
            )

        self.pass_combo.setEnabled(
            bool(
                self._filter_combinations
            )
        )

    def _current_combo_value(
        self,
        combo: QComboBox,
    ) -> Any:
        if not combo.isEnabled():
            return None

        return combo.currentData()

    def _set_combo_to_value(
        self,
        combo: QComboBox,
        value: Any,
    ) -> None:
        target_index = 0

        for index in range(
            combo.count()
        ):
            if str(
                combo.itemData(index)
            ) == str(value):
                target_index = index
                break

        combo.setCurrentIndex(
            target_index
        )

    def _matching_combinations(
        self,
        *,
        rgt: Any = None,
        cycle: Any = None,
        gt: Any = None,
    ) -> list[dict[str, Any]]:
        matches = []

        for item in self._filter_combinations:
            if (
                rgt is not None
                and str(item["rgt"]) != str(rgt)
            ):
                continue

            if (
                cycle is not None
                and str(item["cycle"]) != str(cycle)
            ):
                continue

            if (
                gt is not None
                and str(item["gt"]) != str(gt)
            ):
                continue

            matches.append(item)

        return matches

    def _populate_cascading_combo(
        self,
        combo: QComboBox,
        field_name: str,
        combinations: list[dict[str, Any]],
        selected_value: Any,
    ) -> None:
        counts: Counter[Any] = Counter()

        for item in combinations:
            value = item[field_name]

            if value is not None:
                counts[value] += int(
                    item["count"]
                )

        combo.clear()
        combo.addItem(
            self.ALL_VALUE,
            None,
        )

        for value in sorted(
            counts,
            key=self._natural_filter_sort,
        ):
            combo.addItem(
                (
                    self._format_filter_value(
                        field_name,
                        value,
                    )
                    + f" ({counts[value]:,} points)"
                ),
                value,
            )

        combo.setEnabled(
            bool(counts)
        )
        self._set_combo_to_value(
            combo,
            selected_value,
        )

    def _refresh_individual_filter_combos(
        self,
        preserve_values: bool = True,
    ) -> None:
        previous_rgt = (
            self._current_combo_value(
                self.rgt_combo
            )
            if preserve_values
            else None
        )
        previous_cycle = (
            self._current_combo_value(
                self.cycle_combo
            )
            if preserve_values
            else None
        )
        previous_gt = (
            self._current_combo_value(
                self.track_combo
            )
            if preserve_values
            else None
        )

        self._populate_cascading_combo(
            self.rgt_combo,
            "rgt",
            self._matching_combinations(
                cycle=previous_cycle,
                gt=previous_gt,
            ),
            previous_rgt,
        )
        self._populate_cascading_combo(
            self.cycle_combo,
            "cycle",
            self._matching_combinations(
                rgt=previous_rgt,
                gt=previous_gt,
            ),
            previous_cycle,
        )
        self._populate_cascading_combo(
            self.track_combo,
            "gt",
            self._matching_combinations(
                rgt=previous_rgt,
                cycle=previous_cycle,
            ),
            previous_gt,
        )

    def _sync_pass_combo_from_filters(self) -> None:
        selected = (
            self._current_combo_value(
                self.rgt_combo
            ),
            self._current_combo_value(
                self.cycle_combo
            ),
            self._current_combo_value(
                self.track_combo
            ),
        )

        target_index = 0

        if all(
            value is not None
            for value in selected
        ):
            for index in range(
                1,
                self.pass_combo.count(),
            ):
                item_data = self.pass_combo.itemData(
                    index
                )

                if (
                    item_data is not None
                    and all(
                        str(item_data[position])
                        == str(selected[position])
                        for position in range(3)
                    )
                ):
                    target_index = index
                    break

        self.pass_combo.setCurrentIndex(
            target_index
        )

    def _update_pass_summary(self) -> None:
        matches = self._matching_combinations(
            rgt=self._current_combo_value(self.rgt_combo),
            cycle=self._current_combo_value(self.cycle_combo),
            gt=self._current_combo_value(self.track_combo),
        )
        matching_points = sum(item["count"] for item in matches)
        date_starts = [
            item.get("date_start")
            for item in matches
            if item.get("date_start")
        ]
        date_ends = [
            item.get("date_end")
            for item in matches
            if item.get("date_end")
        ]
        if date_starts:
            date_label = self._date_range_label(
                min(date_starts),
                max(date_ends or date_starts),
            )
        else:
            date_label = "Unavailable"
        self.acquisition_date_label.setText(date_label)
        self.pass_summary_label.setText(
            f"{len(self._filter_combinations):,} valid "
            "RGT-cycle-beam combinations in the layer. "
            f"Current filters match {len(matches):,} "
            f"combination(s) and {matching_points:,} point(s)."
        )

    def _pass_combination_changed(
        self,
        _index: int,
    ) -> None:
        if self._updating_filter_controls:
            return

        combination = self.pass_combo.currentData()

        self._updating_filter_controls = True

        try:
            for combo in (
                self.rgt_combo,
                self.cycle_combo,
                self.track_combo,
            ):
                combo.blockSignals(True)

            values = (
                (
                    None,
                    None,
                    None,
                )
                if combination is None
                else combination
            )

            self._set_combo_to_value(
                self.rgt_combo,
                values[0],
            )
            self._set_combo_to_value(
                self.cycle_combo,
                values[1],
            )
            self._set_combo_to_value(
                self.track_combo,
                values[2],
            )

            self._refresh_individual_filter_combos(
                preserve_values=True
            )

        finally:
            for combo in (
                self.rgt_combo,
                self.cycle_combo,
                self.track_combo,
            ):
                combo.blockSignals(False)

            self._updating_filter_controls = False

        self._update_pass_summary()
        self._mark_profile_stale()

    def _individual_filter_changed(
        self,
        _index: int,
    ) -> None:
        if self._updating_filter_controls:
            return

        self._updating_filter_controls = True

        try:
            for combo in (
                self.pass_combo,
                self.rgt_combo,
                self.cycle_combo,
                self.track_combo,
            ):
                combo.blockSignals(True)

            self._refresh_individual_filter_combos(
                preserve_values=True
            )
            self._sync_pass_combo_from_filters()

        finally:
            for combo in (
                self.pass_combo,
                self.rgt_combo,
                self.cycle_combo,
                self.track_combo,
            ):
                combo.blockSignals(False)

            self._updating_filter_controls = False

        self._update_pass_summary()
        self._mark_profile_stale()

    def _selected_filter_value(
        self,
        combo: QComboBox,
    ) -> Any:
        if not combo.isEnabled():
            return None

        return combo.currentData()

    def _feature_matches_filters(
        self,
        feature,
    ) -> bool:
        filter_values = {
            "rgt": self._selected_filter_value(
                self.rgt_combo
            ),
            "cycle": self._selected_filter_value(
                self.cycle_combo
            ),
            "gt": self._selected_filter_value(
                self.track_combo
            ),
        }

        for (
            field_name,
            selected_value,
        ) in filter_values.items():
            if selected_value is None:
                continue

            if (
                self.layer.fields().indexOf(
                    field_name
                )
                == -1
            ):
                continue

            if (
                str(feature[field_name])
                != str(selected_value)
            ):
                return False

        return True

    @staticmethod
    def _to_finite_float(
        value: Any,
    ) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number):
            return None

        return number

    def create_profile(self) -> None:
        if self.layer is None:
            return

        x_data = self.x_axis_combo.currentData()
        y_data = self.y_axis_combo.currentData()
        self.x_field = str(x_data) if x_data is not None else None
        self.y_field = str(y_data) if y_data is not None else None

        if self.x_field is None or self.y_field is None:
            self._show_information(
                "Select valid numeric fields for both profile axes."
            )
            return

        required_fields = [
            "longitude", "latitude", self.x_field, self.y_field
        ]
        for optional_field in ("rgt", "cycle", "gt"):
            if self.layer.fields().indexOf(optional_field) != -1:
                required_fields.append(optional_field)
        required_fields = list(dict.fromkeys(required_fields))

        request = QgsFeatureRequest()
        request.setSubsetOfAttributes(required_fields, self.layer.fields())
        request.setFlags(QgsFeatureRequest.NoGeometry)

        fids, longitude_values, latitude_values = [], [], []
        x_values, y_values = [], []

        self.create_profile_button.setEnabled(False)
        self.status_label.setText("Reading profile attributes...")
        try:
            for feature in self.layer.getFeatures(request):
                feature_id = int(feature.id())
                if feature_id in self.rejected_fids:
                    continue
                if not self._feature_matches_filters(feature):
                    continue
                longitude = self._to_finite_float(feature["longitude"])
                latitude = self._to_finite_float(feature["latitude"])
                x_value = self._to_finite_float(feature[self.x_field])
                y_value = self._to_finite_float(feature[self.y_field])
                if (
                    longitude is None or latitude is None
                    or x_value is None or y_value is None
                ):
                    continue
                fids.append(feature_id)
                longitude_values.append(longitude)
                latitude_values.append(latitude)
                x_values.append(x_value)
                y_values.append(y_value)
        finally:
            self.create_profile_button.setEnabled(True)

        if not fids:
            self.full_fids = np.array([], dtype=np.int64)
            self.full_lon = np.array([], dtype=float)
            self.full_lat = np.array([], dtype=float)
            self.full_x = np.array([], dtype=float)
            self.full_y = np.array([], dtype=float)
            self._draw_profile()
            return

        fids_array = np.asarray(fids, dtype=np.int64)
        longitude_array = np.asarray(longitude_values, dtype=float)
        latitude_array = np.asarray(latitude_values, dtype=float)
        x_array = np.asarray(x_values, dtype=float)
        y_array = np.asarray(y_values, dtype=float)
        order = np.argsort(x_array, kind="mergesort")
        self.full_fids = fids_array[order]
        self.full_lon = longitude_array[order]
        self.full_lat = latitude_array[order]
        self.full_x = x_array[order]
        self.full_y = y_array[order]
        self._update_display_sample()
        self._draw_profile()

    def _update_display_sample(self) -> None:
        """Build the plotting sample from the current full profile arrays."""
        total_points = len(self.full_fids)
        maximum_points = int(
            self.maximum_points_spin.value()
        )

        if total_points == 0:
            self.display_fids = np.array([], dtype=np.int64)
            self.display_x = np.array([], dtype=float)
            self.display_y = np.array([], dtype=float)
            return

        if total_points <= maximum_points:
            display_indices = np.arange(
                total_points,
                dtype=np.int64,
            )
        else:
            display_indices = np.linspace(
                0,
                total_points - 1,
                maximum_points,
                dtype=np.int64,
            )

        self.display_fids = self.full_fids[display_indices]
        self.display_x = self.full_x[display_indices]
        self.display_y = self.full_y[display_indices]

    def _draw_profile(self) -> None:
        self.axes.clear()

        if self.rectangle_selector is not None:
            try:
                self.rectangle_selector.set_active(
                    False
                )
                self.rectangle_selector.disconnect_events()
            except Exception:
                pass

            self.rectangle_selector = None

        if len(self.full_fids) == 0:
            self.scatter = None
            self.selected_scatter = None

            self.axes.set_title(
                "No valid profile points"
            )
            self.axes.set_xlabel(
                self._axis_label(self.x_field)
            )
            self.axes.set_ylabel(
                self._axis_label(self.y_field)
            )
            self.canvas.draw_idle()

            self.status_label.setText(
                "No valid points matched the "
                "current layer and filters."
            )
            return

        self.scatter = self.axes.scatter(
            self.display_x,
            self.display_y,
            s=8,
            picker=4,
            linewidths=0,
        )

        self.selected_scatter = (
            self.axes.scatter(
                [],
                [],
                s=36,
                facecolors="none",
                edgecolors="black",
                linewidths=1.0,
            )
        )

        self.axes.set_xlabel(
            self._axis_label(self.x_field)
        )
        self.axes.set_ylabel(
            self._axis_label(self.y_field)
        )
        self.axes.set_title(
            self._profile_title()
        )
        self.axes.grid(
            True,
            alpha=0.2,
        )

        if self._should_invert_y_axis():
            self.axes.invert_yaxis()

        self.figure.tight_layout()

        self.rectangle_selector = (
            RectangleSelector(
                self.axes,
                self._rectangle_selected,
                useblit=True,
                button=[1],
                minspanx=2,
                minspany=2,
                spancoords="pixels",
                interactive=False,
            )
        )

        self._update_selected_markers()
        self.canvas.draw_idle()

        total = len(self.full_fids)
        displayed = len(self.display_fids)

        if displayed < total:
            detail = (
                f"{total:,} valid points; "
                f"{displayed:,} displayed for performance."
            )
        else:
            detail = (
                f"{total:,} valid points displayed."
            )

        rejected_count = len(self.rejected_fids)

        self.status_label.setText(
            detail
            + f" Excluded in this session: {rejected_count:,}."
            + " Click a point or drag a rectangle "
            "to select features."
        )

    def _axis_label(
        self,
        field_name: str | None,
    ) -> str:
        if not field_name:
            return "Value"
        definition = get_field_definition(
            self.product or "", field_name
        )
        units = str(definition.get("units", "—") or "—")
        friendly = self._axis_friendly_name(field_name)
        if units in ("", "—", "See source documentation"):
            return friendly
        return f"{friendly} ({units})"

    def _should_invert_y_axis(self) -> bool:
        return self.y_field in {
            "depth",
            "water_depth",
            "depth_tide_corrected_m",
        }

    def _profile_title(self) -> str:
        layer_name = self.layer.name() if self.layer else "ICESat-2"
        x_name = self._axis_friendly_name(self.x_field or "x")
        y_name = self._axis_friendly_name(self.y_field or "y")
        filters = []
        for label, field_name, combo in (
            ("RGT", "rgt", self.rgt_combo),
            ("Cycle", "cycle", self.cycle_combo),
            ("Beam", "gt", self.track_combo),
        ):
            value = self._selected_filter_value(combo)
            if value is not None:
                filters.append(
                    label + " " + self._format_filter_value(
                        field_name, value
                    )
                )
        filter_text = (
            " · ".join(filters)
            if filters else "All valid pass / beam combinations"
        )
        date_text = self.acquisition_date_label.text() or "Date unavailable"
        return (
            f"{layer_name} — {x_name} × {y_name}\n"
            f"{date_text} · {filter_text}"
        )

    def _point_picked(
        self,
        event,
    ) -> None:
        if (
            self.layer is None
            or event.artist is not self.scatter
        ):
            return

        indices = list(
            getattr(event, "ind", [])
        )

        if not indices:
            return

        display_index = int(indices[0])

        if (
            display_index < 0
            or display_index
            >= len(self.display_fids)
        ):
            return

        feature_id = int(
            self.display_fids[
                display_index
            ]
        )

        gui_event = getattr(
            event.mouseevent,
            "guiEvent",
            None,
        )

        modifiers = (
            gui_event.modifiers()
            if gui_event
            else Qt.NoModifier
        )

        if modifiers & Qt.ControlModifier:
            selected_ids = set(
                self.layer.selectedFeatureIds()
            )

            if feature_id in selected_ids:
                selected_ids.remove(
                    feature_id
                )
            else:
                selected_ids.add(
                    feature_id
                )

            self._set_layer_selection(
                selected_ids
            )
        else:
            self._set_layer_selection(
                {feature_id}
            )

    def _rectangle_selected(
        self,
        click_event,
        release_event,
    ) -> None:
        if (
            self.layer is None
            or len(self.full_fids) == 0
        ):
            return

        if (
            click_event.xdata is None
            or click_event.ydata is None
            or release_event.xdata is None
            or release_event.ydata is None
        ):
            return

        x_min, x_max = sorted(
            [
                click_event.xdata,
                release_event.xdata,
            ]
        )

        y_min, y_max = sorted(
            [
                click_event.ydata,
                release_event.ydata,
            ]
        )

        mask = (
            (self.full_x >= x_min)
            & (self.full_x <= x_max)
            & (self.full_y >= y_min)
            & (self.full_y <= y_max)
        )

        selected_ids = set(
            self.full_fids[mask]
            .astype(int)
            .tolist()
        )

        self._set_layer_selection(
            selected_ids
        )

    def _set_layer_selection(
        self,
        feature_ids: set[int],
    ) -> None:
        if self.layer is None:
            return

        self._updating_layer_selection = True

        try:
            self.layer.selectByIds(
                list(feature_ids)
            )
        finally:
            self._updating_layer_selection = False

        self._update_selected_markers()

    def _layer_selection_changed(
        self,
        *args,
    ) -> None:
        if self._updating_layer_selection:
            return

        self._update_selected_markers()

    def _update_selected_markers(
        self,
    ) -> None:
        if (
            self.layer is None
            or self.selected_scatter is None
        ):
            return

        selected_ids = np.asarray(
            self.layer.selectedFeatureIds(),
            dtype=np.int64,
        )

        if (
            len(selected_ids) == 0
            or len(self.full_fids) == 0
        ):
            selected_xy = np.empty(
                (0, 2),
                dtype=float,
            )
            selected_count = 0
        else:
            mask = np.isin(
                self.full_fids,
                selected_ids,
            )

            selected_xy = np.column_stack(
                (
                    self.full_x[mask],
                    self.full_y[mask],
                )
            )

            selected_count = int(
                mask.sum()
            )

        self.selected_scatter.set_offsets(
            selected_xy
        )

        self.canvas.draw_idle()

        self.status_label.setText(
            f"Valid profile points: "
            f"{len(self.full_fids):,}. "
            f"Selected: {selected_count:,}."
        )

    def clear_selection(self) -> None:
        if self.layer is None:
            return

        self.layer.removeSelection()
        self._update_selected_markers()

    def _set_canvas_extent_from_wgs84(
        self,
        longitudes: np.ndarray,
        latitudes: np.ndarray,
    ) -> None:
        """Zoom the QGIS canvas using WGS84 longitude/latitude arrays."""
        if len(longitudes) == 0 or len(latitudes) == 0:
            return

        min_lon = float(np.min(longitudes))
        max_lon = float(np.max(longitudes))
        min_lat = float(np.min(latitudes))
        max_lat = float(np.max(latitudes))

        lon_span = max_lon - min_lon
        lat_span = max_lat - min_lat

        # Keep a visible buffer even for a single point or a very short track.
        lon_buffer = max(lon_span * 0.08, 0.0005)
        lat_buffer = max(lat_span * 0.08, 0.0005)

        rectangle_wgs84 = QgsRectangle(
            min_lon - lon_buffer,
            min_lat - lat_buffer,
            max_lon + lon_buffer,
            max_lat + lat_buffer,
        )

        canvas = self.iface.mapCanvas()
        destination_crs = (
            canvas.mapSettings().destinationCrs()
        )
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

        if destination_crs != wgs84:
            transform = QgsCoordinateTransform(
                wgs84,
                destination_crs,
                QgsProject.instance(),
            )
            rectangle = transform.transformBoundingBox(
                rectangle_wgs84
            )
        else:
            rectangle = rectangle_wgs84

        canvas.setExtent(rectangle)
        canvas.refresh()

    def zoom_to_profile_extent(self) -> None:
        """Zoom to all points currently included by the profile filters."""
        if len(self.full_fids) == 0:
            self._show_information(
                "Create a profile before zooming to its extent."
            )
            return

        self._set_canvas_extent_from_wgs84(
            self.full_lon,
            self.full_lat,
        )

    def zoom_to_selected_points(self) -> None:
        """Zoom only to selected points that belong to the current profile."""
        if self.layer is None or len(self.full_fids) == 0:
            return

        selected_ids = np.asarray(
            self.layer.selectedFeatureIds(),
            dtype=np.int64,
        )

        if len(selected_ids) == 0:
            self._show_information(
                "Select one or more points in the profile first."
            )
            return

        mask = np.isin(
            self.full_fids,
            selected_ids,
        )

        if not np.any(mask):
            self._show_information(
                "The selected map features do not belong to the current "
                "profile filters."
            )
            return

        self._set_canvas_extent_from_wgs84(
            self.full_lon[mask],
            self.full_lat[mask],
        )

    def exclude_selected_from_profile(self) -> None:
        """
        Exclude selected current-profile points without modifying source data.

        Exclusions are session-only. They can be restored with the profile
        button and are cleared when another source layer is selected.
        """
        if self.layer is None or len(self.full_fids) == 0:
            return

        selected_ids = np.asarray(
            self.layer.selectedFeatureIds(),
            dtype=np.int64,
        )

        if len(selected_ids) == 0:
            self._show_information(
                "Select one or more points in the profile first."
            )
            return

        mask = np.isin(
            self.full_fids,
            selected_ids,
        )
        profile_selected = self.full_fids[mask]

        if len(profile_selected) == 0:
            self._show_information(
                "None of the selected map features belongs to the current "
                "profile filters."
            )
            return

        answer = QMessageBox.question(
            self,
            "Exclude profile points",
            (
                f"Exclude {len(profile_selected):,} selected points from "
                "the current profile?\n\n"
                "The source layer and GeoPackage will not be modified."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self.rejected_fids.update(
            int(fid) for fid in profile_selected
        )

        keep_mask = ~mask
        self.full_fids = self.full_fids[keep_mask]
        self.full_lon = self.full_lon[keep_mask]
        self.full_lat = self.full_lat[keep_mask]
        self.full_x = self.full_x[keep_mask]
        self.full_y = self.full_y[keep_mask]

        self.layer.removeSelection()
        self._update_display_sample()
        self._draw_profile()

    def restore_excluded_points(self) -> None:
        """Restore all session-only exclusions and rebuild the profile."""
        if not self.rejected_fids:
            self._show_information(
                "There are no excluded profile points to restore."
            )
            return

        self.rejected_fids.clear()
        self.create_profile()

    def _clear_plot(self) -> None:
        self.full_fids = np.array(
            [],
            dtype=np.int64,
        )
        self.full_lon = np.array(
            [],
            dtype=float,
        )
        self.full_lat = np.array(
            [],
            dtype=float,
        )
        self.full_x = np.array(
            [],
            dtype=float,
        )
        self.full_y = np.array(
            [],
            dtype=float,
        )
        self.display_fids = np.array(
            [],
            dtype=np.int64,
        )
        self.display_x = np.array(
            [],
            dtype=float,
        )
        self.display_y = np.array(
            [],
            dtype=float,
        )

        self.scatter = None
        self.selected_scatter = None

        self.axes.clear()
        self.canvas.draw_idle()

    def closeEvent(self, event) -> None:
        self._disconnect_layer()
        super().closeEvent(event)

    def _show_information(
        self,
        message: str,
    ) -> None:
        QMessageBox.information(
            self,
            "ICESat-2 Interactive Profile",
            message,
        )
