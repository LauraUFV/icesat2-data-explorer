# Changelog

## 0.10.3

- Fixed Windows `h5py` / HDF5 DLL conflicts in the local HDF5 Converter.
- HDF5 files are now read in an isolated QGIS-Python worker process instead of importing `h5py` into the running QGIS process.
- The automatic **Install/Repair HDF5 support** workflow now validates `h5py` in the same isolated environment used for conversion.
- Added explicit selected-polygon instructions and clearer validation messages.
- Added ATL24 selection between bathymetry only (class 40) and all documented classes (0, 1, 40 and 41), including compatibility and diagnostic paths.
- Made the output path editable and updated product-coded filenames predictably when the product changes.
- Added CRS-safe automatic zoom to completed Data Explorer and HDF5 GeoPackage layers.
- Added a large-layer safeguard that keeps the complete HDF5 output but starts layers with 500,000 or more records hidden in QGIS.
- Added ATL24 recovery for interrupted SlideRule responses: bounded retries followed by automatic subdivision of the affected resource batch, without accepting partial data.

## 0.10.2 stable - documentation and local-file tools

- Adds an isolated **HDF5 Converter** module for local ATL03, ATL08, ATL13 and ATL24 granules.
- Adds one-click installation/repair of `h5py` for the active QGIS installation/profile.
- Exports the primary per-photon/per-segment record table to CSV or a WGS 84 GeoPackage while preserving compatible scientific arrays, granule/orbit context and source HDF5 files.
- Adds ATL03 segment-rate geolocation and geophysical values to the corresponding photon rows and derives standard convenience fields such as `height`, `x_atc`, `y_atc` and `gps_seconds` without replacing native fields.
- Labels manual coordinate entry explicitly as decimal-degree longitude/latitude in WGS 84 (EPSG:4326).
- Clarifies that ATL24 `low_confidence_flag` is an ATL24 bathymetry-confidence flag and is not the native ATL03 `signal_conf_ph` field.
- Shortens the QGIS plugin information text and current-version changelog shown in Plugin Manager.
- Expands the user manual with activation, one-time SlideRule support, output saving/export, HDF5 conversion and current interface screenshots.
- Keeps the version number at 0.10.2 and `experimental=False`.

The existing Data Explorer downloads, Interactive Profile, lasso and Model Tide processing implementations are unchanged.

## 0.10.2 - 2026-08-17
- Promoted the fully tested Windows package to the first stable QGIS repository release; functional code is unchanged from the validated 0.10.2 test build.
- Added ATL24 Version 2 resource discovery and automatic batches of at most 250 granules, avoiding SlideRule's 300-resource request limit on broad date/AOI queries.
- Added an explicit WGS 84 / EPSG:4326 note beside the geographic coordinate-entry controls.
- Added freehand lasso selection to Interactive Profile while preserving point and rectangle selection.
- Isolated every ATL03 retry from SlideRule's mutated Arrow-output parameters, preventing a retry from reusing a temporary file whose transfer is still in progress.
- Classified SlideRule Arrow-transfer collisions as transient so the existing retry and per-beam recovery workflow can handle them automatically.
- Preserved ATL24 confidence and quality-filter semantics, including the default minimum confidence of 0.
- Preserved SlideRule 5.5.0, ATL03 scientific parameters and output schema, ATL08, ATL13, ATL24, Model Tide, pyTMD 3.0.9 and GOT4.10c behavior.

## 0.10.1 - 2026-08-13
- Replaced all 50 legacy enum references reported by the QGIS validator with Qt6-compatible scoped enums.
- Resolved all 25 Bandit findings shown by the QGIS repository checker.
- Preserved the SlideRule `pass_invalid=True` request behavior while removing its hardcoded-password false positives.
- Replaced process-output assertions with explicit runtime checks.
- Centralized SQLite identifier quoting for the six dynamically constructed Model Tide queries.
- Documented intentional best-effort exception handling and trusted internal subprocess execution for the security scanner.
- Preserved ATL03, ATL08, ATL13, ATL24, SlideRule 5.5.0, pyTMD 3.0.9 and GOT4.10c processing behavior.

## 0.10.0 - 2026
- Added acquisition date to valid RGT/cycle/beam combinations in Interactive Profile.
- Added user-selectable numeric X/Y profile axes.
- Preserved profile point selection, rectangle selection, zoom, exclusion and restore workflows.
- Improved QComboBox popup selection styling across modules.
- Preserved ATL03 Version 7 and ATL24 Version 2/current plus Version 1 legacy comparison logic.

## 0.9.0
- Added robust large-area ATL03 CMR discovery, granule batching, retry, beam fallback and incremental GeoPackage output.

## 0.8.2
- Corrected ATL08 terrain/canopy quality score controls to the 0-100 scale.
- Added `depth_tide_corrected_m` as a separate model-tide-derived value; original ATL24 `depth` remains unchanged.

## 0.8.1
- Added explicit ATL24 Version 2/current and Version 1 legacy comparison selection and diagnostics.
