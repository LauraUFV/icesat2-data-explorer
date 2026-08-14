from __future__ import annotations

from pathlib import Path
from typing import Any

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsGraduatedSymbolRenderer,
    QgsProject,
    QgsRendererRange,
    QgsSymbol,
    QgsVectorLayer,
)

from .icesat2_dialog import ICESat2Dialog
from .polygon_map_tool import PolygonMapTool
from .report_utils import export_processing_report
from .report_map import render_aoi_overview
from .ui_assets import icon
from .sliderule_support import (
    SlideruleInstallTask,
    activate_managed_sliderule,
    sliderule_health,
)


ATL03_INVALID_EXTENTS_PARAMETER = "pass_invalid"


class ICESat2DataExplorerPlugin:
    """
    Main QGIS plugin class.
    """

    PLUGIN_VERSION = "0.10.1"

    ATL24_LAYER_NAME = "atl24_bathymetry"
    ATL08_LAYER_NAME = "atl08_segments"
    ATL03_LAYER_NAME = "atl03_photons"
    ATL13_LAYER_NAME = "atl13_inland_water"

    ATL08_FALLBACK_DISPLAY_FIELDS = [
        "h_canopy",
        "h_mean_canopy",
        "h_max_canopy",
        "h_te_median",
        "terrain_slope",
        "segment_cover",
        "n_te_photons",
        "n_ca_photons",
    ]

    ATL03_GEOPHYSICS_FIELDS = [
        "geoid",
        "geoid_free2mean",
        "tide_ocean",
    ]

    ATL03_FALLBACK_DISPLAY_FIELDS = [
        "height",
        "height_ortho",
        "geoid",
        "tide_ocean",
        "geoid_free2mean",
        "atl03_cnf",
        "quality_ph",
        "solar_elevation",
        "background_rate",
        "x_atc",
    ]

    ATL13_FALLBACK_DISPLAY_FIELDS = [
        "ht_ortho",
        "ht_water_surf",
        "stdev_water_surf",
        "water_depth",
    ]

    PRODUCT_VERSION_CONTEXT = {
        "ATL03": "ATL03 Version 7",
        "ATL08": "ATL08 Version 7",
        "ATL13": "ATL13 Version 7",
        "ATL24": "ATL24 Version 2",
    }

    def __init__(self, iface):
        self.iface = iface

        self.action = None
        self.profile_action = None
        self.model_tide_action = None
        self.about_action = None

        self.toolbar = None
        self.plugin_menu = None

        self.dialog = None
        self.profile_dialog = None
        self.model_tide_dialog = None
        self.current_task = None
        self.sliderule_install_task = None

        self.polygon_tool = None
        self.previous_map_tool = None

        self.current_aoi_polygon = None
        self.current_aoi_type = "bounding box"

        self.last_parameters = None
        self.last_output_path = None
        self.last_product = None

        self.last_display_field = None
        self.last_display_label = None

        self.last_local_filters = []
        self.last_server_filters = {}

        self.last_report_path = None

        self._setting_coordinates = False

    # ------------------------------------------------------------------
    # Plugin lifecycle
    # ------------------------------------------------------------------

    def _create_action(
        self,
        text: str,
        icon_name: str,
        callback,
        tooltip: str,
        object_name: str,
    ) -> QAction:
        action = QAction(
            icon(icon_name),
            text,
            self.iface.mainWindow(),
        )
        action.setObjectName(object_name)
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)
        action.triggered.connect(callback)
        return action

    def initGui(self) -> None:
        """Create one named toolbar and one grouped Plugins menu."""
        self.toolbar = self.iface.addToolBar(
            "ICESat-2 Data Explorer"
        )
        self.toolbar.setObjectName(
            "ICESat2DataExplorerToolbar"
        )
        self.toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self.toolbar.setIconSize(QSize(24, 24))

        self.plugin_menu = QMenu(
            "ICESat-2 Data Explorer",
            self.iface.mainWindow(),
        )
        self.plugin_menu.setObjectName(
            "ICESat2DataExplorerMenu"
        )
        self.plugin_menu.setIcon(icon("plugin.svg"))
        self.iface.pluginMenu().addMenu(
            self.plugin_menu
        )

        self.action = self._create_action(
            "Data Explorer",
            "data_explorer.svg",
            self.open_dialog,
            "Download and prepare ATL03, ATL08, ATL13 and ATL24 data",
            "ICESat2DataExplorerAction",
        )
        self.profile_action = self._create_action(
            "Interactive Profile",
            "profile.svg",
            self.open_profile_dialog,
            "Open an interactive profile for an ICESat-2 layer",
            "ICESat2ProfileAction",
        )
        self.model_tide_action = self._create_action(
            "Model Tide Values",
            "tide.svg",
            self.open_model_tide_dialog,
            "Add GOT4.10c model tide values to an ATL24 layer",
            "ICESat2ModelTideAction",
        )
        self.about_action = self._create_action(
            "About",
            "about.svg",
            self.show_about,
            "About ICESat-2 Data Explorer",
            "ICESat2AboutAction",
        )

        for action in (
            self.action,
            self.profile_action,
            self.model_tide_action,
        ):
            self.toolbar.addAction(action)
            self.plugin_menu.addAction(action)

        self.plugin_menu.addSeparator()
        self.plugin_menu.addAction(self.about_action)

        if Qgis.QGIS_VERSION_INT < 34400:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "ICESat-2 Data Explorer compatibility",
                (
                    "This plugin requires QGIS 3.44 or later.\n\n"
                    "QGIS 3.44 LTR is the recommended and tested "
                    "environment. Automatic SlideRule setup is not "
                    "supported on QGIS 3.30 because its bundled Python "
                    "environment may not provide a usable SSL module."
                ),
            )

    def open_profile_dialog(self) -> None:
        # Lazy import keeps Matplotlib out of QGIS startup.
        from .profile_dialog import ICESat2ProfileDialog

        if self.profile_dialog is None:
            self.profile_dialog = ICESat2ProfileDialog(
                iface=self.iface,
                parent=self.iface.mainWindow(),
            )
        else:
            self.profile_dialog.refresh_layers()

        self.profile_dialog.show()
        self.profile_dialog.raise_()
        self.profile_dialog.activateWindow()

    def open_model_tide_dialog(self) -> None:
        # pyTMD remains isolated and is not imported into the QGIS process.
        from .model_tide_dialog import ModelTideDialog

        if self.model_tide_dialog is None:
            self.model_tide_dialog = ModelTideDialog(
                iface=self.iface,
                parent=self.iface.mainWindow(),
            )
        else:
            self.model_tide_dialog.refresh_layers()
            self.model_tide_dialog.refresh_support_status()

        self.model_tide_dialog.show()
        self.model_tide_dialog.raise_()
        self.model_tide_dialog.activateWindow()

    def show_about(self) -> None:
        QMessageBox.about(
            self.iface.mainWindow(),
            "About ICESat-2 Data Explorer",
            (
                "<h2>ICESat-2 Data Explorer</h2>"
                f"<p><b>Version {self.PLUGIN_VERSION}</b></p>"
                "<p>Download and analyze ATL03, ATL08, ATL13 and ATL24 "
                "products, create interactive profiles and associate "
                "GOT4.10c model tide values in QGIS.</p>"
                "<p><b>Compatibility</b><br>"
                "QGIS 3.44 or later is required. QGIS 3.44 LTR is "
                "the recommended and tested environment. Automatic "
                "SlideRule setup is not supported on QGIS 3.30.</p>"
                "<p><b>Laura Coelho de Andrade</b><br>"
                "PhD Candidate<br>"
                "Federal University of Viçosa (UFV), Brazil</p>"
            ),
        )

    def unload(self) -> None:
        if self.current_task is not None:
            self.current_task.cancel()

        if self.sliderule_install_task is not None:
            self.sliderule_install_task.cancel()

        if self.polygon_tool is not None:
            self.polygon_tool.clear()

        for dialog_name in (
            "dialog",
            "profile_dialog",
            "model_tide_dialog",
        ):
            dialog = getattr(self, dialog_name, None)
            if dialog is not None:
                dialog.close()
                setattr(self, dialog_name, None)

        if self.plugin_menu is not None:
            self.iface.pluginMenu().removeAction(
                self.plugin_menu.menuAction()
            )
            self.plugin_menu.deleteLater()
            self.plugin_menu = None

        if self.toolbar is not None:
            self.iface.mainWindow().removeToolBar(
                self.toolbar
            )
            self.toolbar.deleteLater()
            self.toolbar = None

        for action_name in (
            "action",
            "profile_action",
            "model_tide_action",
            "about_action",
        ):
            action = getattr(self, action_name, None)
            if action is not None:
                action.deleteLater()
                setattr(self, action_name, None)

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------

    def open_dialog(self) -> None:
        if self.dialog is None:
            self.dialog = ICESat2Dialog(
                self.iface.mainWindow()
            )

            self.dialog.use_extent_button.clicked.connect(
                self.use_current_map_extent
            )

            self.dialog.draw_polygon_button.clicked.connect(
                self.activate_polygon_tool
            )

            self.dialog.use_selected_polygon_button.clicked.connect(
                self.use_selected_polygon
            )

            self.dialog.run_button.clicked.connect(
                self.start_product_task
            )

            self.dialog.cancel_button.clicked.connect(
                self.cancel_current_task
            )

            self.dialog.download_support_button.clicked.connect(
                self.install_or_repair_sliderule_support
            )

            for widget in (
                self.dialog.west_spin,
                self.dialog.south_spin,
                self.dialog.east_spin,
                self.dialog.north_spin,
            ):
                widget.valueChanged.connect(
                    self.coordinate_value_changed
                )

        self.refresh_sliderule_support_status()

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def refresh_sliderule_support_status(self) -> tuple[str, str, str | None]:
        state, details, version = sliderule_health()

        if self.dialog is not None:
            self.dialog.set_download_support_status(
                state,
                details,
                version,
            )

        return state, details, version

    def install_or_repair_sliderule_support(self) -> None:
        if self.sliderule_install_task is not None:
            self.dialog.show_information(
                "Download-support installation is already running."
            )
            return

        if self.current_task is not None:
            self.dialog.show_error(
                "Wait for the current processing task to finish."
            )
            return

        state, details, version = sliderule_health()
        repairing = state in {"ready", "broken"}

        title = (
            "Repair Download Support"
            if repairing
            else "Install Download Support"
        )

        action_text = (
            "repair the managed SlideRule client"
            if repairing
            else "install the SlideRule Python client"
        )

        response = QMessageBox.question(
            self.dialog,
            title,
            (
                f"The plugin will {action_text} in its own local folder.\n\n"
                "It will install only SlideRule and will not replace NumPy, "
                "pandas, GeoPandas, GDAL or other QGIS packages.\n\n"
                "An internet connection is required. Continue?"
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if response != QMessageBox.StandardButton.Yes:
            return

        task = SlideruleInstallTask()
        self.sliderule_install_task = task
        self.dialog.set_download_support_installing(True)
        self.dialog.status_label.setText(
            "Installing SlideRule download support..."
        )
        self.dialog.progress_bar.setValue(0)

        task.progressChanged.connect(
            lambda value: self.dialog.progress_bar.setValue(
                int(round(value))
            )
        )
        task.taskCompleted.connect(
            lambda: self.sliderule_support_install_finished(
                task,
                True,
            )
        )
        task.taskTerminated.connect(
            lambda: self.sliderule_support_install_finished(
                task,
                False,
            )
        )

        QgsApplication.taskManager().addTask(task)

    def sliderule_support_install_finished(
        self,
        task: SlideruleInstallTask,
        completed: bool,
    ) -> None:
        if task is not self.sliderule_install_task:
            return

        self.sliderule_install_task = None
        self.dialog.set_download_support_installing(False)

        if not completed or task.error_message:
            self.dialog.progress_bar.setValue(0)
            self.dialog.status_label.setText(
                "SlideRule download-support installation failed."
            )
            self.refresh_sliderule_support_status()
            self.dialog.show_error(
                (task.error_message or "Installation was canceled.")
                + (
                    "\n\nTechnical details:\n"
                    + task.error_traceback
                    if task.error_traceback
                    else ""
                )
            )
            return

        state, details, version = activate_managed_sliderule()
        self.dialog.set_download_support_status(
            state,
            details,
            version,
        )

        if state != "ready":
            self.dialog.progress_bar.setValue(0)
            self.dialog.status_label.setText(
                "SlideRule was installed but could not be activated."
            )
            self.dialog.show_error(details)
            return

        self.dialog.progress_bar.setValue(100)
        self.dialog.status_label.setText(
            "Download support installed. You can now download ICESat-2 products."
        )
        self.dialog.show_information(
            (
                f"SlideRule {version or ''} was installed successfully.\n\n"
                "ATL03, ATL08, ATL13 and ATL24 downloads are now available. "
                "QGIS does not need to be restarted."
            )
        )

    def coordinate_value_changed(
        self,
        _value,
    ) -> None:
        if self._setting_coordinates:
            return

        self.current_aoi_polygon = None
        self.current_aoi_type = "bounding box"

        if self.dialog is not None:
            self.dialog.aoi_type_label.setText(
                "Area type: bounding box"
            )

    # ------------------------------------------------------------------
    # Coordinate transformations
    # ------------------------------------------------------------------

    @staticmethod
    def wgs84_crs() -> QgsCoordinateReferenceSystem:
        return QgsCoordinateReferenceSystem(
            "EPSG:4326"
        )

    def transform_extent_to_wgs84(
        self,
        extent,
        source_crs,
    ):
        destination_crs = self.wgs84_crs()

        if source_crs == destination_crs:
            return extent

        transform = QgsCoordinateTransform(
            source_crs,
            destination_crs,
            QgsProject.instance(),
        )

        return transform.transformBoundingBox(
            extent
        )

    def transform_geometry_to_wgs84(
        self,
        geometry: QgsGeometry,
        source_crs,
    ) -> QgsGeometry:
        transformed_geometry = QgsGeometry(
            geometry
        )

        destination_crs = self.wgs84_crs()

        if source_crs == destination_crs:
            return transformed_geometry

        transform = QgsCoordinateTransform(
            source_crs,
            destination_crs,
            QgsProject.instance(),
        )

        result = transformed_geometry.transform(
            transform
        )

        if result != 0:
            raise RuntimeError(
                "The polygon could not be transformed "
                "to EPSG:4326."
            )

        return transformed_geometry

    # ------------------------------------------------------------------
    # AOI conversion
    # ------------------------------------------------------------------

    def set_dialog_bounding_box(
        self,
        bounding_box,
    ) -> None:
        self._setting_coordinates = True

        try:
            self.dialog.set_bounding_box(
                bounding_box
            )
        finally:
            self._setting_coordinates = False

    @staticmethod
    def normalize_sliderule_polygon(
        polygon,
    ) -> list[dict[str, float]]:
        """
        Return a closed, counter-clockwise polygon for SlideRule.

        SlideRule requires the first and last point to match and the exterior
        ring to use counter-clockwise orientation. QGIS allows either ring
        orientation, so drawn and selected polygons are normalized here.
        """
        points = [
            {
                "lon": float(point["lon"]),
                "lat": float(point["lat"]),
            }
            for point in polygon
        ]

        if len(points) < 3:
            raise ValueError(
                "The area of interest must contain at least three vertices."
            )

        if (
            points[0]["lon"] == points[-1]["lon"]
            and points[0]["lat"] == points[-1]["lat"]
        ):
            points = points[:-1]

        signed_double_area = 0.0

        for index, point in enumerate(points):
            next_point = points[
                (index + 1)
                % len(points)
            ]
            signed_double_area += (
                point["lon"]
                * next_point["lat"]
                - next_point["lon"]
                * point["lat"]
            )

        if signed_double_area < 0.0:
            points.reverse()

        points.append(
            dict(points[0])
        )

        return points

    @classmethod
    def bounding_box_to_polygon(
        cls,
        bounding_box,
    ) -> list[dict[str, float]]:
        west, south, east, north = bounding_box

        return cls.normalize_sliderule_polygon(
            [
                {"lon": west, "lat": south},
                {"lon": east, "lat": south},
                {"lon": east, "lat": north},
                {"lon": west, "lat": north},
            ]
        )

    @staticmethod
    def geometry_to_sliderule_polygon(
        geometry: QgsGeometry,
    ) -> list[dict[str, float]]:
        if geometry.isNull() or geometry.isEmpty():
            raise ValueError(
                "The polygon geometry is empty."
            )

        if geometry.type() != Qgis.GeometryType.Polygon:
            raise ValueError(
                "The geometry must be a polygon."
            )

        rings = []

        if geometry.isMultipart():
            polygons = geometry.asMultiPolygon()

            for polygon in polygons:
                if polygon and len(polygon[0]) >= 4:
                    rings.append(polygon[0])
        else:
            polygon = geometry.asPolygon()

            if polygon and len(polygon[0]) >= 4:
                rings.append(polygon[0])

        if not rings:
            raise ValueError(
                "No valid exterior polygon ring was found."
            )

        largest_ring = max(
            rings,
            key=lambda ring: abs(
                QgsGeometry.fromPolygonXY(
                    [ring]
                ).area()
            ),
        )

        sliderule_polygon = [
            {
                "lon": float(point.x()),
                "lat": float(point.y()),
            }
            for point in largest_ring
        ]

        return (
            ICESat2DataExplorerPlugin
            .normalize_sliderule_polygon(
                sliderule_polygon
            )
        )

    @staticmethod
    def polygon_extent(
        polygon,
    ) -> tuple[float, float, float, float]:
        longitudes = [
            point["lon"]
            for point in polygon
        ]
        latitudes = [
            point["lat"]
            for point in polygon
        ]

        return (
            min(longitudes),
            min(latitudes),
            max(longitudes),
            max(latitudes),
        )

    @staticmethod
    def sliderule_polygon_to_wkt(
        polygon,
    ) -> str:
        coordinate_text = ", ".join(
            (
                f"{float(point['lon']):.12f} "
                f"{float(point['lat']):.12f}"
            )
            for point in polygon
        )

        return f"POLYGON (({coordinate_text}))"

    # ------------------------------------------------------------------
    # Use current map extent
    # ------------------------------------------------------------------

    def use_current_map_extent(self) -> None:
        try:
            canvas = self.iface.mapCanvas()

            extent = self.transform_extent_to_wgs84(
                canvas.extent(),
                canvas.mapSettings().destinationCrs(),
            )

            bounding_box = (
                extent.xMinimum(),
                extent.yMinimum(),
                extent.xMaximum(),
                extent.yMaximum(),
            )

            self.current_aoi_polygon = (
                self.bounding_box_to_polygon(
                    bounding_box
                )
            )
            self.current_aoi_type = "map extent"

            self.set_dialog_bounding_box(
                bounding_box
            )

            self.dialog.aoi_type_label.setText(
                "Area type: current map extent"
            )
            self.dialog.status_label.setText(
                "Current map extent copied."
            )

        except Exception as error:
            self.dialog.show_error(
                f"{type(error).__name__}: {error}"
            )

    # ------------------------------------------------------------------
    # Draw polygon
    # ------------------------------------------------------------------

    def activate_polygon_tool(self) -> None:
        canvas = self.iface.mapCanvas()
        self.previous_map_tool = canvas.mapTool()

        if self.polygon_tool is None:
            self.polygon_tool = PolygonMapTool(
                canvas
            )

            self.polygon_tool.polygon_created.connect(
                self.polygon_created
            )

            self.polygon_tool.drawing_cancelled.connect(
                self.polygon_drawing_cancelled
            )

        self.polygon_tool.clear()
        canvas.setMapTool(self.polygon_tool)

        self.dialog.status_label.setText(
            "Left-click to add vertices. "
            "Right-click to finish. "
            "Press Esc to cancel."
        )
        self.dialog.hide()

    def polygon_created(
        self,
        geometry: QgsGeometry,
    ) -> None:
        try:
            canvas = self.iface.mapCanvas()

            geometry_wgs84 = (
                self.transform_geometry_to_wgs84(
                    geometry,
                    canvas.mapSettings().destinationCrs(),
                )
            )

            polygon = self.geometry_to_sliderule_polygon(
                geometry_wgs84
            )

            self.current_aoi_polygon = polygon
            self.current_aoi_type = "drawn polygon"

            self.set_dialog_bounding_box(
                self.polygon_extent(polygon)
            )

            self.dialog.aoi_type_label.setText(
                "Area type: exact drawn polygon"
            )
            self.dialog.status_label.setText(
                "The exact drawn polygon will be "
                "sent to SlideRule."
            )

        except Exception as error:
            self.dialog.show_error(
                f"{type(error).__name__}: {error}"
            )

        finally:
            self.restore_previous_map_tool()
            self.show_dialog_again()

    def polygon_drawing_cancelled(self) -> None:
        self.restore_previous_map_tool()
        self.dialog.status_label.setText(
            "Polygon drawing cancelled."
        )
        self.show_dialog_again()

    def restore_previous_map_tool(self) -> None:
        if self.previous_map_tool is not None:
            self.iface.mapCanvas().setMapTool(
                self.previous_map_tool
            )

        self.previous_map_tool = None

    def show_dialog_again(self) -> None:
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    # ------------------------------------------------------------------
    # Use selected polygon
    # ------------------------------------------------------------------

    def use_selected_polygon(self) -> None:
        layer = self.iface.activeLayer()

        if not isinstance(layer, QgsVectorLayer):
            self.dialog.show_error(
                "Select a polygon vector layer first."
            )
            return

        if layer.geometryType() != Qgis.GeometryType.Polygon:
            self.dialog.show_error(
                "The active layer must be a polygon layer."
            )
            return

        selected_features = layer.selectedFeatures()

        if len(selected_features) != 1:
            self.dialog.show_error(
                "Select exactly one polygon feature."
            )
            return

        try:
            geometry = selected_features[0].geometry()

            if geometry.isNull() or geometry.isEmpty():
                raise ValueError(
                    "The selected polygon geometry is empty."
                )

            geometry_wgs84 = (
                self.transform_geometry_to_wgs84(
                    geometry,
                    layer.crs(),
                )
            )

            polygon = self.geometry_to_sliderule_polygon(
                geometry_wgs84
            )

            self.current_aoi_polygon = polygon
            self.current_aoi_type = "selected polygon"

            self.set_dialog_bounding_box(
                self.polygon_extent(polygon)
            )

            self.dialog.aoi_type_label.setText(
                "Area type: exact selected polygon"
            )
            self.dialog.status_label.setText(
                "The exact selected polygon will be "
                "sent to SlideRule."
            )

        except Exception as error:
            self.dialog.show_error(
                f"{type(error).__name__}: {error}"
            )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_bounding_box(
        bounding_box,
    ) -> None:
        west, south, east, north = bounding_box

        if not -180.0 <= west <= 180.0:
            raise ValueError(
                "Invalid western longitude."
            )

        if not -180.0 <= east <= 180.0:
            raise ValueError(
                "Invalid eastern longitude."
            )

        if not -90.0 <= south <= 90.0:
            raise ValueError(
                "Invalid southern latitude."
            )

        if not -90.0 <= north <= 90.0:
            raise ValueError(
                "Invalid northern latitude."
            )

        if west >= east:
            raise ValueError(
                "West must be smaller than east."
            )

        if south >= north:
            raise ValueError(
                "South must be smaller than north."
            )

    def get_active_sliderule_polygon(
        self,
    ) -> list[dict[str, float]]:
        if self.current_aoi_polygon is not None:
            return self.normalize_sliderule_polygon(
                self.current_aoi_polygon
            )

        bounding_box = self.dialog.get_bounding_box()
        self.validate_bounding_box(bounding_box)

        return self.bounding_box_to_polygon(
            bounding_box
        )

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def build_common_parameters(
        self,
    ) -> dict[str, Any]:
        return {
            "poly": self.get_active_sliderule_polygon(),
            "t0": self.dialog.get_start_date(),
            "t1": self.dialog.get_end_date(),
        }

    def build_atl24_parameters(
        self,
    ) -> dict[str, Any]:
        """
        Build an ATL24 request using the current numeric class code.

        The current SlideRule documentation defines class 40 as bathymetry.
        Ancillary beam fields are requested at the top level, as shown in the
        current atl24x ancillary-data example.
        """
        parameters = self.build_common_parameters()

        release = self.dialog.get_atl24_release()
        minimum_confidence = float(
            self.dialog.minimum_confidence_spin.value()
        )

        parameters["granule"] = {
            "version": release,
        }

        parameters["anc_fields"] = [
            "index_ph",
        ]

        atl24_parameters = {
            "compact": False,
            "class_ph": [
                40,
            ],
            "confidence_threshold": minimum_confidence,
        }

        if self.dialog.exclude_low_confidence_check.isChecked():
            atl24_parameters["low_confidence"] = "off"

        if self.dialog.exclude_sensor_depth_check.isChecked():
            atl24_parameters["sensor_depth_exceeded"] = "off"

        if self.dialog.exclude_invalid_kd_check.isChecked():
            atl24_parameters["invalid_kd"] = "off"

        if self.dialog.exclude_invalid_wind_check.isChecked():
            atl24_parameters["invalid_wind_speed"] = "off"

        parameters["atl24"] = atl24_parameters

        self.last_server_filters = {
            "granule.version": release,
            "atl24.class_ph": [
                40,
            ],
            "atl24.confidence_threshold": minimum_confidence,
            "anc_fields": [
                "index_ph",
            ],
        }

        for field_name in (
            "low_confidence",
            "sensor_depth_exceeded",
            "invalid_kd",
            "invalid_wind_speed",
        ):
            if field_name in atl24_parameters:
                self.last_server_filters[
                    "atl24." + field_name
                ] = atl24_parameters[field_name]

        return parameters

    def build_atl08_parameters(
        self,
    ) -> dict[str, Any]:
        parameters = self.build_common_parameters()

        terrain_quality = int(
            self.dialog.terrain_quality_spin.value()
        )
        canopy_quality = int(
            self.dialog.canopy_quality_spin.value()
        )

        self.last_server_filters = {}

        if terrain_quality > 0:
            parameters[
                "te_quality_score"
            ] = terrain_quality
            self.last_server_filters[
                "te_quality_score"
            ] = terrain_quality

        if canopy_quality > 0:
            parameters[
                "can_quality_score"
            ] = canopy_quality
            self.last_server_filters[
                "can_quality_score"
            ] = canopy_quality

        return parameters

    def build_atl08_local_filters(
        self,
    ) -> list[str]:
        expressions = []

        if self.dialog.exclude_invalid_terrain_check.isChecked():
            expressions.append(
                '"h_te_median" IS NOT NULL'
            )

        if self.dialog.exclude_no_ground_check.isChecked():
            expressions.append(
                '"n_te_photons" > 0'
            )

        if self.dialog.exclude_no_canopy_check.isChecked():
            expressions.append(
                '"n_ca_photons" > 0'
            )

        if self.dialog.exclude_negative_canopy_check.isChecked():
            expressions.append(
                '"h_canopy" >= 0'
            )

        return expressions

    def build_atl03_parameters(
        self,
    ) -> dict[str, Any]:
        """Build a robust photon-level ATL03 request through SlideRule."""
        parameters = self.build_common_parameters()

        surface_type = self.dialog.get_atl03_surface_type()
        confidence = self.dialog.get_atl03_confidence()
        quality = self.dialog.get_atl03_quality()

        parameters["srt"] = surface_type
        parameters["cnf"] = confidence
        parameters["quality_ph"] = quality

        # ATL03 Version 7 is the current NSIDC release. Setting it explicitly
        # avoids depending on a server-side default that can lag behind the
        # current collection or vary during catalog transitions.
        parameters["granule"] = {
            "version": "007",
        }

        # ATL03x groups photons into short extents internally. Keeping invalid
        # extents is important for small coastal AOIs and permissive photon
        # filters; otherwise valid individual photons can be excluded because
        # the surrounding extent fails a default spread/count check.
        parameters[ATL03_INVALID_EXTENTS_PARAMETER] = True

        geophysics_fields = list(
            self.ATL03_GEOPHYSICS_FIELDS
        )
        parameters["atl03_corr_fields"] = geophysics_fields

        self.last_server_filters = {
            "srt": surface_type,
            "cnf": confidence,
            "quality_ph": quality,
            ATL03_INVALID_EXTENTS_PARAMETER: True,
            "atl03_corr_fields": geophysics_fields,
            "granule.version": "007",
        }

        return parameters

    def build_atl03_local_filters(
        self,
    ) -> list[str]:
        expressions = []
        display_field = self.dialog.get_atl03_display_field()

        if self.dialog.atl03_hide_null_display_check.isChecked():
            expressions.append(
                f'"{display_field}" IS NOT NULL'
            )

        if self.dialog.atl03_signal_only_check.isChecked():
            expressions.append(
                '"atl03_cnf" >= 1'
            )

        return expressions

    def build_atl13_parameters(
        self,
    ) -> dict[str, Any]:
        """
        Build a spatial and temporal ATL13 request.

        The first implementation uses the standard atl13x AOI/date query.
        Body-of-water selection by refid, name or contained coordinate can
        be added later without changing the output structure.
        """
        self.last_server_filters = {}
        return self.build_common_parameters()

    def build_atl13_local_filters(
        self,
    ) -> list[str]:
        expressions = []
        display_field = self.dialog.get_atl13_display_field()

        if self.dialog.atl13_hide_null_display_check.isChecked():
            expressions.append(
                f'"{display_field}" IS NOT NULL'
            )

        if self.dialog.atl13_detected_bottom_only_check.isChecked():
            expressions.append(
                '"water_depth" IS NOT NULL AND "water_depth" > 0'
            )

        return expressions

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    def start_product_task(self) -> None:
        if self.current_task is not None:
            self.dialog.show_error(
                "Another task is already running."
            )
            return

        state, details, version = self.refresh_sliderule_support_status()

        if state != "ready":
            response = QMessageBox.question(
                self.dialog,
                "Download Support Required",
                (
                    "SlideRule download support is not ready on this computer.\n\n"
                    "Install it now? The plugin will install only the pure-Python "
                    "SlideRule client in its own local folder."
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if response == QMessageBox.StandardButton.Yes:
                self.install_or_repair_sliderule_support()

            return

        product = self.dialog.get_selected_product()
        output_path = self.dialog.get_output_path()

        if not output_path:
            self.dialog.show_error(
                "Select an output GeoPackage."
            )
            return

        try:
            self.validate_bounding_box(
                self.dialog.get_bounding_box()
            )

            if product == "ATL24":
                try:
                    from .atl24_task import ATL24DownloadTask
                except ModuleNotFoundError as error:
                    if error.name == "sliderule":
                        raise RuntimeError(
                            "SlideRule could not be imported after the support check. "
                            "Use Install/Repair download support in the main window."
                        ) from error
                    raise

                parameters = self.build_atl24_parameters()

                task = ATL24DownloadTask(
                    parameters=parameters,
                    output_path=output_path,
                    layer_name=self.ATL24_LAYER_NAME,
                )

                self.last_display_field = "depth"
                self.last_display_label = "Depth"
                self.last_local_filters = []

            elif product == "ATL08":
                try:
                    from .atl08_task import ATL08DownloadTask
                except ModuleNotFoundError as error:
                    if error.name == "sliderule":
                        raise RuntimeError(
                            "SlideRule could not be imported after the support check. "
                            "Use Install/Repair download support in the main window."
                        ) from error
                    raise

                self.last_display_field = (
                    self.dialog.get_atl08_display_field()
                )
                self.last_display_label = (
                    self.dialog.get_atl08_display_label()
                )
                self.last_local_filters = (
                    self.build_atl08_local_filters()
                )

                parameters = self.build_atl08_parameters()

                query_metadata = {
                    "plugin_name": "ICESat-2 Data Explorer",
                    "plugin_version": self.PLUGIN_VERSION,
                    "report_author": "Laura Coelho de Andrade",
                    "report_role": "PhD Candidate",
                    "institution": "Federal University of Viçosa (UFV), Brazil",
                    "product": product,
                    "start_date": self.dialog.get_start_date(),
                    "end_date": self.dialog.get_end_date(),
                    "area_type": self.current_aoi_type,
                    "polygon_wkt": self.sliderule_polygon_to_wkt(
                        parameters.get("poly", [])
                    ),
                    "display_field": self.last_display_field,
                    "display_label": self.last_display_label,
                    "server_filters": self.last_server_filters,
                    "local_display_filters": self.last_local_filters,
                    "local_filters_remove_records": False,
                }

                task = ATL08DownloadTask(
                    parameters=parameters,
                    output_path=output_path,
                    layer_name=self.ATL08_LAYER_NAME,
                    query_metadata=query_metadata,
                )

            elif product == "ATL03":
                try:
                    from .atl03_task import ATL03DownloadTask
                except ModuleNotFoundError as error:
                    if error.name == "sliderule":
                        raise RuntimeError(
                            "SlideRule could not be imported after the support check. "
                            "Use Install/Repair download support in the main window."
                        ) from error
                    raise

                self.last_display_field = (
                    self.dialog.get_atl03_display_field()
                )
                self.last_display_label = (
                    self.dialog.get_atl03_display_label()
                )
                self.last_local_filters = (
                    self.build_atl03_local_filters()
                )

                parameters = self.build_atl03_parameters()

                query_metadata = {
                    "plugin_name": "ICESat-2 Data Explorer",
                    "plugin_version": self.PLUGIN_VERSION,
                    "report_author": "Laura Coelho de Andrade",
                    "report_role": "PhD Candidate",
                    "institution": "Federal University of Viçosa (UFV), Brazil",
                    "product": product,
                    "product_version_context": "ATL03 Version 7",
                    "start_date": self.dialog.get_start_date(),
                    "end_date": self.dialog.get_end_date(),
                    "area_type": self.current_aoi_type,
                    "polygon_wkt": self.sliderule_polygon_to_wkt(
                        parameters.get("poly", [])
                    ),
                    "display_field": self.last_display_field,
                    "display_label": self.last_display_label,
                    "server_filters": self.last_server_filters,
                    "local_display_filters": self.last_local_filters,
                    "local_filters_remove_records": False,
                }

                task = ATL03DownloadTask(
                    parameters=parameters,
                    output_path=output_path,
                    layer_name=self.ATL03_LAYER_NAME,
                    query_metadata=query_metadata,
                )

            elif product == "ATL13":
                try:
                    from .atl13_task import ATL13DownloadTask
                except ModuleNotFoundError as error:
                    if error.name == "sliderule":
                        raise RuntimeError(
                            "SlideRule could not be imported after the support check. "
                            "Use Install/Repair download support in the main window."
                        ) from error
                    raise

                self.last_display_field = (
                    self.dialog.get_atl13_display_field()
                )
                self.last_display_label = (
                    self.dialog.get_atl13_display_label()
                )
                self.last_local_filters = (
                    self.build_atl13_local_filters()
                )

                parameters = self.build_atl13_parameters()

                query_metadata = {
                    "plugin_name": "ICESat-2 Data Explorer",
                    "plugin_version": self.PLUGIN_VERSION,
                    "report_author": "Laura Coelho de Andrade",
                    "report_role": "PhD Candidate",
                    "institution": "Federal University of Viçosa (UFV), Brazil",
                    "product": product,
                    "product_version_context": "ATL13 Version 7",
                    "start_date": self.dialog.get_start_date(),
                    "end_date": self.dialog.get_end_date(),
                    "area_type": self.current_aoi_type,
                    "polygon_wkt": self.sliderule_polygon_to_wkt(
                        parameters.get("poly", [])
                    ),
                    "display_field": self.last_display_field,
                    "display_label": self.last_display_label,
                    "server_filters": self.last_server_filters,
                    "local_display_filters": self.last_local_filters,
                    "local_filters_remove_records": False,
                }

                task = ATL13DownloadTask(
                    parameters=parameters,
                    output_path=output_path,
                    layer_name=self.ATL13_LAYER_NAME,
                    query_metadata=query_metadata,
                )

            else:
                raise ValueError(
                    f"{product} is not implemented yet."
                )

            self.current_task = task
            self.last_parameters = parameters
            self.last_output_path = output_path
            self.last_product = product
            self.last_report_path = None

            task.progressChanged.connect(
                lambda value: (
                    self.dialog.progress_bar.setValue(
                        int(round(value))
                    )
                    if self.dialog is not None
                    else None
                )
            )

            if hasattr(task, "progress_message"):
                task.progress_message.connect(
                    lambda message: (
                        self.dialog.status_label.setText(str(message))
                        if self.dialog is not None
                        else None
                    )
                )

            task.taskCompleted.connect(
                self.task_completed
            )
            task.taskTerminated.connect(
                self.task_terminated
            )

            self.dialog.progress_bar.setValue(0)
            self.dialog.set_running(True)
            self.dialog.status_label.setText(
                f"{product} task started."
            )

            QgsApplication.taskManager().addTask(
                task
            )

        except Exception as error:
            self.current_task = None
            self.dialog.set_running(False)
            self.dialog.show_error(
                f"{type(error).__name__}: {error}"
            )

    def cancel_current_task(self) -> None:
        if self.current_task is None:
            return

        self.current_task.cancel()
        self.dialog.status_label.setText(
            "Cancelling task..."
        )

    def task_completed(self) -> None:
        task = self.current_task
        product = self.last_product

        self.dialog.set_running(False)

        if task is None:
            return

        if task.result_count == 0:
            self.dialog.progress_bar.setValue(100)
            self.dialog.status_label.setText(
                f"No {product} data found."
            )

            if product == "ATL03":
                discovered = int(
                    getattr(task, "granules_discovered", 0) or 0
                )
                checked = int(
                    getattr(task, "diagnostic_resources_checked", 0) or 0
                )
                if discovered:
                    message = (
                        f"NASA CMR identified {discovered:,} ATL03 Version 7 "
                        "granule(s), but no photons were returned by the "
                        "selected filters. "
                        f"The plugin checked up to {checked:,} granule(s) with "
                        "its permissive Land/Ocean/Inland-water diagnostic.\n\n"
                        "Check the acquisition date of the known track and the "
                        "selected native surface/confidence filters."
                    )
                else:
                    message = (
                        "No ATL03 Version 7 granules were discovered for the "
                        "selected area and period. Check the date range and AOI."
                    )
            elif product == "ATL24":
                requested_release = getattr(
                    task,
                    "requested_release",
                    (
                        self.dialog.get_atl24_release()
                        if self.dialog is not None
                        else "002"
                    ),
                )
                release_label = (
                    "Version 2"
                    if str(requested_release) == "002"
                    else "Version 1"
                )
                message = (
                    f"SlideRule found no ATL24 {release_label} records after "
                    "testing the primary request, compatibility syntax and an "
                    "unfiltered class diagnostic.\n\n"
                    "Confirm that the known pass is inside the selected date "
                    "range. If the known file was downloaded from the older "
                    "collection, test ATL24 Version 1 — legacy comparison."
                )
            else:
                message = (
                    f"No {product} data were found inside the selected "
                    "area and date range."
                )

            self.dialog.show_information(
                message
            )
            self.current_task = None
            return

        try:
            layer = self.load_geopackage(
                output_path=task.output_path,
                layer_name=task.layer_name,
                product=product,
            )

            warning_messages = []
            visible_count = task.result_count
            applied_display_field = self.last_display_field

            if product == "ATL24":
                style_applied = self.apply_graduated_style(
                    layer=layer,
                    field_name="depth",
                )

                if not style_applied:
                    warning_messages.append(
                        "Graduated styling could not be applied to depth."
                    )

                if layer.fields().indexOf("index_ph") == -1:
                    warning_messages.append(
                        "index_ph was not returned. The layer is not yet "
                        "ready for exact ATL24-to-ATL03 photon linkage."
                    )

            elif product == "ATL08":
                local_filter_result = (
                    self.apply_atl08_local_filters(
                        layer
                    )
                )

                warning_messages.extend(
                    local_filter_result["warnings"]
                )
                visible_count = local_filter_result[
                    "visible_count"
                ]

                field_result = (
                    self.resolve_atl08_display_field(
                        layer=layer,
                        requested_field=self.last_display_field,
                    )
                )

                applied_display_field = field_result[
                    "field"
                ]

                if field_result["warning"]:
                    warning_messages.append(
                        field_result["warning"]
                    )

                if applied_display_field:
                    style_applied = self.apply_graduated_style(
                        layer=layer,
                        field_name=applied_display_field,
                    )

                    if not style_applied:
                        warning_messages.append(
                            "Graduated styling could not be applied "
                            f"to {applied_display_field}."
                        )

            elif product == "ATL03":
                local_filter_result = (
                    self.apply_atl03_local_filters(layer)
                )

                warning_messages.extend(
                    local_filter_result["warnings"]
                )

                missing_geophysics_fields = [
                    field_name
                    for field_name in self.ATL03_GEOPHYSICS_FIELDS
                    if layer.fields().indexOf(field_name) == -1
                ]

                if missing_geophysics_fields:
                    warning_messages.append(
                        "SlideRule did not return the requested ATL03 "
                        "geophys_corr field(s): "
                        + ", ".join(missing_geophysics_fields)
                        + ". The photon layer was still exported."
                    )
                visible_count = local_filter_result[
                    "visible_count"
                ]

                field_result = self.resolve_atl03_display_field(
                    layer=layer,
                    requested_field=self.last_display_field,
                )

                applied_display_field = field_result["field"]

                if field_result["warning"]:
                    warning_messages.append(
                        field_result["warning"]
                    )

                if applied_display_field:
                    style_applied = self.apply_graduated_style(
                        layer=layer,
                        field_name=applied_display_field,
                    )

                    if not style_applied:
                        warning_messages.append(
                            "Graduated styling could not be applied "
                            f"to {applied_display_field}."
                        )

            elif product == "ATL13":
                local_filter_result = (
                    self.apply_atl13_local_filters(layer)
                )

                warning_messages.extend(
                    local_filter_result["warnings"]
                )
                visible_count = local_filter_result[
                    "visible_count"
                ]

                field_result = self.resolve_atl13_display_field(
                    layer=layer,
                    requested_field=self.last_display_field,
                )

                applied_display_field = field_result["field"]

                if field_result["warning"]:
                    warning_messages.append(
                        field_result["warning"]
                    )

                if applied_display_field:
                    style_applied = self.apply_graduated_style(
                        layer=layer,
                        field_name=applied_display_field,
                    )

                    if not style_applied:
                        warning_messages.append(
                            "Graduated styling could not be applied "
                            f"to {applied_display_field}."
                        )

            report_path = self.export_report(
                task=task,
                layer=layer,
                product=product,
                visible_count=visible_count,
                applied_display_field=applied_display_field,
                warnings=warning_messages,
            )

            self.last_report_path = report_path

            self.dialog.progress_bar.setValue(100)
            self.dialog.status_label.setText(
                f"Completed: {task.result_count:,} records. "
                f"Report: {report_path.name}"
            )

            # Keep the final window short. Detailed metadata are exported.
            self.dialog.show_information(
                f"{product} completed successfully.\n\n"
                f"Records stored: {task.result_count:,}\n"
                f"Report exported to:\n{report_path}"
            )

        except Exception as error:
            self.dialog.status_label.setText(
                "The output or report could not be completed."
            )
            self.dialog.show_error(
                f"{type(error).__name__}: {error}"
            )

        finally:
            self.current_task = None

    def task_terminated(self) -> None:
        task = self.current_task
        self.dialog.set_running(False)

        if task is None:
            return

        if task.isCanceled():
            self.dialog.status_label.setText(
                "Task cancelled."
            )
            self.dialog.progress_bar.setValue(0)
        else:
            self.dialog.status_label.setText(
                "Task failed."
            )

            message = (
                task.error_message
                or "Unknown task error."
            )

            if task.error_traceback:
                message += (
                    "\n\nTechnical details:\n"
                    + task.error_traceback
                )

            self.dialog.show_error(message)

        self.current_task = None

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def export_report(
        self,
        task,
        layer: QgsVectorLayer,
        product: str,
        visible_count: int,
        applied_display_field: str | None,
        warnings: list[str],
    ) -> Path:
        polygon = (
            self.last_parameters.get("poly", [])
            if self.last_parameters
            else []
        )

        returned_fields = [
            field.name()
            for field in layer.fields()
        ]

        scientific_notes = [
            "The GeoPackage stores the returned scientific observations; "
            "the report documents the request and plugin-side operations.",
            "Local QGIS display filters do not remove records from the "
            "GeoPackage.",
        ]

        if product == "ATL24":
            scientific_notes.extend(
                [
                    "The depth field is preserved as produced or derived "
                    "during ATL24 acquisition and is not tide-corrected.",
                    "index_ph is requested to support exact future linkage "
                    "to the source ATL03 photon within the corresponding beam.",
                ]
            )
        elif product == "ATL08":
            scientific_notes.append(
                "h_te_median is a segment-level terrain metric; ATL08 is "
                "not a per-photon terrain product."
            )
        elif product == "ATL03":
            scientific_notes.extend(
                [
                    "ATL03 is a photon-level product. Each row represents an "
                    "individual detected photon returned by the selected "
                    "SlideRule filters.",
                    "height is preserved as the original ellipsoidal photon "
                    "height. The plugin additionally calculates height_ortho as "
                    "height - geoid, referenced to the EGM2008 tide-free geoid.",
                    "tide_ocean is preserved separately and is not applied to "
                    "height or height_ortho.",
                    "geoid, geoid_free2mean and tide_ocean are requested from "
                    "ATL03 /gtx/geophys_corr. They are segment-rate values "
                    "associated with the returned photons and can repeat for "
                    "multiple consecutive photons.",
                    "geoid is the EGM2008 geoid height in the tide-free system. "
                    "geoid_free2mean is an additive conversion term; geoid + "
                    "geoid_free2mean gives the mean-tide geoid value.",
                    "tide_ocean is a modeled short-period ocean-tide correction, "
                    "not an observed water level. It is preserved as supplemental "
                    "information and is not applied automatically to height.",
                    "atl03_cnf is surface-type dependent and is not a universal "
                    "binary signal/noise label. Interpret it together with srt, "
                    "quality_ph, background conditions and the scientific use case.",
                    "ATL03 photon subsets can be very large; the report records "
                    "all server-side and local display filters for reproducibility.",
                    "For large requests, the plugin discovers ATL03 Version 7 "
                    "granules through NASA CMR, processes one granule per request, "
                    "retries interrupted responses and can split an unstable "
                    "granule into individual beam requests before appending the "
                    "results to one GeoPackage.",
                ]
            )
        elif product == "ATL13":
            scientific_notes.extend(
                [
                    "ATL13 provides along-track inland-water segment "
                    "statistics rather than individual photon observations.",
                    "ht_ortho is referenced to EGM2008 and ht_water_surf "
                    "is referenced to the WGS84 ellipsoid.",
                    "water_depth is reported only where a bottom was detected; "
                    "it is not a continuous bathymetric surface.",
                ]
            )

        polygon_wkt = (
            self.sliderule_polygon_to_wkt(
                polygon
            )
            if polygon
            else None
        )

        map_result = render_aoi_overview(
            iface=self.iface,
            polygon_wkt=polygon_wkt,
            excluded_layer_ids={
                layer.id(),
            },
        )

        if map_result.get(
            "warning"
        ):
            warnings.append(
                str(
                    map_result["warning"]
                )
            )

        report_data = {
            "plugin_name": "ICESat-2 Data Explorer",
            "plugin_version": self.PLUGIN_VERSION,
            "qgis_version": Qgis.QGIS_VERSION,
            "product": product,
            "status": "Completed",
            "data_source": "SlideRule Earth",
            "sliderule_endpoint": (
                "atl24x"
                if product == "ATL24"
                else "atl08x"
                if product == "ATL08"
                else "atl03x"
                if product == "ATL03"
                else "atl13x"
                if product == "ATL13"
                else "slideruleearth.io"
            ),
            "product_version_context": (
                (
                    "ATL24 Version "
                    + (
                        "2"
                        if str(
                            getattr(
                                task,
                                "requested_release",
                                "002",
                            )
                        )
                        == "002"
                        else "1"
                    )
                )
                if product == "ATL24"
                else self.PRODUCT_VERSION_CONTEXT.get(
                    product
                )
            ),
            "layer_name": task.layer_name,
            "crs": layer.crs().authid(),
            "record_count": task.result_count,
            "visible_count": visible_count,
            "start_date": self.dialog.get_start_date(),
            "end_date": self.dialog.get_end_date(),
            "area_type": self.current_aoi_type,
            "polygon_wkt": polygon_wkt,
            "aoi_map_data_uri": map_result.get(
                "data_uri"
            ),
            "aoi_map_caption": map_result.get(
                "caption"
            ),
            "display_field": applied_display_field,
            "subset_string": layer.subsetString() or None,
            "returned_fields": returned_fields,
            "field_schema": [
                {
                    "name": field.name(),
                    "type": field.typeName(),
                }
                for field in layer.fields()
            ],
            "server_filters": self.last_server_filters,
            "null_counts": getattr(
                task,
                "null_counts",
                {},
            ),
            "warnings": warnings,
            "scientific_notes": scientific_notes,
            "request_parameters": getattr(
                task,
                "effective_parameters",
                None,
            )
            or self.last_parameters
            or {},
            "request_variant": getattr(
                task,
                "request_variant",
                None,
            ),
            "request_attempts": getattr(
                task,
                "request_attempts",
                [],
            ),
        }

        if product == "ATL24":
            report_data["index_ph_status"] = (
                layer.fields().indexOf("index_ph") != -1
            )

        if product in ("ATL03", "ATL13"):
            report_data["product_statistics"] = getattr(
                task,
                "summary_statistics",
                {},
            )

        if product == "ATL03":
            report_data["category_counts"] = getattr(
                task,
                "category_counts",
                {},
            )
            report_data["processing_strategy"] = getattr(
                task, "processing_strategy", None
            )
            report_data["resource_discovery"] = getattr(
                task, "discovery_variant", None
            )
            report_data["granules_discovered"] = getattr(
                task, "granules_discovered", 0
            )
            report_data["granules_processed"] = getattr(
                task, "granules_processed", 0
            )
            report_data["granules_with_data"] = getattr(
                task, "granules_with_data", 0
            )
            report_data["granules_without_data"] = getattr(
                task, "granules_without_data", 0
            )
            report_data["retry_count"] = getattr(
                task, "retry_count", 0
            )
            report_data["beam_split_resources"] = getattr(
                task, "beam_split_resources", []
            )
            report_data["statistics_note"] = getattr(
                task, "statistics_note", None
            )

        return export_processing_report(
            output_path=task.output_path,
            report_data=report_data,
        )

    # ------------------------------------------------------------------
    # Layer loading
    # ------------------------------------------------------------------

    def load_geopackage(
        self,
        output_path: str,
        layer_name: str,
        product: str,
    ) -> QgsVectorLayer:
        uri = (
            f"{Path(output_path).as_posix()}"
            f"|layername={layer_name}"
        )

        display_name = (
            "ATL24 Bathymetry"
            if product == "ATL24"
            else "ATL08 Segments"
            if product == "ATL08"
            else "ATL03 Photons"
            if product == "ATL03"
            else "ATL13 Inland Water"
            if product == "ATL13"
            else product
        )

        layer = QgsVectorLayer(
            uri,
            display_name,
            "ogr",
        )

        if not layer.isValid():
            raise RuntimeError(
                "The output GeoPackage could not be loaded."
            )

        QgsProject.instance().addMapLayer(layer)
        self.iface.mapCanvas().setExtent(
            layer.extent()
        )
        self.iface.mapCanvas().refresh()

        return layer

    # ------------------------------------------------------------------
    # ATL08 local filters
    # ------------------------------------------------------------------

    def apply_atl08_local_filters(
        self,
        layer: QgsVectorLayer,
    ) -> dict[str, Any]:
        valid_expressions = []
        warnings = []
        filter_definitions = []

        if self.dialog.exclude_invalid_terrain_check.isChecked():
            filter_definitions.append(
                (
                    "h_te_median",
                    '"h_te_median" IS NOT NULL',
                    "The valid-terrain filter was not applied "
                    "because h_te_median was not returned.",
                )
            )

        if self.dialog.exclude_no_ground_check.isChecked():
            filter_definitions.append(
                (
                    "n_te_photons",
                    '"n_te_photons" > 0',
                    "The ground-photon filter was not applied "
                    "because n_te_photons was not returned.",
                )
            )

        if self.dialog.exclude_no_canopy_check.isChecked():
            filter_definitions.append(
                (
                    "n_ca_photons",
                    '"n_ca_photons" > 0',
                    "The canopy-photon filter was not applied "
                    "because n_ca_photons was not returned.",
                )
            )

        if self.dialog.exclude_negative_canopy_check.isChecked():
            filter_definitions.append(
                (
                    "h_canopy",
                    '"h_canopy" >= 0',
                    "The negative-canopy filter was not applied "
                    "because h_canopy was not returned.",
                )
            )

        for required_field, expression, warning in filter_definitions:
            if layer.fields().indexOf(required_field) == -1:
                warnings.append(warning)
            else:
                valid_expressions.append(expression)

        subset_string = " AND ".join(
            valid_expressions
        )

        if subset_string:
            success = layer.setSubsetString(
                subset_string
            )

            if not success:
                warnings.append(
                    "QGIS could not apply one or more "
                    "local display filters."
                )
        else:
            layer.setSubsetString("")

        return {
            "subset_string": layer.subsetString(),
            "visible_count": layer.featureCount(),
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # ATL08 field validation
    # ------------------------------------------------------------------

    def resolve_atl08_display_field(
        self,
        layer: QgsVectorLayer,
        requested_field: str,
    ) -> dict[str, Any]:
        if layer.fields().indexOf(requested_field) != -1:
            return {
                "field": requested_field,
                "warning": None,
            }

        for fallback_field in self.ATL08_FALLBACK_DISPLAY_FIELDS:
            if layer.fields().indexOf(fallback_field) != -1:
                return {
                    "field": fallback_field,
                    "warning": (
                        f"The selected display field "
                        f"'{requested_field}' was not returned. "
                        f"'{fallback_field}' was used instead."
                    ),
                }

        return {
            "field": None,
            "warning": (
                "No supported numeric ATL08 display field "
                "was returned. The layer was loaded without "
                "graduated styling."
            ),
        }

    # ------------------------------------------------------------------
    # ATL03 local filters and field validation
    # ------------------------------------------------------------------

    def apply_atl03_local_filters(
        self,
        layer: QgsVectorLayer,
    ) -> dict[str, Any]:
        valid_expressions = []
        warnings = []
        display_field = self.dialog.get_atl03_display_field()

        if self.dialog.atl03_hide_null_display_check.isChecked():
            if layer.fields().indexOf(display_field) == -1:
                warnings.append(
                    "The selected-value filter was not applied because "
                    f"{display_field} was not returned."
                )
            else:
                valid_expressions.append(
                    f'"{display_field}" IS NOT NULL'
                )

        if self.dialog.atl03_signal_only_check.isChecked():
            if layer.fields().indexOf("atl03_cnf") == -1:
                warnings.append(
                    "The signal-candidate filter was not applied because "
                    "atl03_cnf was not returned."
                )
            else:
                valid_expressions.append(
                    '"atl03_cnf" >= 1'
                )

        subset_string = " AND ".join(valid_expressions)

        if subset_string:
            success = layer.setSubsetString(subset_string)
            if not success:
                warnings.append(
                    "QGIS could not apply one or more ATL03 local filters."
                )
        else:
            layer.setSubsetString("")

        return {
            "subset_string": layer.subsetString(),
            "visible_count": layer.featureCount(),
            "warnings": warnings,
        }

    def resolve_atl03_display_field(
        self,
        layer: QgsVectorLayer,
        requested_field: str,
    ) -> dict[str, Any]:
        if layer.fields().indexOf(requested_field) != -1:
            return {
                "field": requested_field,
                "warning": None,
            }

        for fallback_field in self.ATL03_FALLBACK_DISPLAY_FIELDS:
            if layer.fields().indexOf(fallback_field) != -1:
                return {
                    "field": fallback_field,
                    "warning": (
                        f"The selected ATL03 display field '{requested_field}' "
                        f"was not returned. '{fallback_field}' was used instead."
                    ),
                }

        return {
            "field": None,
            "warning": (
                "No supported numeric ATL03 display field was returned. "
                "The layer was loaded without graduated styling."
            ),
        }

    # ------------------------------------------------------------------
    # ATL13 local filters and field validation
    # ------------------------------------------------------------------

    def apply_atl13_local_filters(
        self,
        layer: QgsVectorLayer,
    ) -> dict[str, Any]:
        valid_expressions = []
        warnings = []

        display_field = self.dialog.get_atl13_display_field()

        if self.dialog.atl13_hide_null_display_check.isChecked():
            if layer.fields().indexOf(display_field) == -1:
                warnings.append(
                    "The selected-value filter was not applied because "
                    f"{display_field} was not returned."
                )
            else:
                valid_expressions.append(
                    f'"{display_field}" IS NOT NULL'
                )

        if self.dialog.atl13_detected_bottom_only_check.isChecked():
            if layer.fields().indexOf("water_depth") == -1:
                warnings.append(
                    "The detected-bottom filter was not applied because "
                    "water_depth was not returned."
                )
            else:
                valid_expressions.append(
                    '"water_depth" IS NOT NULL AND "water_depth" > 0'
                )

        subset_string = " AND ".join(valid_expressions)

        if subset_string:
            success = layer.setSubsetString(subset_string)

            if not success:
                warnings.append(
                    "QGIS could not apply one or more ATL13 local filters."
                )
        else:
            layer.setSubsetString("")

        return {
            "subset_string": layer.subsetString(),
            "visible_count": layer.featureCount(),
            "warnings": warnings,
        }

    def resolve_atl13_display_field(
        self,
        layer: QgsVectorLayer,
        requested_field: str,
    ) -> dict[str, Any]:
        if layer.fields().indexOf(requested_field) != -1:
            return {
                "field": requested_field,
                "warning": None,
            }

        for fallback_field in self.ATL13_FALLBACK_DISPLAY_FIELDS:
            if layer.fields().indexOf(fallback_field) != -1:
                return {
                    "field": fallback_field,
                    "warning": (
                        f"The selected display field '{requested_field}' "
                        f"was not returned. '{fallback_field}' was used instead."
                    ),
                }

        return {
            "field": None,
            "warning": (
                "No supported numeric ATL13 display field was returned. "
                "The layer was loaded without graduated styling."
            ),
        }

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    @staticmethod
    def apply_graduated_style(
        layer: QgsVectorLayer,
        field_name: str,
    ) -> bool:
        field_index = layer.fields().indexOf(
            field_name
        )

        if field_index == -1:
            return False

        minimum = layer.minimumValue(field_index)
        maximum = layer.maximumValue(field_index)

        if minimum is None or maximum is None:
            return False

        try:
            minimum = float(minimum)
            maximum = float(maximum)
        except (TypeError, ValueError):
            return False

        if minimum == maximum:
            return False

        interval_count = 5
        interval_size = (
            maximum - minimum
        ) / interval_count

        if interval_size <= 0:
            return False

        ranges = []

        for index in range(interval_count):
            lower = minimum + index * interval_size
            upper = (
                maximum
                if index == interval_count - 1
                else lower + interval_size
            )

            symbol = QgsSymbol.defaultSymbol(
                layer.geometryType()
            )

            if symbol is None:
                continue

            if hasattr(symbol, "setSize"):
                symbol.setSize(1.2)

            ranges.append(
                QgsRendererRange(
                    lower,
                    upper,
                    symbol,
                    f"{lower:.2f} – {upper:.2f}",
                )
            )

        if not ranges:
            return False

        renderer = QgsGraduatedSymbolRenderer(
            field_name,
            ranges,
        )

        layer.setRenderer(renderer)
        layer.triggerRepaint()

        return True
