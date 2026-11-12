## 1. Purpose

ICESat-2 Data Explorer is a QGIS plugin for accessing, converting, visualizing, documenting, and analyzing selected ICESat-2 products directly inside QGIS. Version 0.10.3 supports ATL03, ATL08, ATL13, and ATL24 workflows through SlideRule, converts local HDF5 granules to CSV or GeoPackage, includes an interactive profile viewer, generates HTML processing reports, and provides an optional model-tide workflow for ATL24 using GOT4.10c through pyTMD.

The plugin is designed so that data acquisition, visualization, profile inspection, and provenance reporting remain in a single GIS environment.

> **What is new in version 0.10.3**  
> - The **HDF5 Converter** now uses a more robust support workflow for `h5py`.  
> - HDF5 access runs in an **isolated QGIS-Python process**, reducing DLL conflicts on Windows/QGIS installations.  
> - The support check can report **Installed**, **Not installed**, or **Repair required**, and the converter interface shown in this manual reflects that updated behavior.
> - The **Use selected polygon** procedure is now documented explicitly, including the active-layer and one-feature requirements.
> - ATL24 now offers independent checkboxes for classes **0, 1, 40 and 41**, with class 40 selected by default.
> - Output names update predictably when the product changes, successful layers are zoomed to automatically, and very large HDF5 layers are added with rendering disabled to keep QGIS responsive.

## 2. Compatibility and requirements

- QGIS 3.44 or later.
- QGIS 3.44 is the recommended and tested family for this release.
- Internet access is required for SlideRule installation and ICESat-2 data requests.
- A NASA Earthdata Login is not required by the plugin's SlideRule download workflow.
- The local HDF5 Converter can install its required `h5py` support automatically for the active QGIS installation/profile.
- Model tide support is optional and is managed separately from the SlideRule download support.

### Supported products

| Product | Main purpose in the plugin | Current behavior |
|---|---|---|
| ATL03 | Photon-level geolocated data | Explicitly requests ATL03 Version 7 and can retrieve geoid and ocean-tide ancillary fields. Broad requests are handled automatically with retry and beam fallback. |
| ATL08 | Land and vegetation segments | Supports terrain/canopy display and server-side quality-score thresholds from 0 to 100. |
| ATL13 | Inland-water segments | Supports water-surface and detected-water-depth visualization with local display filtering. |
| ATL24 | Coastal and nearshore bathymetry | Version 2 is the current/default option. Version 1 is retained as a legacy comparison option. |

## 3. Installation

### 3.1 Install the plugin from ZIP

1. Open QGIS.
2. Open **Plugins > Manage and Install Plugins**.
3. Choose **Install from ZIP**.
4. Select the ICESat-2 Data Explorer ZIP file.
5. Enable **ICESat-2 Data Explorer**.
6. In QGIS, make sure that **ICESat-2 Data Explorer** is enabled, and then go to **Plugins > ICESat-2 Data Explorer > Data Explorer**.

The plugin menu contains five entries:

- **Data Explorer**
- **HDF5 Converter**
- **Interactive Profile**
- **Model Tide Values**
- **About**

The toolbar provides direct access to Data Explorer, HDF5 Converter, Interactive Profile, and Model Tide Values, in that order:

![ICESat-2 Data Explorer toolbar icons](images/toolbar_icons.png){width=2.0in}

### 3.2 First-time download support

The SlideRule download support needs to be installed only once for each QGIS installation/profile. After opening the Data Explorer window in Step 6 above, the user can install it by clicking **Install download support** in the **Download support** section.

1. Open **Data Explorer**.
2. In **Download support**, click **Install download support**.
3. Wait until the status confirms that the managed SlideRule support is ready.
4. The same support is then used for ATL03, ATL08, ATL13, and ATL24 downloads.

Once the status shows that SlideRule is installed, the same support remains available to that QGIS installation/profile unless it is removed or repaired.

## 4. Data Explorer overview

The Data Explorer is the main acquisition module. A typical workflow is:

![Data Explorer window](images/data_explorer.png){width=95%}

1. Select the ICESat-2 product.
2. Select the start and end dates.
3. Define the area of interest.
4. Configure product-specific settings.
5. Choose an output GeoPackage.
6. Run the download.
7. Inspect the resulting QGIS layer and the associated HTML report.

### 4.1 Date range

Dates are entered as `YYYY-MM-DD`. The selected period is sent with the data request and is also recorded in the report.

For broad ATL03 searches, a long date range can intersect many granules and take substantially longer to process. The plugin handles the request automatically; if repeated failures continue, use a smaller AOI or a narrower date range.

### 4.2 Area of interest

The coordinate boxes use geographic longitude and latitude in **decimal degrees** in **WGS 84 (EPSG:4326)**:

- **West**: western longitude
- **East**: eastern longitude
- **South**: southern latitude
- **North**: northern latitude

These values are not UTM eastings or northings.

The user can define the AOI using one of three approaches:

- **Use current map extent**: adopts the visible map extent.
- **Draw polygon on map**: interactively draws an AOI.
- **Use selected polygon**: uses a selected polygon feature already present in QGIS.

To use **Use selected polygon**:

1. Add or activate a polygon vector layer in QGIS.
2. Select exactly one polygon feature in the map or attribute table.
3. Keep that layer active in the **Layers** panel.
4. Return to Data Explorer and click **Use selected polygon**.

The plugin reads only the active layer and its selected feature. If there are zero features or more than one selected feature, the selection is rejected so that the AOI is not ambiguous.

The exact request geometry is retained for provenance in the processing report. The report can also include an AOI overview rendered from the visible QGIS project layers.

## 5. ATL24 bathymetry

Choose **ATL24** in the Product selector.

For Version 2, broad requests are divided into smaller automatic batches when many granules intersect the selected date range or AOI. If SlideRule closes a response before it finishes, the plugin retries that request. When the interruption persists, only the affected batch is subdivided and retried automatically. The plugin does not treat an incomplete response as a successful download.

### 5.1 ATL24 release

Two explicit choices are available:

- **Version 2 - current and recommended**
- **Version 1 - legacy comparison**

Version 2 should normally be used for new analyses. Version 1 is provided so that previously downloaded or known legacy results can be compared without silently mixing product releases.

### 5.2 ATL24 filters

#### Photon class filter

The **Photon class filter** uses independent checkboxes to control which ATL24 `class_ph` records are requested:

- **Class 0 — unclassified**;
- **Class 1 — other**;
- **Class 40 — bathymetry** (selected by default); and
- **Class 41 — sea surface**.

Select any combination of classes. Selecting only class 40 reproduces the previous bathymetry-only behavior; selecting all four classes reproduces the previous all-classes behavior. At least one class must remain selected.

The selected class scope is applied to the main request and to the plugin's compatibility and diagnostic paths. The exported GeoPackage retains `class_ph` and a readable `class_name` field when the service returns the classification. Selecting all classes does not apply ATL03 `signal_conf_ph` filtering.

**Minimum confidence** accepts values from 0.00 to 1.00. A value of 0.00 is the most permissive setting.

Optional exclusion controls are available for:

- low-confidence photons;
- sensor-depth-exceeded photons;
- photons with invalid Kd;
- photons with invalid wind speed.

For diagnostic tests in an area where bathymetry is known to exist, start with **Minimum confidence = 0.00** and leave all exclusion options unchecked. More restrictive filters can be applied after confirming data availability.

#### ATL24 confidence versus ATL03 signal confidence

`low_confidence_flag` is an **ATL24 bathymetry flag**. It accompanies the ATL24 `confidence` field, which is an ensemble confidence score from 0.0 to 1.0 for the ATL24 bathymetry classification. In the SlideRule ATL24 definition, `low_confidence_flag = 1` identifies a bathymetry confidence below 0.6.

This field is **not** the same as ATL03 `signal_conf_ph`. The ATL03 field is a native per-photon, per-surface-type signal-confidence classification stored in `/gtx/heights/signal_conf_ph`, with codes from -2 to 4. ATL24 uses photons and source information derived from ATL03, but ATL24 bathymetry confidence and ATL03 signal confidence are different variables produced by different processing methods. The methodology for `signal_conf_ph` belongs to the ATL03 ATBD; the ATL24 bathymetry confidence methodology belongs to the ATL24 documentation.

Official references: [NSIDC ATL24 Version 2](https://nsidc.org/data/atl24/versions/2), [ATL24 Product Data Dictionary](https://nsidc.org/sites/default/files/documents/technical-reference/icesat2_atl24_data_dict_v001.pdf), and [SlideRule ICESat-2 / ATL24 documentation](https://docs.slideruleearth.io/user_guide/icesat2.html#atl24-atl24x).

### 5.3 ATL24 output

The output is a GeoPackage containing the ATL24 records returned by the request and the attributes supplied by SlideRule. The GeoPackage can later be used in the Interactive Profile and Model Tide Values modules. After a successful download, the plugin adds the layer and zooms the QGIS map to its extent while respecting the current project CRS.

## 6. ATL08 land and vegetation segments

Choose **ATL08** in the Product selector.

### 6.1 Server-side quality filters

Two quality-score thresholds are available:

- **Minimum terrain quality score**
- **Minimum canopy quality score**

Both use an integer scale from 0 to 100. A value of **0 disables the corresponding server-side filter**. Higher values are more restrictive.

These are server-side filters: records that do not satisfy the selected threshold are not returned by the SlideRule request.

### 6.2 Display field

The display field controls which attribute is used to style the resulting layer in QGIS. Available choices include:

- canopy height;
- mean canopy height;
- maximum canopy height;
- minimum canopy height;
- terrain elevation;
- terrain slope;
- vegetation cover;
- ground photon count;
- canopy photon count;
- canopy openness.

### 6.3 Local display filters

Local filters affect the QGIS visualization but do not delete records from the GeoPackage. Options include hiding:

- segments without valid terrain elevation;
- segments without ground photons;
- segments without canopy photons;
- negative canopy heights.

This distinction is important: **server-side filters change the downloaded dataset; local display filters only change what is visible in QGIS**.

## 7. ATL03 photon-level data

Choose **ATL03** in the Product selector.

ATL03 can contain very large numbers of individual photons. For the first test in a new study area, a smaller AOI or narrower time range is recommended.

### 7.1 Surface type

The available native surface-type choices are:

- Dynamic / all surface types
- Land
- Ocean
- Sea ice
- Land ice
- Inland water

In coastal environments, a known pass may not necessarily be returned under the surface type a user intuitively expects. The plugin retains diagnostic logic that can test permissive Land, Ocean, and Inland-water settings when needed.

### 7.2 Minimum confidence

Available choices range from no native confidence filter to high-confidence-only selection. The interface also provides a permissive option that includes possible TEP photons.

### 7.3 Photon quality

Two main choices are available:

- **All photon-quality classes**
- **Nominal photons only**

### 7.4 Display and local filters

The display field can include photon height, orthometric photon height, geoid, geoid free-to-mean conversion, ATL03 ocean tide, signal confidence, photon quality, solar elevation, background rate, and along-track distance.

Local display options can hide photons without a valid display value or show only signal candidates. These options do not remove records from the GeoPackage.

### 7.5 Large-area ATL03 processing

The plugin handles broad ATL03 requests automatically, including interrupted-transfer retries and beam-level recovery when needed. Large photon requests can take time and produce large GeoPackages. If a request repeatedly fails after automatic recovery, reduce the AOI or date range and retry.

## 8. ATL13 inland-water data

Choose **ATL13** in the Product selector.

The display field can be set to:

- orthometric water-surface height;
- ellipsoidal water-surface height;
- water-surface standard deviation;
- detected water depth.

Local display options can hide segments without a valid display value and restrict the view to segments with detected positive water depth. These local filters do not remove records from the GeoPackage.

## 9. HDF5 Converter

Open **Plugins > ICESat-2 Data Explorer > HDF5 Converter** to read a local NASA ICESat-2 granule without sending it to SlideRule. The module accepts `.h5` or `.hdf5` files for ATL03, ATL08, ATL13, and ATL24.

![HDF5 Converter window](images/hdf5_converter.png){width=92%}

The converter reads the primary per-photon or per-segment table for each ground-track beam and never modifies the source HDF5 file. It exports:

- standardized `latitude`, `longitude`, `product`, `beam`, `source_group`, and `record_index` columns;
- granule and orbit context when present, including release/version, start/end time, RGT, cycle, orbit number, spacecraft orientation, beam type, and spot number;
- all one-dimensional scientific datasets aligned with the product record dimension;
- small two-dimensional scientific datasets as separate columns, including arrays whose record dimension is stored in either direction;
- ATL03 `signal_conf_ph` as five explicit surface-type columns: land, ocean, sea ice, land ice, and inland water;
- ATL03 geolocation and geophysical-correction values associated with each photon through the source segment mapping, including fields such as `segment_id`, `segment_dist_x`, `solar_elevation`, `geoid`, `geoid_free2mean`, and `tide_ocean` when available;
- useful standardized columns without removing the native fields: ATL03 `height`, `x_atc`, `y_atc`, and `ph_index`; common `gps_seconds`; ATL08 terrain/canopy aliases; and ATL24 `depth` calculated as `surface_h - ortho_h` only when the source does not already provide `depth`.

CSV and GeoPackage contain the same attribute table. The GeoPackage additionally stores a WGS 84 point geometry in EPSG:4326 and can be added directly to the current QGIS project. The CSV keeps longitude and latitude as ordinary columns and has no GIS geometry object.

The HDF5 hierarchy can contain metadata tables, dimension scales, large multidimensional arrays, and variables recorded at resolutions that do not match the selected photon/segment table. Those items are not blindly repeated. Large non-tabular arrays are skipped and reported in the completion summary; the scientifically important ATL03 segment-rate fields described above are explicitly mapped to their photons.

When a GeoPackage conversion contains at least **500,000 records** and **Add the converted GeoPackage layer to the current QGIS project** is enabled, the plugin adds the complete layer with rendering disabled. Enable it in the **Layers** panel when you are ready to visualize it; the output file is not reduced or filtered.

### 9.1 Convert a local granule

1. In **HDF5 support**, check the status first. If support is **Not installed**, click **Install HDF5 support**. If support is present but the status indicates a problem, click **Repair HDF5 support**. This is normally required only once for each QGIS installation/profile.
2. Click **Select HDF5 file** and choose one ATL03, ATL08, ATL13, or ATL24 granule.
3. Confirm the detected product.
4. Choose an output format:
   - **GeoPackage - WGS 84 point layer (recommended)** creates point geometry in EPSG:4326 and can add the result directly to QGIS.
   - **CSV - coordinate columns** creates a standard table with longitude and latitude fields.
5. Select the output file.
6. Click **Convert HDF5**.
7. Wait for the record and beam summary.

The module processes records in chunks to limit memory use. It does not apply SlideRule filters, ATL24 confidence thresholds, refraction corrections, or model tides. Native values remain available under their source field names; the convenience columns listed above are added separately.

### 9.2 HDF5 support

The converter installs its managed `h5py` dependency only for the active QGIS installation/profile and loads it only when needed. In version 0.10.3, HDF5 access is executed in an **isolated QGIS-Python process**, which improves robustness in environments where direct in-process loading may fail because of library conflicts.

If the user clicks **Convert HDF5** while support is missing, the plugin offers to install it and resumes the conversion after a successful installation. Use **Repair HDF5 support** whenever the status reports a damaged or unloadable installation.

HDF5 support is separate from SlideRule download support and from the optional Model Tide environment.

## 10. Interactive Profile

Open **Plugins > ICESat-2 Data Explorer > Interactive Profile**.

![Interactive Profile window](images/interactive_profile.png){width=95%}

The module can use compatible ATL03, ATL08, ATL13, and ATL24 layers already loaded in the QGIS project.

### 10.1 Select a layer and pass

1. Select an **ICESat-2 layer**.
2. The plugin identifies the product.
3. Use **Available pass / beam** to choose a valid combination.

The combination list includes acquisition date, RGT, cycle, beam, and point count, for example:

`2024-07-13 · RGT 0392 · Cycle 06 · gt2r · 951 points`

The fields have different roles:

- **Acquisition date** comes from the observation time.
- **RGT** is the Reference Ground Track identifier; it is spatial/orbital and is not itself a date.
- **Cycle** identifies the repeat cycle.
- **Beam (gt)** identifies the ICESat-2 ground-track beam.

The separate RGT, Cycle, and Beam selectors are cascading: impossible combinations are not intentionally offered.

### 10.2 Choose X and Y axes

The user can choose any numeric attributes available in the selected layer for the X and Y axes.

Default combinations are:

| Product | Default X | Default Y |
|---|---|---|
| ATL24 | Latitude | Depth |
| ATL08 | Latitude | Terrain elevation (`h_te_median`) |
| ATL03 | Latitude | Photon height (`height`) |
| ATL13 | Latitude | Orthometric water-surface height (`ht_ortho`) |

For along-track analysis, a useful choice is often **X = Along-track distance (`x_atc`)** when that field is available.

Depth fields that are positive downward are plotted with an inverted Y axis. Elevation and height fields keep the conventional positive-up orientation.

### 10.3 Maximum displayed points

The profile may contain more points than are practical to draw interactively. **Maximum displayed** limits the number of points drawn in the profile while preserving the underlying layer.

### 10.4 Create and interact with the profile

Click **Create profile** after selecting the pass and axes.

Available interactions include:

- clicking points in the profile;
- rectangle selection;
- freehand lasso selection, chosen with **Selection shape**;
- Matplotlib pan and zoom tools;
- **Clear selection**;
- **Zoom to profile extent**;
- **Zoom to selected points**;
- **Exclude selected from profile**;
- **Restore excluded points**.

Profile exclusion is temporary. It does not delete records from the GeoPackage. Geographic longitude and latitude are retained separately from the plotted X/Y variables, so map zoom remains correct even when the profile uses non-geographic axes.

To save the profile figure, click the **floppy-disk icon** in the Matplotlib toolbar, choose an image filename and select a supported graphic format such as PNG. Saving the figure does not change or save edits to the source GeoPackage; point exclusion remains temporary.

## 11. Model Tide Values for ATL24

Open **Plugins > ICESat-2 Data Explorer > Model Tide Values**.

This module is designed for ATL24 layers containing the required `depth`, longitude, latitude, and time information.

![Model Tide Values interface](images/model_tide_values.jpeg){width=80%}

### 11.1 First-time tide support

On a new QGIS installation:

1. Click **Install tide support**.
2. Wait until the isolated tide environment is ready.
3. Click **Download GOT4.10c**.
4. Use **Check status** to verify the environment and model files.

If QGIS was reinstalled or moved and the old tide environment points to a missing Python interpreter, use **Repair tide support**. The repair is designed to recreate the isolated environment while preserving existing model files when possible.

### 11.2 Select the ATL24 layer

The layer list identifies which loaded layers are ready. Layers missing the ATL24 `depth` field are shown as incompatible.

### 11.3 Interpolation

Two methods are available:

- **Linear**
- **Nearest**

**Allow spatial extrapolation** is disabled by default. Enable it only when the scientific implications are understood.

### 11.4 Processing chunk

The processing chunk controls how many photons are processed in each batch. The default is 50,000 photons. Smaller chunks can reduce memory pressure on limited systems, while larger chunks may reduce overhead on capable systems.

### 11.5 Output fields

The model-tide workflow creates a new GeoPackage and preserves the original ATL24 `depth` field. Important added fields include:

| Field | Meaning |
|---|---|
| `tide_ocean_model_m` | Modeled astronomical ocean-tide elevation from GOT4.10c. |
| `depth_tide_corrected_m` | Tide-reduced depth calculated as `depth - tide_ocean_model_m`. |
| `tide_time_utc` | UTC time used for the model evaluation. |
| `tide_valid` | Validity indicator for the modeled tide value. |
| `tide_model` | Model identifier. |
| `tide_method` | Interpolation method used. |

The formula is:

`depth_tide_corrected_m = depth - tide_ocean_model_m`

A positive modeled tide means the instantaneous water level is above the model tide zero; subtracting that positive elevation reduces the instantaneous positive-down depth toward the model tide zero. A negative modeled tide increases the reduced depth.

**Important vertical-reference limitation:** `depth_tide_corrected_m` is not automatically a chart-datum depth, LAT depth, MLLW depth, or observed local-MSL depth. It is a tide-reduced value relative to the zero/mean level implicit in the astronomical tide model. Meteorological and other non-astronomical water-level effects are not represented by this field.

The module creates an HTML summary beside the new GeoPackage:

![ATL24 Model Tide report](images/model_tide_report.jpeg){width=92%}

## 12. Saving data, GeoPackages and HTML reports

### 12.1 Save a Data Explorer download

Before starting a download, scroll to the **Output** section in Data Explorer:

1. Use the editable **Output GeoPackage** field or click **Browse**.
2. Choose the destination folder.
3. Enter a descriptive filename ending in `.gpkg`.
4. Click **Save** in the file chooser, if using the dialog.
5. Run the product download.

The field starts with a product-coded name such as `ATL24_output.gpkg`. When the product changes, a product-coded filename updates predictably, for example `KimATL03.gpkg` becomes `KimATL08.gpkg`. A custom filename without the previous product code is preserved, and the field can always be edited directly. A successful request writes the data directly to that GeoPackage, adds its layer to QGIS, and zooms the map to the downloaded data. Saving the QGIS project stores the project reference to the GeoPackage; it does not replace the need to retain the `.gpkg` file itself. The associated HTML processing report is written in the output location and should be retained with the GeoPackage.

### 12.2 Export a loaded layer to CSV or another GIS format

To create another copy of any resulting QGIS layer:

1. Right-click the layer in the **Layers** panel.
2. Choose **Export > Save Features As**.
3. Select **Comma Separated Value [CSV]**, GeoPackage, ESRI Shapefile, GeoJSON, or another QGIS-supported format.
4. For CSV, choose a geometry option such as **AS_XY** when longitude and latitude columns are required.
5. Select the output path and click **OK**.

This QGIS export is distinct from the plugin's local **HDF5 Converter**, which reads a NASA `.h5` granule directly. The Model Tide module also has its own **Select output GeoPackage** control and always creates a new file so that the source ATL24 GeoPackage remains unchanged.

### 12.3 Processing reports

The report is intended to provide provenance and interpretation, not just a raw parameter dump. Depending on the product, it can include:

- Executive summary
- Data source and provenance
- Request and visualization
- Area-of-interest overview
- Vertical-reference notes
- Product statistics
- Classification summary
- Quality assessment
- Attribute dictionary
- Warnings
- Scientific notes
- Technical details and request parameters

The date range is displayed in a concise `YYYY-MM-DD to YYYY-MM-DD` format. The exact AOI WKT is retained under Technical details rather than occupying the main visual section.

![Example ATL24 processing report](images/processing_report.jpeg){width=92%}

## 13. Recommended workflows

### 13.1 Quick ATL24 bathymetry workflow

1. Open Data Explorer.
2. Select ATL24.
3. Keep Version 2 for a new analysis.
4. Select dates and AOI.
5. Keep **Class 40 — bathymetry** checked for depth-focused work, or check any combination of the four ATL24 classes for broader inspection.
6. Start with Minimum confidence = 0.00 and no exclusion flags.
7. Choose an output GeoPackage.
8. Download; the map automatically zooms to the resulting layer.
9. Open Interactive Profile.
10. Select a date/RGT/cycle/beam combination.
11. Choose X = along-track distance if available and Y = depth.
12. Inspect/select/exclude points as needed.
13. If tide reduction is required, open Model Tide Values and process the ATL24 output.

### 13.2 Quick ATL03 workflow

1. Start with a modest AOI and limited date range.
2. Select ATL03.
3. Choose the native surface type appropriate to the study.
4. Use a permissive confidence setting for an initial availability test.
5. Download.
6. For large requests, allow the plugin to process the discovered granules incrementally.
7. Use Interactive Profile to isolate the desired acquisition date, RGT, cycle, and beam.

## 14. Troubleshooting

### SlideRule is not installed

Open Data Explorer and click **Install download support**. This is normally required once per QGIS installation/profile.

### Use selected polygon reports no selected feature

Activate a polygon vector layer, select exactly one polygon feature in the map or attribute table, and click **Use selected polygon** while that layer remains active. The plugin intentionally rejects zero or multiple selected features.

### The map jumps to an incorrect location after download

The corrected release transforms the downloaded layer extent into the current QGIS project CRS before zooming. If the map still does not show the layer, right-click it and choose **Zoom to Layer**, then verify that the layer CRS is valid and that the project CRS is correctly defined.

### HDF5 Converter reports that `h5py` is missing

Open the HDF5 Converter and click **Install HDF5 support**. The plugin installs a compatible `h5py` package for the active QGIS installation/profile. This is normally required only once and is separate from SlideRule download support. If installation already exists but cannot be loaded, click **Repair HDF5 support**. In version 0.10.3, the converter runs HDF5 access in an isolated QGIS-Python process to reduce DLL-loading conflicts.

### HDF5 Converter does not identify the product

Confirm that the selected file is an unmodified ICESat-2 ATL03, ATL08, ATL13, or ATL24 HDF5 granule. Product detection first uses the filename and then the HDF5 metadata. Renaming a file is acceptable when its internal product metadata remain available, but unrelated HDF5 products are not supported.

### ATL03 returns `Unexpected termination of response`

The plugin retries interrupted ATL03 transfers and can recover at beam level. If a specific request still fails after automatic recovery, reduce the AOI or date range and retry.

### ATL24 returns `Unexpected termination of response`

The plugin retries interrupted ATL24 responses and automatically subdivides the affected resource batch when the response remains too large or unstable. If the same error persists after recovery, reduce the AOI or date range and retry. This keeps the smaller-area workflow as a valid fallback for temporary SlideRule or network limits.

### Known ATL03 data are not returned

Check:

- date range;
- AOI;
- surface type;
- confidence selection;
- photon quality.

A coastal pass can be represented under a native ATL03 surface-confidence category that differs from what is intuitively expected.

### Known ATL24 data are not returned

First test Version 2 with Minimum confidence = 0.00 and all exclusion flags disabled. If the known data come from an older collection, use **Version 1 - legacy comparison** explicitly. Do not silently combine releases in one analysis.

### Model Tide Values shows `missing: depth`

The selected layer is not a compatible ATL24 bathymetry layer for the tide workflow. Select an ATL24 layer containing the `depth` field.

### Tide environment requires repair

Use **Repair tide support**. This is especially relevant after reinstalling or moving QGIS, because an older virtual environment may retain a reference to a previous QGIS Python path.

## 15. Data integrity and scientific cautions

- Local display filters do not delete data from the GeoPackage.
- Temporary profile exclusions do not delete source observations.
- ATL03 and ATL24 product releases should be recorded and kept consistent within an analysis.
- ATL24 Version 1 and Version 2 should not be silently mixed.
- Model tide values are an additional modeled attribute; the original ATL24 depth is preserved.
- Tide reduction by GOT4.10c is not equivalent to a full hydrographic chart-datum transformation.
- Processing reports should be retained with project outputs because they document request parameters and provenance.
- HDF5 conversion does not apply scientific corrections or filters. Native values are preserved, while the documented convenience columns are added separately.

## 16. Citation

Recommended short citation in plugin-generated material:

**Andrade et al. (2026). ICESat-2 Data Explorer. Version 0.10.3.**
