# ICESat-2 Data Explorer

**QGIS plugin for direct access, inspection and analysis of ICESat-2 ATL03, ATL08, ATL13 and ATL24 products.**

Version: **0.10.0**  
License: **GPL-2.0-or-later**  
Status: **Experimental**  
Minimum QGIS version: **3.44** (maximum 3.99)

## Main capabilities

- Download/subset **ATL03 Version 7**, ATL08, ATL13 and **ATL24 Version 2** through SlideRule.
- Retain **ATL24 Version 1** as an explicit legacy comparison option; the plugin never silently mixes ATL24 releases.
- Robust large-area ATL03 processing: NASA CMR resource discovery, one-granule requests, retry on transient failures, optional per-beam fallback, and incremental GeoPackage writing.
- Draw an AOI or use the current QGIS map extent.
- Create interactive profiles by valid **date + RGT + cycle + beam** combinations.
- Choose numeric fields for X and Y axes while preserving point selection, rectangle selection, map synchronization, zoom, temporary exclusion and restore.
- Export GeoPackage layers and structured HTML provenance reports.
- Optionally evaluate **GOT4.10c** at ATL24 photon positions/times using **pyTMD** in an isolated environment. The source ATL24 `depth` is preserved; `depth_tide_corrected_m = depth - tide_ocean_model_m` is written separately and is not a chart-datum transformation.

## Installation

### QGIS Plugin Repository
After the plugin is approved, install it from **Plugins > Manage and Install Plugins**.

### ZIP during testing
Use **Plugins > Manage and Install Plugins > Install from ZIP** and select the release ZIP.

On first data download the plugin offers to install the SlideRule Python client into plugin-managed user storage. The optional Model Tide module similarly creates an isolated pyTMD environment and can download GOT4.10c at runtime.

## External dependencies

The plugin does **not** bundle third-party Python binaries or tide-model files.

- SlideRule Python client **5.5.0** (BSD-3-Clause), installed on demand into plugin-managed storage.
- pyTMD **3.0.9** (MIT), optional and installed into an isolated environment for model-tide calculations.
- h5py, h5netcdf and Dask are installed only inside the optional tide environment as required by that workflow.
- NumPy, pandas and GeoPandas are expected from a compatible QGIS Python environment and are checked, not upgraded by the SlideRule installer.

See `THIRD_PARTY_NOTICES.md` for licensing/provenance notes.

## Tested environment

Functional validation has been performed on **QGIS 3.44.12 LTR, Windows**. QGIS 3.30 is intentionally unsupported for automatic dependency setup because some Windows distributions cannot expose a usable SSL module to the external Python process used by pip. Linux and macOS packaging should be validated before the plugin is marked non-experimental.

## Outputs and reproducibility

Each processing workflow records request parameters, product/release context, source fields and quality/filter settings. Reports use the compact citation **Andrade et al. (2026)** and retain the full author list in the source code.

## Authors

- Laura Coelho de Andrade
- Kim Earle Lowell
- Nilcilene das Gracas Medeiros
- Arthur Amaral e Silva
- Italo Oliveira Ferreira

## Citation

A GEOINFO 2026 tools paper is being prepared. Until publication, cite the software as described in `CITATION.cff`.

## Source, issues and documentation

**Before publication in the QGIS repository, replace the repository placeholders in `metadata.txt` with the public source repository and issue tracker URLs.**

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Manual do Usuário - Português](docs/USER_GUIDE_pt-BR.md)
- [PDF User Manual](docs/ICESat2_Data_Explorer_User_Manual_v0.10.0.pdf)
- [Manual do Usuário - PDF](docs/ICESat2_Data_Explorer_Manual_do_Usuario_v0.10.0.pdf)

The User Guide covers installation, ATL03/ATL08/ATL13/ATL24 acquisition, interactive profile tools, model tide processing, reports, and troubleshooting.
