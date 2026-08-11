# Testing status

## Validated
- QGIS 3.44.12 LTR on Windows.
- ATL03 Version 7 data access, including large-request resource batching/retry.
- ATL08, ATL13 and ATL24 data access.
- ATL24 Version 2 current/default and Version 1 legacy comparison.
- Interactive profile selection/zoom/exclusion workflows.
- Optional pyTMD/GOT4.10c model-tide workflow.

## Before removing `experimental=True`
- Validate current release on representative Linux distributions.
- Validate current release on macOS.
- Re-test after any QGIS/Python/Qt major-version change.

## Important
The product request builders, ATL03/ATL24 product-version logic, and the SlideRule Python client pin were preserved from the tested v0.10.0 plugin.
