# Testing status

## Validated
- QGIS 3.44.12 LTR on Windows.
- ATL03 Version 7 data access and one-granule-at-a-time processing.
- Automated ATL03 retry regression check: each attempt receives an isolated parameter dictionary without a stale SlideRule Arrow-output path.
- ATL08, ATL13 and ATL24 data access.
- ATL24 Version 2 current/default and Version 1 legacy comparison.
- ATL24 Version 2 resource discovery and 250-granule batch boundaries with a 687-granule AOI/date query.
- ATL24 transient-response recovery: interrupted requests are retried and a failed resource batch is split into smaller requests without accepting partial data.
- Interactive profile point/rectangle/lasso selection, zoom and exclusion workflows.
- WGS 84 / EPSG:4326 coordinate-entry guidance in the main dialog.
- Optional pyTMD/GOT4.10c model-tide workflow.
- HDF5 Converter fixtures for ATL03, ATL08, ATL13 and ATL24 detection, CSV export, per-beam row preservation and ATL03 `signal_conf_ph` column expansion.

## Stable release status
- Version 0.10.3 is the corrective stable release based on the HDF5-updated package and the previously validated principal workflows on QGIS 3.44.12 LTR for Windows.
- Linux and macOS have not yet received equivalent functional validation; platform-specific reports should be submitted through the public issue tracker.
- Re-test after any QGIS, Python or Qt major-version change.

## Correction-specific checks
- Selected polygon: active polygon layer plus exactly one selected feature is accepted; zero or multiple selections produce an actionable message.
- ATL24: class 40 bathymetry-only and all-class requests (0, 1, 40 and 41) are passed through the primary, compatibility and broad diagnostic paths.
- Output naming: a product-coded path such as `KimATL03.gpkg` updates to `KimATL08.gpkg`; custom filenames remain editable and are preserved.
- Layer zoom: completed GeoPackage extents are transformed into the current project CRS before the map is zoomed.
- Large HDF5: outputs with at least 500,000 records remain complete while their initial QGIS rendering is disabled.

## Important
The ATL24 Version 2 request supplies explicit granule batches after SlideRule AMS discovery. Transient ATL24 response recovery retries the same request and subdivides only the affected batch; it does not accept partial responses or silently skip failed resources. ATL03 retry isolation changes only transient transfer recovery; scientific request parameters and the output schema remain unchanged. Confidence/quality filters, ATL24 Version 1 legacy comparison, all other product request builders, and the SlideRule Python client 5.5.0 pin remain unchanged.

The HDF5 Converter is additive and loaded lazily. Existing acquisition,
profile, lasso and model-tide code paths are not imported or altered by a
local HDF5 conversion.
