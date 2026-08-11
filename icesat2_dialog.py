from __future__ import annotations

from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
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
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .ui_assets import (
    apply_dialog_theme,
    create_dialog_header,
    icon,
    set_button_icon,
)


class ICESat2Dialog(QDialog):
    """
    Main interface for the ICESat-2 Data Explorer plugin.
    """

    ATL08_DISPLAY_FIELDS = {
        "Canopy height": "h_canopy",
        "Mean canopy height": "h_mean_canopy",
        "Maximum canopy height": "h_max_canopy",
        "Minimum canopy height": "h_min_canopy",
        "Terrain elevation": "h_te_median",
        "Terrain slope": "terrain_slope",
        "Vegetation cover": "segment_cover",
        "Ground photon count": "n_te_photons",
        "Canopy photon count": "n_ca_photons",
        "Canopy openness": "canopy_openness",
    }

    ATL03_DISPLAY_FIELDS = {
        "Photon height — ellipsoidal": "height",
        "Orthometric photon height — EGM2008 tide-free": "height_ortho",
        "Geoid height — EGM2008 tide-free": "geoid",
        "Geoid free-to-mean conversion": "geoid_free2mean",
        "ATL03 ocean tide": "tide_ocean",
        "ATL03 signal confidence": "atl03_cnf",
        "Photon quality code": "quality_ph",
        "Solar elevation": "solar_elevation",
        "Background rate": "background_rate",
        "Along-track distance": "x_atc",
    }

    ATL13_DISPLAY_FIELDS = {
        "Orthometric water-surface height": "ht_ortho",
        "Ellipsoidal water-surface height": "ht_water_surf",
        "Water-surface standard deviation": "stdev_water_surf",
        "Detected water depth": "water_depth",
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "ICESat-2 Data Explorer"
        )
        self.setWindowIcon(icon("plugin.svg"))
        self.setMinimumSize(680, 560)

        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            target_width = min(
                1120,
                max(
                    760,
                    available.width() - 120,
                ),
            )
            target_height = min(
                820,
                max(
                    560,
                    available.height() - 140,
                ),
            )
            self.resize(
                target_width,
                target_height,
            )
        else:
            self.resize(760, 760)

        apply_dialog_theme(self)

        # ------------------------------------------------------------------
        # Product
        # ------------------------------------------------------------------

        self.product_combo = QComboBox()

        self.product_combo.addItems(
            [
                "ATL24",
                "ATL08",
                "ATL03",
                "ATL13",
            ]
        )

        self.data_source_label = QLabel(
            "SlideRule — NASA Earthdata Login not required"
        )

        # ------------------------------------------------------------------
        # Download support
        # ------------------------------------------------------------------

        self.download_support_status_label = QLabel(
            "Checking SlideRule support..."
        )
        self.download_support_status_label.setWordWrap(True)

        self.download_support_button = QPushButton(
            "Install download support"
        )
        set_button_icon(
            self.download_support_button,
            "refresh.svg",
        )

        self.download_support_note = QLabel(
            "Required once per QGIS installation for ATL03, ATL08, ATL13 and ATL24 downloads. "
            "No NASA Earthdata Login is required."
        )
        self.download_support_note.setWordWrap(True)
        self.download_support_note.setProperty("muted", True)

        # ------------------------------------------------------------------
        # Dates
        # ------------------------------------------------------------------

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(
            True
        )
        self.start_date_edit.setDisplayFormat(
            "yyyy-MM-dd"
        )
        self.start_date_edit.setDate(
            QDate(2024, 1, 1)
        )

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(
            True
        )
        self.end_date_edit.setDisplayFormat(
            "yyyy-MM-dd"
        )
        self.end_date_edit.setDate(
            QDate.currentDate()
        )

        # ------------------------------------------------------------------
        # Area of interest
        # ------------------------------------------------------------------

        self.west_spin = (
            self._create_longitude_spin()
        )
        self.south_spin = (
            self._create_latitude_spin()
        )
        self.east_spin = (
            self._create_longitude_spin()
        )
        self.north_spin = (
            self._create_latitude_spin()
        )

        self.west_spin.setValue(
            -35.80
        )
        self.south_spin.setValue(
            -9.80
        )
        self.east_spin.setValue(
            -35.55
        )
        self.north_spin.setValue(
            -9.45
        )

        self.use_extent_button = QPushButton(
            "Use current map extent"
        )

        self.draw_polygon_button = QPushButton(
            "Draw polygon on map"
        )

        self.use_selected_polygon_button = QPushButton(
            "Use selected polygon"
        )

        self.aoi_type_label = QLabel(
            "Area type: bounding box"
        )

        # ------------------------------------------------------------------
        # ATL24 filters
        # ------------------------------------------------------------------

        self.atl24_release_combo = QComboBox()
        self.atl24_release_combo.addItem(
            "Version 2 — current and recommended",
            "002",
        )
        self.atl24_release_combo.addItem(
            "Version 1 — legacy comparison",
            "001",
        )

        self.atl24_release_note = QLabel(
            "ATL24 Version 2 is the current product. Version 1 is retained "
            "only for comparison with previously downloaded granules."
        )
        self.atl24_release_note.setWordWrap(True)
        self.atl24_release_note.setProperty(
            "muted",
            True,
        )

        self.minimum_confidence_spin = (
            QDoubleSpinBox()
        )

        self.minimum_confidence_spin.setRange(
            0.0,
            1.0,
        )
        self.minimum_confidence_spin.setDecimals(
            2
        )
        self.minimum_confidence_spin.setSingleStep(
            0.05
        )
        self.minimum_confidence_spin.setValue(
            0.0
        )

        self.exclude_low_confidence_check = (
            QCheckBox(
                "Exclude low-confidence photons"
            )
        )

        self.exclude_sensor_depth_check = (
            QCheckBox(
                "Exclude sensor-depth-exceeded photons"
            )
        )

        self.exclude_invalid_kd_check = (
            QCheckBox(
                "Exclude photons with invalid Kd"
            )
        )

        self.exclude_invalid_wind_check = (
            QCheckBox(
                "Exclude photons with invalid wind speed"
            )
        )

        # ------------------------------------------------------------------
        # ATL08 server-side filters
        # ------------------------------------------------------------------

        self.terrain_quality_spin = (
            QSpinBox()
        )
        self.terrain_quality_spin.setRange(
            0,
            100,
        )
        self.terrain_quality_spin.setSingleStep(
            5
        )
        self.terrain_quality_spin.setValue(
            0
        )
        self.terrain_quality_spin.setSuffix(
            " / 100"
        )
        self.terrain_quality_spin.setSpecialValueText(
            "Disabled (0)"
        )
        self.terrain_quality_spin.setToolTip(
            "Minimum ATL08 terrain quality-score threshold. "
            "The valid scale is 0–100. Set 0 to disable this "
            "server-side filter."
        )

        self.canopy_quality_spin = (
            QSpinBox()
        )
        self.canopy_quality_spin.setRange(
            0,
            100,
        )
        self.canopy_quality_spin.setSingleStep(
            5
        )
        self.canopy_quality_spin.setValue(
            0
        )
        self.canopy_quality_spin.setSuffix(
            " / 100"
        )
        self.canopy_quality_spin.setSpecialValueText(
            "Disabled (0)"
        )
        self.canopy_quality_spin.setToolTip(
            "Minimum ATL08 canopy quality-score threshold. "
            "The valid scale is 0–100. Set 0 to disable this "
            "server-side filter."
        )

        self.atl08_quality_note = QLabel(
            "ATL08 terrain and canopy quality scores are integer "
            "thresholds from 0 to 100. A value of 0 disables the "
            "corresponding server-side filter; higher thresholds are "
            "more restrictive."
        )
        self.atl08_quality_note.setWordWrap(
            True
        )
        self.atl08_quality_note.setProperty(
            "muted",
            True,
        )

        # ------------------------------------------------------------------
        # ATL08 display
        # ------------------------------------------------------------------

        self.atl08_display_field_combo = (
            QComboBox()
        )

        for label, field_name in (
            self.ATL08_DISPLAY_FIELDS.items()
        ):
            self.atl08_display_field_combo.addItem(
                label,
                field_name,
            )

        # ------------------------------------------------------------------
        # ATL08 local display filters
        # ------------------------------------------------------------------

        self.exclude_invalid_terrain_check = (
            QCheckBox(
                "Hide segments without valid terrain elevation"
            )
        )

        self.exclude_no_ground_check = (
            QCheckBox(
                "Hide segments without ground photons"
            )
        )

        self.exclude_no_canopy_check = (
            QCheckBox(
                "Hide segments without canopy photons"
            )
        )

        self.exclude_negative_canopy_check = (
            QCheckBox(
                "Hide negative canopy heights"
            )
        )

        self.local_filter_note = QLabel(
            "Local display filters hide records in QGIS "
            "but do not remove them from the GeoPackage."
        )

        self.local_filter_note.setWordWrap(
            True
        )

        # ------------------------------------------------------------------
        # ATL03 photon selection, display and local filters
        # ------------------------------------------------------------------

        self.atl03_surface_type_combo = QComboBox()
        self.atl03_surface_type_combo.addItem(
            "Dynamic / all surface types",
            -1,
        )
        self.atl03_surface_type_combo.addItem("Land", 0)
        self.atl03_surface_type_combo.addItem("Ocean", 1)
        self.atl03_surface_type_combo.addItem("Sea ice", 2)
        self.atl03_surface_type_combo.addItem("Land ice", 3)
        self.atl03_surface_type_combo.addItem("Inland water", 4)

        self.atl03_confidence_combo = QComboBox()
        self.atl03_confidence_combo.addItem(
            "No native confidence filter (exclude possible TEP)",
            -1,
        )
        self.atl03_confidence_combo.addItem(
            "All photons including possible TEP",
            -2,
        )
        self.atl03_confidence_combo.addItem(
            "Background/noise and higher",
            0,
        )
        self.atl03_confidence_combo.addItem(
            "Within 10 m and higher",
            1,
        )
        self.atl03_confidence_combo.addItem(
            "Low confidence and higher",
            2,
        )
        self.atl03_confidence_combo.addItem(
            "Medium confidence and higher",
            3,
        )
        self.atl03_confidence_combo.addItem(
            "High confidence only",
            4,
        )

        self.atl03_quality_combo = QComboBox()
        self.atl03_quality_combo.addItem(
            "All photon-quality classes",
            [0, 1, 2, 3],
        )
        self.atl03_quality_combo.addItem(
            "Nominal photons only",
            [0],
        )

        self.atl03_display_field_combo = QComboBox()
        for label, field_name in self.ATL03_DISPLAY_FIELDS.items():
            self.atl03_display_field_combo.addItem(
                label,
                field_name,
            )

        self.atl03_hide_null_display_check = QCheckBox(
            "Hide photons without a valid selected display value"
        )

        self.atl03_signal_only_check = QCheckBox(
            "Show only signal candidates (atl03_cnf >= 1)"
        )

        self.atl03_filter_note = QLabel(
            "ATL03 can contain very large numbers of photons. Use a small "
            "AOI and an appropriate confidence threshold for the first test. "
            "Local display filters do not remove records from the GeoPackage."
        )
        self.atl03_filter_note.setWordWrap(True)

        # ------------------------------------------------------------------
        # ATL13 display and local filters
        # ------------------------------------------------------------------

        self.atl13_display_field_combo = QComboBox()

        for label, field_name in self.ATL13_DISPLAY_FIELDS.items():
            self.atl13_display_field_combo.addItem(
                label,
                field_name,
            )

        self.atl13_hide_null_display_check = QCheckBox(
            "Hide segments without a valid selected display value"
        )

        self.atl13_detected_bottom_only_check = QCheckBox(
            "Show only segments with detected positive water depth"
        )

        self.atl13_filter_note = QLabel(
            "ATL13 filters are applied locally in QGIS and do not remove "
            "records from the GeoPackage."
        )
        self.atl13_filter_note.setWordWrap(True)

        # ------------------------------------------------------------------
        # Product filter stack
        # ------------------------------------------------------------------

        self.filter_stack = QStackedWidget()

        self.atl24_filter_page = (
            self._create_atl24_filter_page()
        )

        self.atl08_filter_page = (
            self._create_atl08_filter_page()
        )

        self.atl03_filter_page = (
            self._create_atl03_filter_page()
        )

        self.atl13_filter_page = (
            self._create_atl13_filter_page()
        )

        self.pending_filter_page = (
            self._create_pending_filter_page()
        )

        self.filter_stack.addWidget(
            self.atl24_filter_page
        )

        self.filter_stack.addWidget(
            self.atl08_filter_page
        )

        self.filter_stack.addWidget(
            self.atl03_filter_page
        )

        self.filter_stack.addWidget(
            self.atl13_filter_page
        )

        self.filter_stack.addWidget(
            self.pending_filter_page
        )

        # ------------------------------------------------------------------
        # Output
        # ------------------------------------------------------------------

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(
            True
        )

        self.browse_button = QPushButton(
            "Browse..."
        )

        self.browse_button.clicked.connect(
            self.select_output_file
        )

        # ------------------------------------------------------------------
        # Status
        # ------------------------------------------------------------------

        self.status_label = QLabel(
            "Ready."
        )

        self.status_label.setWordWrap(
            True
        )

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(
            0,
            100,
        )
        self.progress_bar.setValue(
            0
        )

        # ------------------------------------------------------------------
        # Buttons
        # ------------------------------------------------------------------

        self.run_button = QPushButton(
            "Download ATL24 bathymetry"
        )

        self.cancel_button = QPushButton(
            "Cancel"
        )
        self.cancel_button.setEnabled(
            False
        )

        self.close_button = QPushButton(
            "Close"
        )
        self.close_button.clicked.connect(
            self.close
        )

        set_button_icon(self.use_extent_button, "map_extent.svg")
        set_button_icon(self.draw_polygon_button, "polygon.svg")
        set_button_icon(self.use_selected_polygon_button, "selection.svg")
        set_button_icon(self.browse_button, "folder.svg")
        set_button_icon(self.run_button, "run.svg")
        set_button_icon(self.close_button, "close.svg")
        self.run_button.setProperty("primary", True)

        self._build_layout()

        self.product_combo.currentTextChanged.connect(
            self.update_product_interface
        )

        self.update_product_interface(
            self.product_combo.currentText()
        )

    @staticmethod
    def _create_longitude_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(
            -180.0,
            180.0,
        )
        spin.setDecimals(
            8
        )
        spin.setSingleStep(
            0.01
        )
        return spin

    @staticmethod
    def _create_latitude_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(
            -90.0,
            90.0,
        )
        spin.setDecimals(
            8
        )
        spin.setSingleStep(
            0.01
        )
        return spin

    def _create_atl24_filter_page(
        self,
    ) -> QWidget:
        page = QWidget()
        layout = QFormLayout(
            page
        )

        layout.addRow(
            "ATL24 release:",
            self.atl24_release_combo,
        )
        layout.addRow(
            "",
            self.atl24_release_note,
        )

        layout.addRow(
            "Minimum confidence:",
            self.minimum_confidence_spin,
        )

        layout.addRow(
            self.exclude_low_confidence_check
        )

        layout.addRow(
            self.exclude_sensor_depth_check
        )

        layout.addRow(
            self.exclude_invalid_kd_check
        )

        layout.addRow(
            self.exclude_invalid_wind_check
        )

        return page

    def _create_atl08_filter_page(
        self,
    ) -> QWidget:
        page = QWidget()
        main_layout = QVBoxLayout(
            page
        )

        server_group = QGroupBox(
            "Server-side filters"
        )

        server_layout = QFormLayout(
            server_group
        )

        server_layout.addRow(
            "Minimum terrain quality score:",
            self.terrain_quality_spin,
        )

        server_layout.addRow(
            "Minimum canopy quality score:",
            self.canopy_quality_spin,
        )

        server_layout.addRow(
            "",
            self.atl08_quality_note,
        )

        main_layout.addWidget(
            server_group
        )

        display_group = QGroupBox(
            "ATL08 display"
        )

        display_layout = QFormLayout(
            display_group
        )

        display_layout.addRow(
            "Display field:",
            self.atl08_display_field_combo,
        )

        main_layout.addWidget(
            display_group
        )

        local_group = QGroupBox(
            "Local display filters"
        )

        local_layout = QVBoxLayout(
            local_group
        )

        local_layout.addWidget(
            self.exclude_invalid_terrain_check
        )

        local_layout.addWidget(
            self.exclude_no_ground_check
        )

        local_layout.addWidget(
            self.exclude_no_canopy_check
        )

        local_layout.addWidget(
            self.exclude_negative_canopy_check
        )

        local_layout.addWidget(
            self.local_filter_note
        )

        main_layout.addWidget(
            local_group
        )

        return page

    def _create_atl03_filter_page(
        self,
    ) -> QWidget:
        page = QWidget()
        main_layout = QVBoxLayout(page)

        server_group = QGroupBox(
            "Server-side photon selection"
        )
        server_layout = QFormLayout(server_group)
        server_layout.addRow(
            "Surface type:",
            self.atl03_surface_type_combo,
        )
        server_layout.addRow(
            "Minimum confidence:",
            self.atl03_confidence_combo,
        )
        server_layout.addRow(
            "Photon quality:",
            self.atl03_quality_combo,
        )
        main_layout.addWidget(server_group)

        display_group = QGroupBox(
            "ATL03 display"
        )
        display_layout = QFormLayout(display_group)
        display_layout.addRow(
            "Display field:",
            self.atl03_display_field_combo,
        )
        main_layout.addWidget(display_group)

        local_group = QGroupBox(
            "Local display filters"
        )
        local_layout = QVBoxLayout(local_group)
        local_layout.addWidget(
            self.atl03_hide_null_display_check
        )
        local_layout.addWidget(
            self.atl03_signal_only_check
        )
        local_layout.addWidget(
            self.atl03_filter_note
        )
        main_layout.addWidget(local_group)

        return page

    def _create_atl13_filter_page(
        self,
    ) -> QWidget:
        page = QWidget()
        main_layout = QVBoxLayout(page)

        display_group = QGroupBox(
            "ATL13 display"
        )
        display_layout = QFormLayout(display_group)
        display_layout.addRow(
            "Display field:",
            self.atl13_display_field_combo,
        )
        main_layout.addWidget(display_group)

        local_group = QGroupBox(
            "Local display filters"
        )
        local_layout = QVBoxLayout(local_group)
        local_layout.addWidget(
            self.atl13_hide_null_display_check
        )
        local_layout.addWidget(
            self.atl13_detected_bottom_only_check
        )
        local_layout.addWidget(
            self.atl13_filter_note
        )
        main_layout.addWidget(local_group)

        return page

    @staticmethod
    def _create_pending_filter_page() -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(
            page
        )

        label = QLabel(
            "This product has not been implemented yet."
        )

        label.setWordWrap(
            True
        )

        layout.addWidget(
            label
        )

        return page

    def _build_layout(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(11)

        main_layout.addWidget(
            create_dialog_header(
                "ICESat-2 Data Explorer",
                "Download, document and visualize ICESat-2 products in QGIS.",
                "plugin.svg",
                "v0.10.0",
            )
        )

        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("ICESat2MainScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )

        content_widget = QWidget()
        content_widget.setObjectName("ICESat2MainScrollContent")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(11)

        selection_group = QGroupBox("Data selection")
        selection_layout = QGridLayout(selection_group)
        selection_layout.setColumnStretch(1, 1)
        selection_layout.setColumnStretch(3, 1)

        selection_layout.addWidget(QLabel("Product:"), 0, 0)
        selection_layout.addWidget(self.product_combo, 0, 1)

        self.product_badge = QLabel("ATL24")
        self.product_badge.setObjectName("ICESat2ProductBadge")
        self.product_badge.setAlignment(Qt.AlignCenter)
        selection_layout.addWidget(self.product_badge, 0, 2)
        selection_layout.addWidget(self.data_source_label, 0, 3)

        selection_layout.addWidget(QLabel("Start date:"), 1, 0)
        selection_layout.addWidget(self.start_date_edit, 1, 1)
        selection_layout.addWidget(QLabel("End date:"), 1, 2)
        selection_layout.addWidget(self.end_date_edit, 1, 3)

        content_layout.addWidget(selection_group)

        support_group = QGroupBox("Download support")
        support_layout = QGridLayout(support_group)
        support_layout.setColumnStretch(0, 1)
        support_layout.addWidget(
            self.download_support_status_label,
            0,
            0,
        )
        support_layout.addWidget(
            self.download_support_button,
            0,
            1,
        )
        support_layout.addWidget(
            self.download_support_note,
            1,
            0,
            1,
            2,
        )
        content_layout.addWidget(support_group)

        area_group = QGroupBox("Area of interest")
        area_layout = QVBoxLayout(area_group)

        coordinates = QGridLayout()
        coordinates.addWidget(QLabel("West:"), 0, 0)
        coordinates.addWidget(self.west_spin, 0, 1)
        coordinates.addWidget(QLabel("East:"), 0, 2)
        coordinates.addWidget(self.east_spin, 0, 3)
        coordinates.addWidget(QLabel("South:"), 1, 0)
        coordinates.addWidget(self.south_spin, 1, 1)
        coordinates.addWidget(QLabel("North:"), 1, 2)
        coordinates.addWidget(self.north_spin, 1, 3)
        coordinates.setColumnStretch(1, 1)
        coordinates.setColumnStretch(3, 1)
        area_layout.addLayout(coordinates)

        area_buttons = QHBoxLayout()
        area_buttons.addWidget(self.use_extent_button)
        area_buttons.addWidget(self.draw_polygon_button)
        area_buttons.addWidget(self.use_selected_polygon_button)
        area_layout.addLayout(area_buttons)

        self.aoi_type_label.setProperty("muted", True)
        area_layout.addWidget(self.aoi_type_label)
        content_layout.addWidget(area_group)

        self.product_settings_group = QGroupBox("ATL24 settings")
        filter_layout = QVBoxLayout(self.product_settings_group)
        filter_layout.addWidget(self.filter_stack)
        content_layout.addWidget(self.product_settings_group)

        output_group = QGroupBox("Output")
        output_layout = QFormLayout(output_group)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_path_edit, 1)
        output_row.addWidget(self.browse_button)
        output_layout.addRow("Output GeoPackage:", output_row)
        content_layout.addWidget(output_group)

        content_layout.addStretch(1)

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area, 1)

        status_panel = QFrame()
        status_panel.setObjectName("ICESat2StatusPanel")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(10, 8, 10, 8)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        main_layout.addWidget(status_panel)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.close_button)
        main_layout.addLayout(button_layout)

    def update_product_interface(
        self,
        product: str,
    ) -> None:
        """
        Update product-specific controls.
        """
        product_colors = {
            "ATL03": "#7b5aa6",
            "ATL08": "#4f8f32",
            "ATL13": "#197fa3",
            "ATL24": "#0f6688",
        }

        if hasattr(self, "product_badge"):
            self.product_badge.setText(product)
            self.product_badge.setStyleSheet(
                "background: "
                + product_colors.get(product, "#61717c")
                + "; color: white; font-weight: 700; "
                  "padding: 4px 10px; border-radius: 9px;"
            )

        if hasattr(self, "product_settings_group"):
            self.product_settings_group.setTitle(
                f"{product} settings"
            )
        if product == "ATL24":
            self.filter_stack.setCurrentWidget(
                self.atl24_filter_page
            )

            self.run_button.setText(
                "Download ATL24 bathymetry"
            )

            self.run_button.setEnabled(
                True
            )

        elif product == "ATL08":
            self.filter_stack.setCurrentWidget(
                self.atl08_filter_page
            )

            self.run_button.setText(
                "Download ATL08 segments"
            )

            self.run_button.setEnabled(
                True
            )

        elif product == "ATL03":
            self.filter_stack.setCurrentWidget(
                self.atl03_filter_page
            )

            self.run_button.setText(
                "Download ATL03 photons"
            )

            self.run_button.setEnabled(
                True
            )

        elif product == "ATL13":
            self.filter_stack.setCurrentWidget(
                self.atl13_filter_page
            )

            self.run_button.setText(
                "Download ATL13 inland-water segments"
            )

            self.run_button.setEnabled(
                True
            )

        else:
            self.filter_stack.setCurrentWidget(
                self.pending_filter_page
            )

            self.run_button.setText(
                f"{product} is not implemented yet"
            )

            self.run_button.setEnabled(
                False
            )

    def select_output_file(self) -> None:
        product = (
            self.product_combo.currentText()
        )

        default_name = (
            f"{product}_output.gpkg"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select output GeoPackage",
            default_name,
            "GeoPackage (*.gpkg)",
        )

        if not file_path:
            return

        if not file_path.lower().endswith(
            ".gpkg"
        ):
            file_path += ".gpkg"

        self.output_path_edit.setText(
            file_path
        )

    def get_selected_product(self) -> str:
        return (
            self.product_combo.currentText()
        )

    def get_atl24_release(self) -> str:
        release = self.atl24_release_combo.currentData()
        return str(
            release
            or "002"
        )

    def get_atl08_display_field(
        self,
    ) -> str:
        """
        Return the ATL08 field name selected for styling.
        """
        field_name = (
            self.atl08_display_field_combo
            .currentData()
        )

        return str(field_name)

    def get_atl08_display_label(
        self,
    ) -> str:
        return (
            self.atl08_display_field_combo
            .currentText()
        )

    def get_atl03_surface_type(self) -> int:
        return int(
            self.atl03_surface_type_combo.currentData()
        )

    def get_atl03_confidence(self) -> int:
        return int(
            self.atl03_confidence_combo.currentData()
        )

    def get_atl03_quality(self) -> list[int]:
        value = self.atl03_quality_combo.currentData()

        if isinstance(value, (list, tuple)):
            return [
                int(item)
                for item in value
            ]

        return [int(value)]

    def get_atl03_display_field(self) -> str:
        return str(
            self.atl03_display_field_combo.currentData()
        )

    def get_atl03_display_label(self) -> str:
        return self.atl03_display_field_combo.currentText()

    def get_atl13_display_field(
        self,
    ) -> str:
        return str(
            self.atl13_display_field_combo.currentData()
        )

    def get_atl13_display_label(
        self,
    ) -> str:
        return self.atl13_display_field_combo.currentText()

    def get_bounding_box(
        self,
    ) -> tuple[
        float,
        float,
        float,
        float,
    ]:
        return (
            self.west_spin.value(),
            self.south_spin.value(),
            self.east_spin.value(),
            self.north_spin.value(),
        )

    def set_bounding_box(
        self,
        bounding_box,
    ) -> None:
        west, south, east, north = (
            bounding_box
        )

        self.west_spin.setValue(
            west
        )
        self.south_spin.setValue(
            south
        )
        self.east_spin.setValue(
            east
        )
        self.north_spin.setValue(
            north
        )

    def set_download_support_status(
        self,
        state: str,
        details: str,
        version: str | None = None,
    ) -> None:
        if state == "ready":
            version_text = (
                f" {version}"
                if version
                else ""
            )
            self.download_support_status_label.setText(
                f"Installed — SlideRule{version_text}"
            )
            self.download_support_button.setText(
                "Repair download support"
            )
        elif state == "broken":
            self.download_support_status_label.setText(
                "Repair required"
            )
            self.download_support_button.setText(
                "Repair download support"
            )
        else:
            self.download_support_status_label.setText(
                "Not installed"
            )
            self.download_support_button.setText(
                "Install download support"
            )

        self.download_support_status_label.setToolTip(
            details
        )

    def set_download_support_installing(
        self,
        installing: bool,
    ) -> None:
        self.download_support_button.setEnabled(
            not installing
        )

        if installing:
            self.download_support_status_label.setText(
                "Installing SlideRule download support..."
            )

    def get_start_date(self) -> str:
        return (
            self.start_date_edit
            .date()
            .toString("yyyy-MM-dd")
            + "T00:00:00Z"
        )

    def get_end_date(self) -> str:
        return (
            self.end_date_edit
            .date()
            .toString("yyyy-MM-dd")
            + "T23:59:59Z"
        )

    def get_output_path(self) -> str:
        return (
            self.output_path_edit
            .text()
            .strip()
        )

    def set_running(
        self,
        running: bool,
    ) -> None:
        self.cancel_button.setEnabled(
            running
        )

        self.close_button.setEnabled(
            not running
        )

        self.product_combo.setEnabled(
            not running
        )

        self.start_date_edit.setEnabled(
            not running
        )

        self.end_date_edit.setEnabled(
            not running
        )

        self.use_extent_button.setEnabled(
            not running
        )

        self.draw_polygon_button.setEnabled(
            not running
        )

        self.use_selected_polygon_button.setEnabled(
            not running
        )

        self.browse_button.setEnabled(
            not running
        )

        self.download_support_button.setEnabled(
            not running
        )

        if running:
            self.run_button.setEnabled(
                False
            )
        else:
            product = self.get_selected_product()

            self.run_button.setEnabled(
                product in (
                    "ATL24",
                    "ATL08",
                    "ATL03",
                    "ATL13",
                )
            )

    def show_error(
        self,
        message: str,
    ) -> None:
        QMessageBox.critical(
            self,
            "ICESat-2 Data Explorer",
            message,
        )

    def show_information(
        self,
        message: str,
    ) -> None:
        QMessageBox.information(
            self,
            "ICESat-2 Data Explorer",
            message,
        )

    def show_warning(
        self,
        message: str,
    ) -> None:
        QMessageBox.warning(
            self,
            "ICESat-2 Data Explorer",
            message,
        )