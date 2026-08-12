# ICESat-2 Data Explorer - User Guide

Version 0.10.0

Software authors: Laura Coelho de Andrade; Kim Earle Lowell; Nilcilene das Graças Medeiros; Arthur Amaral e Silva; Italo Oliveira Ferreira.

Recommended short citation: Andrade et al. (2026), *ICESat-2 Data Explorer*.

## 1\. Purpose

ICESat-2 Data Explorer is a QGIS plugin for accessing, visualizing, documenting, and analyzing selected ICESat-2 products directly inside QGIS. Version 0.10.0 supports ATL03, ATL08, ATL13, and ATL24 workflows through SlideRule, includes an interactive profile viewer, generates HTML processing reports, and provides an optional model-tide workflow for ATL24 using GOT4.10c through pyTMD.

The plugin is designed so that data acquisition, visualization, profile inspection, and provenance reporting remain in a single GIS environment.

## 2\. Compatibility and requirements

* QGIS 3.44 or later.
* QGIS 3.44 is the recommended and tested family for this release.
* QGIS 3.30 is not supported for automatic SlideRule setup because its bundled Python environment may fail to provide a usable SSL module.
* Internet access is required for SlideRule installation and ICESat-2 data requests.
* A NASA Earthdata Login is not required by the plugin's SlideRule download workflow.
* Model tide support is optional and is managed separately from the SlideRule download support.

### Supported products

|Product|Main purpose in the plugin|Current behavior|
|-|-|-|
|ATL03|Photon-level geolocated data|Explicitly requests ATL03 Version 7 and can retrieve geoid and ocean-tide ancillary fields. Large requests are processed by granule with retry and beam fallback.|
|ATL08|Land and vegetation segments|Supports terrain/canopy display and server-side quality-score thresholds from 0 to 100.|
|ATL13|Inland-water segments|Supports water-surface and detected-water-depth visualization with local display filtering.|
|ATL24|Coastal and nearshore bathymetry|Version 2 is the current/default option. Version 1 is retained as a legacy comparison option.|

## 3\. Installation

### 3.1 Install the plugin from ZIP

1. Open QGIS.
2. Open **Plugins > Manage and Install Plugins**.
3. Choose **Install from ZIP**.
4. Select the ICESat-2 Data Explorer ZIP file.
5. Enable **ICESat-2 Data Explorer**.
6. Open the plugin from **Plugins > ICESat-2 Data Explorer > Data Explorer**.

The plugin menu contains four entries:

* **Data Explorer**
* **Interactive Profile**
* **Model Tide Values**
* **About**

### 3.2 First-time download support

On a new QGIS installation, the SlideRule Python client must be set up once.

1. Open **Data Explorer**.
2. In **Download support**, click **Install download support**.
3. Wait until the status confirms that the managed SlideRule support is ready.
4. The same support is then used for ATL03, ATL08, ATL13, and ATL24 downloads.

The plugin manages this support outside the plugin source folder. This helps keep the plugin package portable and avoids unnecessarily modifying the scientific Python packages shipped with QGIS.

## 4\. Data Explorer overview

The Data Explorer is the main acquisition module. A typical workflow is:

1. Select the ICESat-2 product.
2. Select the start and end dates.
3. Define the area of interest.
4. Configure product-specific settings.
5. Choose an output GeoPackage.
6. Run the download.
7. Inspect the resulting QGIS layer and the associated HTML report.

### 4.1 Date range

Dates are entered as `YYYY-MM-DD`. The selected period is sent with the data request and is also recorded in the report.

For broad ATL03 searches, a long date range can intersect many granules. Version 0.10.0 preserves the large-area strategy introduced earlier: CMR resource discovery, one-granule-at-a-time processing, retry of interrupted responses, per-beam fallback when needed, and incremental GeoPackage writing.

### 4.2 Area of interest

The coordinate boxes use geographic longitude and latitude in decimal degrees:

* **West**: western longitude
* **East**: eastern longitude
* **South**: southern latitude
* **North**: northern latitude

These values are not UTM eastings or northings.

The user can define the AOI using one of three approaches:

* **Use current map extent**: adopts the visible map extent.
* **Draw polygon on map**: interactively draws an AOI.
* **Use selected polygon**: uses a selected polygon feature already present in QGIS.

The exact request geometry is retained for provenance in the processing report. The report can also include an AOI overview rendered from the visible QGIS project layers.

## 5\. ATL24 bathymetry

Choose **ATL24** in the Product selector.

### 5.1 ATL24 release

Two explicit choices are available:

* **Version 2 - current and recommended**
* **Version 1 - legacy comparison**

Version 2 should normally be used for new analyses. Version 1 is provided so that previously downloaded or known legacy results can be compared without silently mixing product releases.

### 5.2 ATL24 filters

**Minimum confidence** accepts values from 0.00 to 1.00. A value of 0.00 is the most permissive setting.

Optional exclusion controls are available for:

* low-confidence photons;
* sensor-depth-exceeded photons;
* photons with invalid Kd;
* photons with invalid wind speed.

For diagnostic tests in an area where bathymetry is known to exist, start with **Minimum confidence = 0.00** and leave all exclusion options unchecked. More restrictive filters can be applied after confirming data availability.

### 5.3 ATL24 output

The output is a GeoPackage containing the ATL24 records returned by the request and the attributes supplied by SlideRule. The GeoPackage can later be used in the Interactive Profile and Model Tide Values modules.

## 6\. ATL08 land and vegetation segments

Choose **ATL08** in the Product selector.

### 6.1 Server-side quality filters

Two quality-score thresholds are available:

* **Minimum terrain quality score**
* **Minimum canopy quality score**

Both use an integer scale from 0 to 100. A value of **0 disables the corresponding server-side filter**. Higher values are more restrictive.

These are server-side filters: records that do not satisfy the selected threshold are not returned by the SlideRule request.

### 6.2 Display field

The display field controls which attribute is used to style the resulting layer in QGIS. Available choices include:

* canopy height;
* mean canopy height;
* maximum canopy height;
* minimum canopy height;
* terrain elevation;
* terrain slope;
* vegetation cover;
* ground photon count;
* canopy photon count;
* canopy openness.

### 6.3 Local display filters

Local filters affect the QGIS visualization but do not delete records from the GeoPackage. Options include hiding:

* segments without valid terrain elevation;
* segments without ground photons;
* segments without canopy photons;
* negative canopy heights.

This distinction is important: **server-side filters change the downloaded dataset; local display filters only change what is visible in QGIS**.

## 7\. ATL03 photon-level data

Choose **ATL03** in the Product selector.

ATL03 can contain very large numbers of individual photons. For the first test in a new study area, a smaller AOI or narrower time range is recommended.

### 7.1 Surface type

The available native surface-type choices are:

* Dynamic / all surface types
* Land
* Ocean
* Sea ice
* Land ice
* Inland water

In coastal environments, a known pass may not necessarily be returned under the surface type a user intuitively expects. The plugin retains diagnostic logic that can test permissive Land, Ocean, and Inland-water settings when needed.

### 7.2 Minimum confidence

Available choices range from no native confidence filter to high-confidence-only selection. The interface also provides a permissive option that includes possible TEP photons.

### 7.3 Photon quality

Two main choices are available:

* **All photon-quality classes**
* **Nominal photons only**

### 7.4 Display and local filters

The display field can include photon height, orthometric photon height, geoid, geoid free-to-mean conversion, ATL03 ocean tide, signal confidence, photon quality, solar elevation, background rate, and along-track distance.

Local display options can hide photons without a valid display value or show only signal candidates. These options do not remove records from the GeoPackage.

### 7.5 Large-area ATL03 processing

Version 0.10.0 retains robust large-request handling:

1. Discover ATL03 Version 7 granules through NASA CMR.
2. Process one granule at a time using the exact AOI.
3. Retry transiently interrupted SlideRule responses.
4. If a full-granule stream remains unstable, split that granule into individual beams.
5. Append successful chunks incrementally to a temporary GeoPackage.
6. Commit the final GeoPackage only when the task completes successfully.

This workflow is intended to reduce failures such as `Unexpected termination of response` on larger photon requests.

## 8\. ATL13 inland-water data

Choose **ATL13** in the Product selector.

The display field can be set to:

* orthometric water-surface height;
* ellipsoidal water-surface height;
* water-surface standard deviation;
* detected water depth.

Local display options can hide segments without a valid display value and restrict the view to segments with detected positive water depth. These local filters do not remove records from the GeoPackage.

## 9\. Interactive Profile

Open **Plugins > ICESat-2 Data Explorer > Interactive Profile**.

The module can use compatible ATL03, ATL08, ATL13, and ATL24 layers already loaded in the QGIS project.

### 9.1 Select a layer and pass

1. Select an **ICESat-2 layer**.
2. The plugin identifies the product.
3. Use **Available pass / beam** to choose a valid combination.

The combination list includes acquisition date, RGT, cycle, beam, and point count, for example:

`2024-07-13 · RGT 0392 · Cycle 06 · gt2r · 951 points`

The fields have different roles:

* **Acquisition date** comes from the observation time.
* **RGT** is the Reference Ground Track identifier; it is spatial/orbital and is not itself a date.
* **Cycle** identifies the repeat cycle.
* **Beam (gt)** identifies the ICESat-2 ground-track beam.

The separate RGT, Cycle, and Beam selectors are cascading: impossible combinations are not intentionally offered.

### 9.2 Choose X and Y axes

The user can choose any numeric attributes available in the selected layer for the X and Y axes.

Default combinations are:

|Product|Default X|Default Y|
|-|-|-|
|ATL24|Latitude|Depth|
|ATL08|Latitude|Terrain elevation (`h\_te\_median`)|
|ATL03|Latitude|Photon height (`height`)|
|ATL13|Latitude|Orthometric water-surface height (`ht\_ortho`)|

For along-track analysis, a useful choice is often **X = Along-track distance (`x\_atc`)** when that field is available.

Depth fields that are positive downward are plotted with an inverted Y axis. Elevation and height fields keep the conventional positive-up orientation.

### 9.3 Maximum displayed points

The profile may contain more points than are practical to draw interactively. **Maximum displayed** limits the number of points drawn in the profile while preserving the underlying layer.

### 9.4 Create and interact with the profile

Click **Create profile** after selecting the pass and axes.

Available interactions include:

* clicking points in the profile;
* rectangle selection;
* Matplotlib pan and zoom tools;
* **Clear selection**;
* **Zoom to profile extent**;
* **Zoom to selected points**;
* **Exclude selected from profile**;
* **Restore excluded points**.

Profile exclusion is temporary. It does not delete records from the GeoPackage. Geographic longitude and latitude are retained separately from the plotted X/Y variables, so map zoom remains correct even when the profile uses non-geographic axes.

## 10\. Model Tide Values for ATL24

Open **Plugins > ICESat-2 Data Explorer > Model Tide Values**.

This module is designed for ATL24 layers containing the required `depth`, longitude, latitude, and time information.

!\[Model Tide Values interface](images/model\_tide\_values.png)

### 10.1 First-time tide support

On a new QGIS installation:

1. Click **Install tide support**.
2. Wait until the isolated tide environment is ready.
3. Click **Download GOT4.10c**.
4. Use **Check status** to verify the environment and model files.

If QGIS was reinstalled or moved and the old tide environment points to a missing Python interpreter, use **Repair tide support**. The repair is designed to recreate the isolated environment while preserving existing model files when possible.

### 10.2 Select the ATL24 layer

The layer list identifies which loaded layers are ready. Layers missing the ATL24 `depth` field are shown as incompatible.

### 10.3 Interpolation

Two methods are available:

* **Linear**
* **Nearest**

**Allow spatial extrapolation** is disabled by default. Enable it only when the scientific implications are understood.

### 10.4 Processing chunk

The processing chunk controls how many photons are processed in each batch. The default is 50,000 photons. Smaller chunks can reduce memory pressure on limited systems, while larger chunks may reduce overhead on capable systems.

### 10.5 Output fields

The model-tide workflow creates a new GeoPackage and preserves the original ATL24 `depth` field. Important added fields include:

|Field|Meaning|
|-|-|
|`tide\_ocean\_model\_m`|Modeled astronomical ocean-tide elevation from GOT4.10c.|
|`depth\_tide\_corrected\_m`|Tide-reduced depth calculated as `depth - tide\_ocean\_model\_m`.|
|`tide\_time\_utc`|UTC time used for the model evaluation.|
|`tide\_valid`|Validity indicator for the modeled tide value.|
|`tide\_model`|Model identifier.|
|`tide\_method`|Interpolation method used.|

The formula is:

`depth\_tide\_corrected\_m = depth - tide\_ocean\_model\_m`

A positive modeled tide means the instantaneous water level is above the model tide zero; subtracting that positive elevation reduces the instantaneous positive-down depth toward the model tide zero. A negative modeled tide increases the reduced depth.

**Important vertical-reference limitation:** `depth\_tide\_corrected\_m` is not automatically a chart-datum depth, LAT depth, MLLW depth, or observed local-MSL depth. It is a tide-reduced value relative to the zero/mean level implicit in the astronomical tide model. Meteorological and other non-astronomical water-level effects are not represented by this field.

## 11\. Output GeoPackages and HTML reports

A successful product request creates a GeoPackage and an HTML report.

The report is intended to provide provenance and interpretation, not just a raw parameter dump. Depending on the product, it can include:

* Executive summary
* Data source and provenance
* Request and visualization
* Area-of-interest overview
* Vertical-reference notes
* Product statistics
* Classification summary
* Quality assessment
* Attribute dictionary
* Warnings
* Scientific notes
* Technical details and request parameters

The date range is displayed in a concise `YYYY-MM-DD to YYYY-MM-DD` format. The exact AOI WKT is retained under Technical details rather than occupying the main visual section.

The Attribute dictionary intentionally omits QGIS field-type and NULL-count columns. NULL information remains available in quality-oriented parts of the report where it has analytical value.

## 12\. Recommended workflows

### 12.1 Quick ATL24 bathymetry workflow

1. Open Data Explorer.
2. Select ATL24.
3. Keep Version 2 for a new analysis.
4. Select dates and AOI.
5. Start with Minimum confidence = 0.00 and no exclusion flags.
6. Choose an output GeoPackage.
7. Download.
8. Open Interactive Profile.
9. Select a date/RGT/cycle/beam combination.
10. Choose X = along-track distance if available and Y = depth.
11. Inspect/select/exclude points as needed.
12. If tide reduction is required, open Model Tide Values and process the ATL24 output.

### 12.2 Quick ATL03 workflow

1. Start with a modest AOI and limited date range.
2. Select ATL03.
3. Choose the native surface type appropriate to the study.
4. Use a permissive confidence setting for an initial availability test.
5. Download.
6. For large requests, allow the plugin to process the discovered granules incrementally.
7. Use Interactive Profile to isolate the desired acquisition date, RGT, cycle, and beam.

## 13\. Troubleshooting

### SlideRule is not installed

Open Data Explorer and click **Install download support**. This is normally required once per QGIS installation.

### QGIS 3.30 reports SSL errors while installing SlideRule

Version 0.10.0 requires QGIS 3.44 or later. Use a supported QGIS version instead of attempting to repair the old 3.30 Python environment inside the plugin.

### ATL03 returns `Unexpected termination of response`

Version 0.10.0 processes large ATL03 requests granule-by-granule, retries transient failures, and can split an unstable granule by beam. If a specific request still fails, reduce the AOI or date range and retry.

### Known ATL03 data are not returned

Check:

* date range;
* AOI;
* surface type;
* confidence selection;
* photon quality.

A coastal pass can be represented under a native ATL03 surface-confidence category that differs from what is intuitively expected.

### Known ATL24 data are not returned

First test Version 2 with Minimum confidence = 0.00 and all exclusion flags disabled. If the known data come from an older collection, use **Version 1 - legacy comparison** explicitly. Do not silently combine releases in one analysis.

### Model Tide Values shows `missing: depth`

The selected layer is not a compatible ATL24 bathymetry layer for the tide workflow. Select an ATL24 layer containing the `depth` field.

### Tide environment requires repair

Use **Repair tide support**. This is especially relevant after reinstalling or moving QGIS, because an older virtual environment may retain a reference to a previous QGIS Python path.

## 14\. Data integrity and scientific cautions

* Local display filters do not delete data from the GeoPackage.
* Temporary profile exclusions do not delete source observations.
* ATL03 and ATL24 product releases should be recorded and kept consistent within an analysis.
* ATL24 Version 1 and Version 2 should not be silently mixed.
* Model tide values are an additional modeled attribute; the original ATL24 depth is preserved.
* Tide reduction by GOT4.10c is not equivalent to a full hydrographic chart-datum transformation.
* Processing reports should be retained with project outputs because they document request parameters and provenance.

## 15\. Citation and authorship

Recommended short citation in plugin-generated material:

**Andrade et al. (2026). ICESat-2 Data Explorer. Version 0.10.0.**

Software authors:

* Laura Coelho de Andrade
* Kim Earle Lowell
* Nilcilene das Graças Medeiros
* Arthur Amaral e Silva
* Italo Oliveira Ferreira

## 

