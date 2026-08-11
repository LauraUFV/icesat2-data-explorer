# Changelog

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
