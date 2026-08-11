from __future__ import annotations

from typing import Any

REPORT_AUTHOR = "Andrade et al. (2026)"
REPORT_ROLE = "ICESat-2 Data Explorer"
REPORT_INSTITUTION = "UFV, Brazil"

AUTHOR_LINE = REPORT_AUTHOR

# Full author list retained in the source code for provenance.
# The compact citation above is used in generated reports.
FULL_AUTHORS = (
    "Laura Coelho de Andrade",
    "Kim Earle Lowell",
    "Nilcilene das Graças Medeiros",
    "Arthur Amaral e Silva",
    "Italo Oliveira Ferreira",
)

# Each definition uses: description, units, notes.
COMMON_FIELDS: dict[str, dict[str, str]] = {
    "fid": {
        "description": "GeoPackage feature identifier created for the output layer.",
        "units": "—",
        "notes": "Database key; not an ICESat-2 science variable.",
    },
    "time": {
        "description": "Observation time returned by the source service.",
        "units": "UTC datetime",
        "notes": "May duplicate time_ns after conversion during export.",
    },
    "time_ns": {
        "description": "Observation time. SlideRule supplies Unix time at nanosecond precision and the GeoPackage stores it as a date-time value when supported.",
        "units": "UTC datetime / nanoseconds",
        "notes": "Use this field for temporal matching and time-dependent corrections.",
    },
    "latitude": {
        "description": "Latitude of the returned photon or segment coordinate.",
        "units": "degrees",
        "notes": "Output layer CRS is EPSG:4326.",
    },
    "longitude": {
        "description": "Longitude of the returned photon or segment coordinate.",
        "units": "degrees",
        "notes": "Output layer CRS is EPSG:4326.",
    },
    "x_atc": {
        "description": "Along-track distance of the photon or segment within the ICESat-2 ground track.",
        "units": "m",
        "notes": "Useful for profile ordering and along-track diagnostics.",
    },
    "y_atc": {
        "description": "Across-track distance of the photon relative to the reference track or segment.",
        "units": "m",
        "notes": "Sign convention follows the source product/SlideRule output.",
    },
    "spot": {
        "description": "ATLAS detector field-of-view number.",
        "units": "1–6",
        "notes": "Independent of spacecraft orientation; beam strength can change after yaw flips.",
    },
    "cycle": {
        "description": "ICESat-2 orbital cycle number.",
        "units": "count",
        "notes": "The reference orbit repeats approximately every 91 days.",
    },
    "region": {
        "description": "Standard ICESat-2 granule region number.",
        "units": "1–14",
        "notes": "Used with RGT and cycle to identify a standard-product granule.",
    },
    "rgt": {
        "description": "Reference Ground Track identifier.",
        "units": "count",
        "notes": "ICESat-2 has 1,387 reference ground tracks in a repeat cycle.",
    },
    "gt": {
        "description": "ICESat-2 beam/ground-track code.",
        "units": "code",
        "notes": "Common numeric encoding: 10=gt1l, 20=gt1r, 30=gt2l, 40=gt2r, 50=gt3l, 60=gt3r; some services return text labels.",
    },
    "srcid": {
        "description": "Source-record or source-granule identifier returned by SlideRule.",
        "units": "identifier",
        "notes": "Useful for provenance and tracing observations to source data.",
    },
    "geometry": {
        "description": "Point geometry used by QGIS to locate the observation.",
        "units": "EPSG:4326",
        "notes": "Stored internally in the GeoPackage and normally not shown as a standard attribute column.",
    },
}

ATL03_FIELDS: dict[str, dict[str, str]] = {
    "height": {
        "description": "Ellipsoidal elevation of the individual ATL03 photon above the WGS 84 reference ellipsoid.",
        "units": "m",
        "notes": "Source ATL03/SlideRule photon height. The plugin preserves this value unchanged.",
    },
    "height_ortho": {
        "description": "Orthometric/geoidal elevation of the ATL03 photon referenced to the EGM2008 tide-free geoid.",
        "units": "m",
        "notes": "Plugin-derived attribute calculated as height - geoid. The ATL03 tide_ocean value is not applied to this column.",
    },
    "geoid": {
        "description": "EGM2008 geoid height above the WGS 84 reference ellipsoid in the tide-free system.",
        "units": "m",
        "notes": "ATL03 /gtx/geophys_corr segment-rate field associated with photons by SlideRule. It is supplemental and is not applied automatically to height.",
    },
    "geoid_free2mean": {
        "description": "Additive term used to convert the ATL03 geoid from the tide-free system to the mean-tide system.",
        "units": "m",
        "notes": "Compute the mean-tide geoid as geoid + geoid_free2mean. The plugin stores the source term but does not create a corrected height.",
    },
    "geoid_mean_tide": {
        "description": "EGM2008 geoid height expressed in the mean-tide system.",
        "units": "m",
        "notes": "Plugin-derived attribute calculated as geoid + geoid_free2mean. It is not applied automatically to the ATL03 photon height.",
    },
    "tide_ocean": {
        "description": "ATL03 modeled short-period ocean-tide correction, including principally diurnal and semidiurnal periods.",
        "units": "m",
        "notes": "ATL03 /gtx/geophys_corr segment-rate field. It is supplemental, is not an observed tide-gauge water level, and is not applied automatically to photon height.",
    },
    "solar_elevation": {
        "description": "Solar elevation angle at the photon observation time.",
        "units": "degrees",
        "notes": "Negative values normally indicate nighttime acquisition.",
    },
    "background_rate": {
        "description": "Estimated solar/background photon event rate near the observation.",
        "units": "photoelectrons s⁻¹",
        "notes": "High background rates can make signal-photon discrimination more difficult.",
    },
    "spacecraft_velocity": {
        "description": "Along-track velocity of the ICESat-2 footprint on the Earth's surface.",
        "units": "m s⁻¹",
        "notes": "Returned by the SlideRule ATL03 service when available.",
    },
    "atl03_cnf": {
        "description": "Native ATL03 signal-confidence classification for the selected surface type.",
        "units": "code",
        "notes": "-2=possible TEP; -1=not considered; 0=background/noise; 1=within 10 m; 2=low; 3=medium; 4=high confidence.",
    },
    "atl03_cnf_name": {
        "description": "Readable label derived by the plugin from atl03_cnf.",
        "units": "text",
        "notes": "Added for interpretation; the original atl03_cnf code is preserved.",
    },
    "quality_ph": {
        "description": "ATL03 photon-quality classification identifying nominal returns and possible instrument artifacts.",
        "units": "code",
        "notes": "0=nominal; 1=possible afterpulse; 2=possible impulse-response effect; 3=possible TEP. ATL03 Version 7 can include additional quality values.",
    },
    "quality_name": {
        "description": "Readable label derived by the plugin from quality_ph.",
        "units": "text",
        "notes": "Unknown Version 7 codes remain explicitly labeled by their numeric code.",
    },
    "ph_index": {
        "description": "Index of the photon within the corresponding beam of the source ATL03 granule.",
        "units": "index",
        "notes": "Use together with source-granule identity and beam; it is not globally unique by itself.",
    },
    "signal_class_ph": {
        "description": "Experimental ATL03 signal-classification field available in Version 7 when requested.",
        "units": "code",
        "notes": "Interpret using the ATL03 Version 7 data dictionary.",
    },
    "weight_ph": {
        "description": "Photon signal weight used by ATL03 classification algorithms when returned.",
        "units": "unitless",
        "notes": "Higher values generally indicate stronger evidence of signal; consult the product release documentation.",
    },
    "yapc_score": {
        "description": "Yet Another Photon Classification density/weight score calculated by SlideRule when YAPC is enabled.",
        "units": "0–255",
        "notes": "Higher scores indicate denser photon neighborhoods and generally stronger surface-return evidence.",
    },
    "atl08_class": {
        "description": "ATL08 photon classification appended to ATL03 when ATL08 classification is enabled.",
        "units": "code",
        "notes": "0=noise; 1=ground; 2=canopy; 3=top of canopy; 4=unclassified.",
    },
    "atl24_class": {
        "description": "ATL24 photon classification appended to ATL03 when ATL24 classification is enabled.",
        "units": "code",
        "notes": "0=unclassified; 40=bathymetry; 41=sea surface.",
    },
    "atl24_confidence": {
        "description": "ATL24 bathymetry confidence associated with an ATL03 photon when ATL24 classification is enabled.",
        "units": "0–1",
        "notes": "Higher values represent greater confidence in the bathymetry classification.",
    },
}

ATL08_FIELDS: dict[str, dict[str, str]] = {
    "segment_id_beg": {
        "description": "Identifier of the first ATL03 geolocation segment used in the ATL08 land segment.",
        "units": "index",
        "notes": "Supports traceability to the source photon segments.",
    },
    "segment_landcover": {
        "description": "Land-cover class assigned to the ATL08 segment from the ancillary land-cover product.",
        "units": "code",
        "notes": "Interpret class codes using the ATL08 data dictionary for the product release.",
    },
    "segment_snowcover": {
        "description": "Snow/ice-cover condition assigned to the segment using ATL09 ancillary information.",
        "units": "code",
        "notes": "Common values: 0=ice-free water; 1=snow-free land; 2=snow; 3=ice.",
    },
    "n_seg_ph": {
        "description": "Number of photons contained in the ATL08 land segment.",
        "units": "count",
        "notes": "Segment-level total, not only classified terrain or canopy photons.",
    },
    "solar_elevation": {
        "description": "Solar elevation angle at the segment observation time.",
        "units": "degrees",
        "notes": "Negative values normally indicate nighttime acquisition.",
    },
    "terrain_slope": {
        "description": "Along-track terrain slope estimated for the segment.",
        "units": "m m⁻¹",
        "notes": "Source documentation labels this as an along-track terrain-slope metric.",
    },
    "n_te_photons": {
        "description": "Number of photons classified as terrain/ground in the segment.",
        "units": "count",
        "notes": "Zero indicates that no terrain photons contributed to the terrain estimate.",
    },
    "h_te_uncertainty": {
        "description": "Estimated vertical uncertainty of the terrain-height metric.",
        "units": "m",
        "notes": "Segment-level uncertainty.",
    },
    "h_te_median": {
        "description": "Median terrain/ground height for the ATL08 segment.",
        "units": "m",
        "notes": "Vertical reference is controlled by the processing request; no plugin-side transformation is applied.",
    },
    "h_canopy": {
        "description": "Canopy height represented by the 98th percentile of canopy-photon relief heights.",
        "units": "m",
        "notes": "A segment-level canopy metric, not an individual-tree height.",
    },
    "h_canopy_uncertainty": {
        "description": "Estimated vertical uncertainty of the canopy-height metric.",
        "units": "m",
        "notes": "Segment-level uncertainty.",
    },
    "segment_cover": {
        "description": "Average fractional vegetation-cover value for the segment from the ancillary cover product.",
        "units": "% / product scale",
        "notes": "Check the ATL08 release documentation for the exact scaling convention.",
    },
    "n_ca_photons": {
        "description": "Number of photons classified as canopy in the segment.",
        "units": "count",
        "notes": "Zero indicates no canopy photons contributed to the canopy metrics.",
    },
    "h_max_canopy": {
        "description": "Maximum canopy-photon relief height in the segment.",
        "units": "m",
        "notes": "Sensitive to isolated high returns and classification errors.",
    },
    "h_min_canopy": {
        "description": "Minimum canopy-photon relief height in the segment.",
        "units": "m",
        "notes": "Segment-level metric.",
    },
    "h_mean_canopy": {
        "description": "Mean canopy-photon relief height in the segment.",
        "units": "m",
        "notes": "Segment-level metric.",
    },
    "canopy_openness": {
        "description": "Standard deviation of canopy-photon relief heights within the segment.",
        "units": "m",
        "notes": "Represents vertical dispersion/openness of canopy returns.",
    },
    "canopy_h_metrics": {
        "description": "Serialized array of canopy-height percentiles returned for the segment.",
        "units": "m",
        "notes": "The GeoPackage stores the percentile array as JSON text.",
    },
}

ATL13_FIELDS: dict[str, dict[str, str]] = {
    "ht_ortho": {
        "description": "Orthometric height of the inland-water surface.",
        "units": "m",
        "notes": "Referenced to EGM2008 according to the SlideRule ATL13 documentation.",
    },
    "ht_water_surf": {
        "description": "Ellipsoidal height of the inland-water surface.",
        "units": "m",
        "notes": "Referenced to the WGS 84 ellipsoid according to the ATL13 service documentation.",
    },
    "stdev_water_surf": {
        "description": "Derived standard deviation of the water-surface-height observations within the ATL13 segment.",
        "units": "m",
        "notes": "A measure of within-segment spread, not necessarily the full vertical uncertainty budget.",
    },
    "water_depth": {
        "description": "Depth from the mean water surface to a detected bottom return.",
        "units": "m",
        "notes": "Available only where a bottom was detected; it is not a continuous bathymetric surface.",
    },
    "refid": {
        "description": "ATL13 reference identifier for the inland-water body or feature.",
        "units": "identifier",
        "notes": "May be absent depending on the subset returned by the service.",
    },
    "name": {
        "description": "Name of the inland-water body when available in the ATL13 source metadata.",
        "units": "text",
        "notes": "May be blank or unavailable for unnamed features.",
    },
}

ATL24_FIELDS: dict[str, dict[str, str]] = {
    "ellipse_h": {
        "description": "Refraction-corrected ellipsoidal height of the classified ATL24 photon.",
        "units": "m",
        "notes": "Reference frame follows the ATL24/source release; no plugin-side vertical transformation is applied.",
    },
    "ortho_h": {
        "description": "Refraction-corrected orthometric height of the classified ATL24 photon.",
        "units": "m",
        "notes": "Referenced to EGM2008 in the ATL24/SlideRule product definition.",
    },
    "surface_h": {
        "description": "Orthometric height of the calculated instantaneous sea surface associated with the photon.",
        "units": "m",
        "notes": "Referenced to EGM2008 in the ATL24 service output.",
    },
    "depth": {
        "description": "Instantaneous water depth derived between the sea surface and bathymetric photon.",
        "units": "m",
        "notes": "The plugin preserves this source value. Tide reduction is written separately to depth_tide_corrected_m.",
    },
    "class_ph": {
        "description": "ATL24 photon-classification code.",
        "units": "code",
        "notes": "Typical values: 40=bathymetry; 41=sea surface; 0=unclassified.",
    },
    "class_name": {
        "description": "Readable label derived from the ATL24 photon-classification code.",
        "units": "text",
        "notes": "Added or preserved for convenient interpretation in QGIS.",
    },
    "confidence": {
        "description": "ATL24 bathymetry-classification confidence score.",
        "units": "0–1",
        "notes": "Higher values indicate greater confidence.",
    },
    "low_confidence_flag": {
        "description": "Flag indicating a low-confidence ATL24 bathymetry classification.",
        "units": "0/1",
        "notes": "Interpret together with confidence and the request filters.",
    },
    "sensor_depth_exceeded": {
        "description": "Flag indicating that the estimated depth exceeded the sensor/model processing limit.",
        "units": "0/1",
        "notes": "Flagged observations require careful review.",
    },
    "night_flag": {
        "description": "Flag indicating nighttime acquisition.",
        "units": "0/1",
        "notes": "Nighttime observations generally have lower solar background.",
    },
    "invalid_kd": {
        "description": "Flag indicating that a valid diffuse attenuation coefficient (Kd) was unavailable for uncertainty processing.",
        "units": "0/1",
        "notes": "Used in the ATL24 uncertainty calculation.",
    },
    "invalid_wind_speed": {
        "description": "Flag indicating that a valid wind-speed value was unavailable for uncertainty processing.",
        "units": "0/1",
        "notes": "Used in the ATL24 uncertainty calculation.",
    },
    "sigma_thu": {
        "description": "Estimated total horizontal uncertainty of the ATL24 photon position.",
        "units": "m",
        "notes": "Review the ATL24 ATBD for the full uncertainty model.",
    },
    "sigma_tvu": {
        "description": "Estimated total vertical uncertainty of the ATL24 photon height/depth solution.",
        "units": "m",
        "notes": "Review the ATL24 ATBD for the full uncertainty model.",
    },
    "index_ph": {
        "description": "Index of the corresponding source ATL03 photon within the beam.",
        "units": "index",
        "notes": "Use with source-granule identity and beam; not globally unique by itself.",
    },
}

MODEL_TIDE_FIELDS: dict[str, dict[str, str]] = {
    "depth_tide_corrected_m": {
        "description": "ATL24 water depth reduced by the modeled astronomical ocean tide.",
        "units": "m",
        "notes": "Calculated as depth - tide_ocean_model_m. This is a modeled mean-tide-level reduction, not a chart-datum transformation.",
    },
    "tide_ocean_model_m": {
        "description": "Astronomical ocean-tide elevation predicted by the selected pyTMD model at the photon location and UTC time.",
        "units": "m",
        "notes": "Not an observed water level and not a chart-datum transformation.",
    },
    "tide_time_utc": {
        "description": "UTC timestamp supplied to the tide model for the observation.",
        "units": "UTC datetime",
        "notes": "Derived from the source time_ns field.",
    },
    "tide_valid": {
        "description": "Validity flag for the model-tide result.",
        "units": "0/1",
        "notes": "1=finite model result; 0=invalid, masked or unavailable result.",
    },
    "tide_model": {
        "description": "Identifier of the tide model used for the prediction.",
        "units": "text",
        "notes": "Current implementation uses GOT4.10_nc/GOT4.10c.",
    },
    "tide_method": {
        "description": "Spatial interpolation method used by pyTMD.",
        "units": "text",
        "notes": "Typical values are linear or nearest.",
    },
}

PRODUCT_MAP = {
    "ATL03": ATL03_FIELDS,
    "ATL08": ATL08_FIELDS,
    "ATL13": ATL13_FIELDS,
    "ATL24": ATL24_FIELDS,
    "MODEL_TIDE": MODEL_TIDE_FIELDS,
}

VALUE_LABELS: dict[tuple[str, str], dict[Any, str]] = {
    ("ATL03", "atl03_cnf"): {
        -2: "possible TEP",
        -1: "not considered",
        0: "background/noise",
        1: "within 10 m",
        2: "low confidence",
        3: "medium confidence",
        4: "high confidence",
    },
    ("ATL03", "quality_ph"): {
        0: "nominal",
        1: "possible afterpulse",
        2: "possible impulse-response effect",
        3: "possible TEP",
    },
    ("ATL03", "atl08_class"): {
        0: "noise",
        1: "ground",
        2: "canopy",
        3: "top of canopy",
        4: "unclassified",
    },
    ("ATL03", "atl24_class"): {
        0: "unclassified",
        40: "bathymetry",
        41: "sea surface",
    },
}


def get_field_definition(
    product: str,
    field_name: str,
) -> dict[str, str]:
    """Return a documented field definition with a safe fallback."""
    product_key = str(product or "").upper()
    name = str(field_name)

    definition = COMMON_FIELDS.get(name)

    if definition is None:
        definition = PRODUCT_MAP.get(
            product_key,
            {},
        ).get(name)

    # SlideRule appends _x/_y when a requested ancillary field duplicates
    # a default output field. Explain the base field while retaining the
    # actual output name.
    if definition is None and name.endswith(("_x", "_y")):
        base_name = name[:-2]
        definition = (
            COMMON_FIELDS.get(base_name)
            or PRODUCT_MAP.get(
                product_key,
                {},
            ).get(base_name)
        )

        if definition is not None:
            definition = dict(definition)
            suffix_note = (
                "SlideRule added the suffix because the same field name "
                "was returned from more than one source."
            )
            existing = definition.get("notes", "")
            definition["notes"] = (
                existing + " " + suffix_note
            ).strip()

    if definition is None:
        return {
            "description": (
                "Field returned by SlideRule or created during GeoPackage "
                "export. A product-specific definition is not mapped in "
                "this plugin version."
            ),
            "units": "See source documentation",
            "notes": (
                "Consult the official product data dictionary and the "
                "SlideRule request parameters recorded in this report."
            ),
        }

    return dict(definition)


def get_value_label(
    product: str,
    field_name: str,
    value: Any,
) -> str | None:
    labels = VALUE_LABELS.get(
        (
            str(product or "").upper(),
            str(field_name),
        ),
        {},
    )

    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = value

    return labels.get(normalized)
