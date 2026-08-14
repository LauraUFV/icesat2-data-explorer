from __future__ import annotations

import copy
import json
import sqlite3
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import sliderule
from sliderule import earthdata

from qgis.PyQt.QtCore import pyqtSignal
from qgis.core import QgsTask


ATL03_INVALID_EXTENTS_PARAMETER = "pass_invalid"


class ATL03DownloadTask(QgsTask):
    progress_message = pyqtSignal(str)

    RESOURCE_REQUEST_ATTEMPTS = 2
    CMR_REQUEST_ATTEMPTS = 2
    REQUEST_RETRY_DELAY_SECONDS = 1.5
    MAX_DISCOVERED_RESOURCES = 5000
    DIAGNOSTIC_RESOURCE_LIMIT = 30
    MEDIAN_BUFFER_LIMIT = 500000

    ALL_BEAMS = (
        "gt1l",
        "gt1r",
        "gt2l",
        "gt2r",
        "gt3l",
        "gt3r",
    )

    """
    Background task that requests ATL03 photons from SlideRule, preserves
    the returned photon fields, writes a GeoPackage and creates a
    query_metadata attribute table.
    """

    GEOPHYSICS_FIELDS = (
        "geoid",
        "geoid_free2mean",
        "tide_ocean",
    )

    SUMMARY_FIELDS = (
        "height",
        "height_ortho",
        "geoid",
        "geoid_free2mean",
        "geoid_mean_tide",
        "tide_ocean",
        "solar_elevation",
        "background_rate",
        "x_atc",
        "y_atc",
    )

    CATEGORY_FIELDS = (
        "atl03_cnf",
        "quality_ph",
    )

    CONFIDENCE_NAMES = {
        -2: "possible_tep",
        -1: "not_considered",
        0: "background_noise",
        1: "within_10m",
        2: "low",
        3: "medium",
        4: "high",
    }

    QUALITY_NAMES = {
        0: "nominal",
        1: "possible_afterpulse",
        2: "possible_impulse_response",
        3: "possible_tep",
    }

    def __init__(
        self,
        parameters: dict[str, Any],
        output_path: str,
        layer_name: str,
        query_metadata: dict[str, Any] | None = None,
    ):
        super().__init__(
            "Download ATL03 photons",
            QgsTask.Flag.CanCancel,
        )

        self.parameters = parameters
        self.output_path = output_path
        self.layer_name = layer_name
        self.query_metadata = query_metadata or {}

        self.result_count = 0
        self.error_message: str | None = None
        self.error_traceback: str | None = None

        self.returned_columns: list[str] = []
        self.null_counts: dict[str, int] = {}
        self.numeric_fields: list[str] = []
        self.summary_statistics: dict[str, dict[str, float | int | None]] = {}
        self.category_counts: dict[str, dict[str, int]] = {}

        self.output_crs = "EPSG:4326"
        self.request_variant = "not_started"
        self.request_attempts: list[str] = []
        self.effective_parameters = copy.deepcopy(
            parameters
        )

        self.processing_strategy = (
            "CMR discovery + one ATL03 granule per SlideRule request + "
            "automatic retry + per-beam fallback + incremental GeoPackage"
        )
        self.discovery_variant = "not_started"
        self.granules_discovered = 0
        self.granules_processed = 0
        self.granules_with_data = 0
        self.granules_without_data = 0
        self.retry_count = 0
        self.beam_split_resources: list[str] = []
        self.diagnostic_resources_checked = 0
        self.statistics_note: str | None = None

        final_output = Path(self.output_path).expanduser()
        self._working_output = final_output.with_name(
            final_output.stem
            + ".__icesat2_partial__"
            + final_output.suffix
        )
        self._output_initialized = False
        self._schema_columns: list[str] = []
        self._schema_dropped_fields: set[str] = set()

        self._summary_accumulators: dict[str, dict[str, Any]] = {}
        self._category_accumulators: dict[str, dict[str, int]] = {}
        self._median_buffers: dict[str, list[np.ndarray] | None] = {}

    def run(self) -> bool:
        try:
            self._remove_partial_output()
            self.setProgress(2)
            self._emit_progress_message("Connecting to SlideRule...")
            if self.isCanceled():
                return False

            initialized = sliderule.init(
                url="slideruleearth.io",
                verbose=False,
                rethrow=True,
            )
            if initialized is False:
                raise RuntimeError("SlideRule initialization failed.")

            self.setProgress(7)
            if self.isCanceled():
                return False

            original = copy.deepcopy(self.parameters)
            original.setdefault("granule", {})
            original["granule"]["version"] = "007"
            self.effective_parameters = copy.deepcopy(original)

            self._emit_progress_message(
                "Discovering ATL03 Version 7 granules in NASA CMR..."
            )
            resources = self._discover_resources(original)
            self.granules_discovered = len(resources)

            if not resources:
                self.request_variant = "v007_cmr_no_resources"
                self.result_count = 0
                self.setProgress(100)
                self._emit_progress_message(
                    "No ATL03 Version 7 granules were discovered for "
                    "the selected area and period."
                )
                return True

            self._emit_progress_message(
                f"Found {len(resources):,} ATL03 Version 7 granule(s). "
                "Processing one granule at a time..."
            )
            self.setProgress(12)

            for resource_index, resource in enumerate(resources, start=1):
                if self.isCanceled():
                    self._remove_partial_output()
                    return False

                self._emit_progress_message(
                    f"ATL03 granule {resource_index:,} / {len(resources):,}: "
                    f"{resource} | {self.result_count:,} photons written"
                )

                chunks, variant = self._download_resource_with_fallbacks(
                    original=original,
                    resource=resource,
                )
                self.granules_processed += 1
                nonempty_chunks = [
                    chunk for chunk in chunks
                    if chunk is not None and not chunk.empty
                ]

                if not nonempty_chunks:
                    self.granules_without_data += 1
                else:
                    self.granules_with_data += 1
                    self.request_variant = variant
                    for raw_chunk in nonempty_chunks:
                        if self.isCanceled():
                            self._remove_partial_output()
                            return False
                        prepared = self._prepare_output(raw_chunk)
                        if prepared.empty:
                            continue
                        self._append_output_chunk(prepared)
                        self._update_incremental_statistics(prepared)

                self.setProgress(
                    12.0 + 73.0 * (resource_index / max(1, len(resources)))
                )

            if self.result_count == 0:
                self._emit_progress_message(
                    "No photons passed the selected ATL03 filters. "
                    "Running a limited filter diagnostic..."
                )
                self._diagnose_no_data(original=original, resources=resources)
                self.setProgress(100)
                return True

            self._finalize_incremental_statistics()
            self.setProgress(88)
            if self.isCanceled():
                self._remove_partial_output()
                return False

            self._write_query_metadata(output_file=self._working_output)
            self.setProgress(95)
            if self.isCanceled():
                self._remove_partial_output()
                return False

            self._commit_partial_output()
            self.setProgress(100)
            self._emit_progress_message(
                f"ATL03 completed: {self.result_count:,} photons from "
                f"{self.granules_with_data:,} / "
                f"{self.granules_discovered:,} discovered granules."
            )
            return True

        except Exception as error:
            self._remove_partial_output()
            self.error_message = f"{type(error).__name__}: {error}"
            self.error_traceback = traceback.format_exc()
            return False

    @staticmethod
    def _coerce_result(
        result,
    ) -> gpd.GeoDataFrame:
        if result is None:
            return gpd.GeoDataFrame()

        if isinstance(result, gpd.GeoDataFrame):
            return result

        return gpd.GeoDataFrame(result)

    def _emit_progress_message(self, message: str) -> None:
        try:
            self.progress_message.emit(str(message))
        except Exception:  # nosec B110
            pass

    @staticmethod
    def _is_transient_sliderule_error(error: Exception) -> bool:
        text = f"{type(error).__name__}: {error}".lower()
        transient_markers = (
            "unexpected termination of response",
            "timeout",
            "timed out",
            "connection",
            "connection reset",
            "remote end closed",
            "server disconnected",
            "chunkedencoding",
            "chunked encoding",
            "incomplete read",
            "eof",
            "502",
            "503",
            "504",
            "temporarily unavailable",
        )
        return any(marker in text for marker in transient_markers)

    def _cmr_query_with_retry(
        self,
        polygon: list[dict[str, float]],
        time_start: str,
        time_end: str,
        label: str,
    ) -> list[str]:
        last_error: Exception | None = None
        for attempt in range(1, self.CMR_REQUEST_ATTEMPTS + 1):
            if self.isCanceled():
                return []
            try:
                self.request_attempts.append(
                    f"cmr:{label}:attempt_{attempt}"
                )
                resources = earthdata.cmr(
                    short_name="ATL03",
                    version="007",
                    polygon=polygon,
                    time_start=time_start,
                    time_end=time_end,
                )
                if resources is None:
                    return []
                if isinstance(resources, tuple):
                    resources = resources[0]
                return [str(resource) for resource in resources if resource]
            except Exception as error:
                last_error = error
                if (
                    attempt < self.CMR_REQUEST_ATTEMPTS
                    and self._is_transient_sliderule_error(error)
                ):
                    self.retry_count += 1
                    self._emit_progress_message(
                        "CMR query was interrupted. Retrying "
                        f"({attempt + 1}/{self.CMR_REQUEST_ATTEMPTS})..."
                    )
                    time.sleep(self.REQUEST_RETRY_DELAY_SECONDS * attempt)
                    continue
                raise
        if last_error is not None:
            raise last_error
        return []

    @staticmethod
    def _bounding_box_polygon(
        polygon: list[dict[str, float]],
    ) -> list[dict[str, float]]:
        longitudes = [float(point["lon"]) for point in polygon]
        latitudes = [float(point["lat"]) for point in polygon]
        west, east = min(longitudes), max(longitudes)
        south, north = min(latitudes), max(latitudes)
        return [
            {"lon": west, "lat": south},
            {"lon": east, "lat": south},
            {"lon": east, "lat": north},
            {"lon": west, "lat": north},
            {"lon": west, "lat": south},
        ]

    def _discover_resources(self, original: dict[str, Any]) -> list[str]:
        polygon = copy.deepcopy(original.get("poly", []))
        time_start = str(original.get("t0", ""))
        time_end = str(original.get("t1", ""))
        if not polygon:
            raise RuntimeError(
                "ATL03 resource discovery requires an area-of-interest polygon."
            )

        try:
            resources = self._cmr_query_with_retry(
                polygon=polygon,
                time_start=time_start,
                time_end=time_end,
                label="exact_polygon",
            )
            self.discovery_variant = "CMR exact AOI polygon"
        except Exception as exact_error:
            self._emit_progress_message(
                "The exact CMR polygon query failed; retrying discovery "
                "with the AOI bounding box only. The exact polygon will still "
                "be used for photon subsetting."
            )
            try:
                resources = self._cmr_query_with_retry(
                    polygon=self._bounding_box_polygon(polygon),
                    time_start=time_start,
                    time_end=time_end,
                    label="bounding_box_fallback",
                )
                self.discovery_variant = "CMR AOI bounding-box fallback"
            except Exception:
                raise RuntimeError(
                    "ATL03 granule discovery failed for both the exact AOI "
                    "and its bounding box. The original CMR error was: "
                    f"{type(exact_error).__name__}: {exact_error}"
                ) from exact_error

        if not resources:
            fallback_resources = self._cmr_query_with_retry(
                polygon=self._bounding_box_polygon(polygon),
                time_start=time_start,
                time_end=time_end,
                label="empty_result_bounding_box",
            )
            if fallback_resources:
                resources = fallback_resources
                self.discovery_variant = (
                    "CMR AOI bounding-box fallback after empty exact query"
                )

        resources = sorted(dict.fromkeys(
            str(resource) for resource in resources if resource
        ))
        if len(resources) > self.MAX_DISCOVERED_RESOURCES:
            raise RuntimeError(
                "The ATL03 request intersects "
                f"{len(resources):,} Version 7 granules. This exceeds the "
                f"plugin safety limit of {self.MAX_DISCOVERED_RESOURCES:,} "
                "granules for one output. Reduce the date range or AOI."
            )
        return resources

    def _run_request_with_retry(
        self,
        parameters: dict[str, Any],
        variant: str,
        resource: str,
        beam: str | None = None,
    ) -> gpd.GeoDataFrame:
        last_error: Exception | None = None
        for attempt in range(1, self.RESOURCE_REQUEST_ATTEMPTS + 1):
            if self.isCanceled():
                return gpd.GeoDataFrame()
            attempt_label = (
                variant + ":" + resource
                + (f":{beam}" if beam else "")
                + f":attempt_{attempt}"
            )
            self.request_attempts.append(attempt_label)
            try:
                result = sliderule.run(
                    "atl03x",
                    parameters,
                    resources=[resource],
                )
                return self._coerce_result(result)
            except Exception as error:
                last_error = error
                if (
                    attempt < self.RESOURCE_REQUEST_ATTEMPTS
                    and self._is_transient_sliderule_error(error)
                ):
                    self.retry_count += 1
                    self._emit_progress_message(
                        "SlideRule response was interrupted for "
                        f"{resource}"
                        + (f" / {beam}" if beam else "")
                        + ". Retrying..."
                    )
                    time.sleep(self.REQUEST_RETRY_DELAY_SECONDS * attempt)
                    continue
                raise
        if last_error is not None:
            raise last_error
        return gpd.GeoDataFrame()

    def _request_resource_resilient(
        self,
        parameters: dict[str, Any],
        resource: str,
        variant: str,
    ) -> list[gpd.GeoDataFrame]:
        try:
            result = self._run_request_with_retry(
                parameters=parameters,
                variant=variant,
                resource=resource,
            )
            return [result]
        except Exception as error:
            if not self._is_transient_sliderule_error(error):
                raise

            selected_track = parameters.get("track", 0)
            if selected_track not in (None, 0, "0"):
                raise RuntimeError(
                    "A large ATL03 resource request was interrupted, but the "
                    "plugin cannot safely split this request by beam because "
                    "a nonzero track filter is active. Reduce the AOI/date "
                    "range for this request."
                ) from error

            requested_beams = parameters.get("beams")
            beams = (
                tuple(str(beam) for beam in requested_beams)
                if requested_beams
                else self.ALL_BEAMS
            )
            if resource not in self.beam_split_resources:
                self.beam_split_resources.append(resource)

            self._emit_progress_message(
                "The full-granule ATL03 stream was interrupted for "
                f"{resource}. Splitting that granule into "
                f"{len(beams)} beam request(s)..."
            )
            chunks: list[gpd.GeoDataFrame] = []
            for beam in beams:
                if self.isCanceled():
                    return []
                beam_parameters = copy.deepcopy(parameters)
                beam_parameters["beams"] = [beam]
                try:
                    beam_result = self._run_request_with_retry(
                        parameters=beam_parameters,
                        variant=variant + "_beam_split",
                        resource=resource,
                        beam=beam,
                    )
                except Exception as beam_error:
                    raise RuntimeError(
                        "ATL03 processing remained unstable after automatic "
                        "granule and beam splitting. Failed resource: "
                        f"{resource}; beam: {beam}. Last error: "
                        f"{type(beam_error).__name__}: {beam_error}"
                    ) from beam_error
                if not beam_result.empty:
                    chunks.append(beam_result)
            return chunks

    @staticmethod
    def _nonempty_chunks(
        chunks: list[gpd.GeoDataFrame],
    ) -> list[gpd.GeoDataFrame]:
        return [
            chunk for chunk in chunks
            if chunk is not None and not chunk.empty
        ]

    def _chunks_have_requested_geophysics(
        self,
        chunks: list[gpd.GeoDataFrame],
    ) -> bool:
        nonempty = self._nonempty_chunks(chunks)
        if not nonempty:
            return False
        return all(
            self._has_requested_geophysics(chunk)
            for chunk in nonempty
        )

    def _missing_geophysics_text(
        self,
        chunks: list[gpd.GeoDataFrame],
    ) -> str:
        returned_fields: set[str] = set()
        for chunk in self._nonempty_chunks(chunks):
            normalized = self._normalize_geophysics_fields(chunk)
            returned_fields.update(
                str(column) for column in normalized.columns
                if column != "geometry"
            )
        missing = [
            field_name for field_name in self.GEOPHYSICS_FIELDS
            if field_name not in returned_fields
        ]
        return (
            "missing=" + ", ".join(missing)
            + "; returned=" + ", ".join(sorted(returned_fields))
        )

    def _download_resource_with_fallbacks(
        self,
        original: dict[str, Any],
        resource: str,
    ) -> tuple[list[gpd.GeoDataFrame], str]:
        fields = list(self.GEOPHYSICS_FIELDS)

        primary = copy.deepcopy(original)
        primary.setdefault("granule", {})
        primary["granule"]["version"] = "007"
        primary.pop("atl03_cor_fields", None)
        primary["atl03_corr_fields"] = fields
        primary_chunks = self._request_resource_resilient(
            parameters=primary,
            resource=resource,
            variant="v007_atl03_corr_fields",
        )
        if self._chunks_have_requested_geophysics(primary_chunks):
            self.effective_parameters = primary
            return (
                self._nonempty_chunks(primary_chunks),
                "v007_atl03_corr_fields_resource_batch",
            )

        alternate = copy.deepcopy(original)
        alternate.setdefault("granule", {})
        alternate["granule"]["version"] = "007"
        alternate.pop("atl03_corr_fields", None)
        alternate["atl03_cor_fields"] = fields
        alternate_chunks = self._request_resource_resilient(
            parameters=alternate,
            resource=resource,
            variant="v007_atl03_cor_fields",
        )
        if self._chunks_have_requested_geophysics(alternate_chunks):
            self.effective_parameters = alternate
            return (
                self._nonempty_chunks(alternate_chunks),
                "v007_atl03_cor_fields_resource_batch",
            )

        first_nonempty = (
            self._nonempty_chunks(primary_chunks)
            or self._nonempty_chunks(alternate_chunks)
        )
        if first_nonempty:
            raise RuntimeError(
                "ATL03 Version 7 photons were returned for resource "
                f"{resource}, but the requested geophys_corr attributes "
                "were incomplete after both supported parameter spellings. "
                + self._missing_geophysics_text(first_nonempty)
            )
        return ([], "v007_resource_no_selected_photons")

    def _diagnose_no_data(
        self,
        original: dict[str, Any],
        resources: list[str],
    ) -> None:
        diagnostic_resources = resources[: self.DIAGNOSTIC_RESOURCE_LIMIT]
        self.diagnostic_resources_checked = len(diagnostic_resources)

        filtered_basic = copy.deepcopy(original)
        filtered_basic.pop("atl03_corr_fields", None)
        filtered_basic.pop("atl03_cor_fields", None)
        for resource in diagnostic_resources:
            chunks = self._request_resource_resilient(
                parameters=filtered_basic,
                resource=resource,
                variant="v007_selected_filters_without_geophysics_diagnostic",
            )
            if self._nonempty_chunks(chunks):
                raise RuntimeError(
                    "ATL03 Version 7 photons were found with the selected "
                    "surface/confidence/quality settings, but the SlideRule "
                    "server did not return geoid, geoid_free2mean and "
                    "tide_ocean with either ancillary-field parameter spelling."
                )

        broad_surface_types = {
            0: "Land",
            1: "Ocean",
            4: "Inland water",
        }
        for resource in diagnostic_resources:
            for surface_code, surface_label in broad_surface_types.items():
                diagnostic = {
                    "poly": copy.deepcopy(original.get("poly", [])),
                    "t0": original.get("t0"),
                    "t1": original.get("t1"),
                    "srt": surface_code,
                    "cnf": -2,
                    "quality_ph": [0, 1, 2, 3],
                    ATL03_INVALID_EXTENTS_PARAMETER: True,
                    "granule": {"version": "007"},
                }
                chunks = self._request_resource_resilient(
                    parameters=diagnostic,
                    resource=resource,
                    variant=(
                        "v007_broad_"
                        + surface_label.lower().replace(" ", "_")
                        + "_diagnostic"
                    ),
                )
                nonempty = self._nonempty_chunks(chunks)
                if nonempty:
                    count = sum(len(chunk) for chunk in nonempty)
                    raise RuntimeError(
                        "ATL03 Version 7 data exist inside the selected AOI "
                        "and date range, but the selected native photon "
                        "filters returned no records. A permissive diagnostic "
                        f"found {count:,} {surface_label} photon(s) in "
                        f"resource {resource}. Selected srt code: "
                        f"{original.get('srt')}. Choose the matching surface "
                        "type and run the request again."
                    )
        self.request_variant = "v007_no_data_after_batched_filter_diagnostics"

    def _has_requested_geophysics(
        self,
        result: gpd.GeoDataFrame,
    ) -> bool:
        if result.empty:
            return False
        normalized = self._normalize_geophysics_fields(result)
        return all(
            field_name in normalized.columns
            for field_name in self.GEOPHYSICS_FIELDS
        )

    def _prepare_output(
        self,
        result: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        result = result.copy()

        # SlideRule normally stores time_ns in the DataFrame index.
        if (
            result.index.name is not None
            or not isinstance(result.index, pd.RangeIndex)
        ):
            index_name = result.index.name or "time_ns"

            if index_name in result.columns:
                result = result.reset_index(drop=True)
            else:
                result = result.reset_index()

                if "index" in result.columns and "time_ns" not in result.columns:
                    result = result.rename(
                        columns={"index": "time_ns"}
                    )
                elif (
                    index_name in result.columns
                    and index_name != "time_ns"
                    and "time_ns" not in result.columns
                ):
                    result = result.rename(
                        columns={index_name: "time_ns"}
                    )

        if "geometry" not in result.columns:
            if {"longitude", "latitude"}.issubset(result.columns):
                result = gpd.GeoDataFrame(
                    result,
                    geometry=gpd.points_from_xy(
                        result["longitude"],
                        result["latitude"],
                    ),
                    crs="EPSG:4326",
                )
            else:
                raise ValueError(
                    "SlideRule returned ATL03 data without geometry."
                )

        if result.crs is None:
            result = result.set_crs(
                "EPSG:4326",
                allow_override=True,
            )
        else:
            result = result.to_crs("EPSG:4326")

        result["longitude"] = result.geometry.x
        result["latitude"] = result.geometry.y

        if "height" not in result.columns:
            raise ValueError(
                "SlideRule returned ATL03 data without the photon height field."
            )

        result = self._normalize_geophysics_fields(
            result
        )

        missing_geophysics = [
            field_name
            for field_name in self.GEOPHYSICS_FIELDS
            if field_name not in result.columns
        ]

        if missing_geophysics:
            returned_fields = ", ".join(
                str(column)
                for column in result.columns
                if column != "geometry"
            )

            raise RuntimeError(
                "SlideRule returned ATL03 photons but did not return the "
                "requested geophys_corr fields: "
                + ", ".join(missing_geophysics)
                + ". Request variant: "
                + self.request_variant
                + ". Returned fields were: "
                + returned_fields
            )

        geoid_values = pd.to_numeric(
            result["geoid"],
            errors="coerce",
        )
        free_to_mean_values = pd.to_numeric(
            result["geoid_free2mean"],
            errors="coerce",
        )

        height_values = pd.to_numeric(
            result["height"],
            errors="coerce",
        )

        # Orthometric/geoidal photon height referenced to the
        # EGM2008 tide-free geoid supplied by ATL03.
        #
        # H = h - N
        #
        # The ATL03 ocean-tide correction is intentionally not applied.
        result["height_ortho"] = (
            height_values
            - geoid_values
        )

        result["geoid_mean_tide"] = (
            geoid_values
            + free_to_mean_values
        )

        if "atl03_cnf" in result.columns:
            confidence_codes = pd.to_numeric(
                result["atl03_cnf"],
                errors="coerce",
            )
            result["atl03_cnf_name"] = confidence_codes.apply(
                self._confidence_name
            )

        if "quality_ph" in result.columns:
            quality_codes = pd.to_numeric(
                result["quality_ph"],
                errors="coerce",
            )
            result["quality_name"] = quality_codes.apply(
                self._quality_name
            )

        result = self._replace_non_finite_values(result)
        result = self._serialize_complex_columns(result)

        preferred_columns = [
            "time",
            "time_ns",
            "latitude",
            "longitude",
            "height",
            "height_ortho",
            "geoid",
            "geoid_free2mean",
            "geoid_mean_tide",
            "tide_ocean",
            "atl03_cnf",
            "atl03_cnf_name",
            "quality_ph",
            "quality_name",
            "ph_index",
            "solar_elevation",
            "background_rate",
            "spacecraft_velocity",
            "x_atc",
            "y_atc",
            "signal_class_ph",
            "weight_ph",
            "yapc_score",
            "atl08_class",
            "atl24_class",
            "atl24_confidence",
            "spot",
            "cycle",
            "region",
            "rgt",
            "gt",
            "srcid",
            "geometry",
        ]

        available_preferred = [
            column
            for column in preferred_columns
            if column in result.columns
        ]

        additional_columns = [
            column
            for column in result.columns
            if column not in available_preferred
            and column != "geometry"
        ]

        final_columns = [
            column
            for column in available_preferred
            if column != "geometry"
        ]
        final_columns.extend(additional_columns)
        final_columns.append("geometry")

        return result[final_columns].copy()

    @classmethod
    def _normalize_geophysics_fields(
        cls,
        result: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        """
        Normalize SlideRule ancillary-field names to stable attribute names.

        Depending on the server/client combination, ancillary fields can be
        returned with a group prefix or with pandas merge suffixes. The plugin
        always exposes geoid, geoid_free2mean and tide_ocean in the GeoPackage.
        """
        result = result.copy()

        aliases = {
            "geoid": (
                "geoid",
                "geoid_y",
                "geophys_corr/geoid",
                "geophys_corr_geoid",
                "atl03_corr_geoid",
                "atl03_cor_geoid",
            ),
            "geoid_free2mean": (
                "geoid_free2mean",
                "geoid_free2mean_y",
                "geophys_corr/geoid_free2mean",
                "geophys_corr_geoid_free2mean",
                "atl03_corr_geoid_free2mean",
                "atl03_cor_geoid_free2mean",
            ),
            "tide_ocean": (
                "tide_ocean",
                "tide_ocean_y",
                "geophys_corr/tide_ocean",
                "geophys_corr_tide_ocean",
                "atl03_corr_tide_ocean",
                "atl03_cor_tide_ocean",
            ),
        }

        for canonical_name, candidates in aliases.items():
            if canonical_name in result.columns:
                continue

            source_name = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate in result.columns
                ),
                None,
            )

            if source_name is not None:
                result[canonical_name] = result[source_name]

        return result

    @classmethod
    def _confidence_name(cls, value: Any) -> str | None:
        if pd.isna(value):
            return None

        try:
            code = int(value)
        except (TypeError, ValueError):
            return str(value)

        return cls.CONFIDENCE_NAMES.get(
            code,
            f"code_{code}",
        )

    @classmethod
    def _quality_name(cls, value: Any) -> str | None:
        if pd.isna(value):
            return None

        try:
            code = int(value)
        except (TypeError, ValueError):
            return str(value)

        return cls.QUALITY_NAMES.get(
            code,
            f"atl03_v7_code_{code}",
        )

    @staticmethod
    def _replace_non_finite_values(
        result: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        result = result.copy()

        for column in result.columns:
            if column == "geometry":
                continue

            if pd.api.types.is_numeric_dtype(result[column]):
                result[column] = result[column].replace(
                    [np.inf, -np.inf],
                    np.nan,
                )

        return result

    @staticmethod
    def _is_complex_value(value: Any) -> bool:
        return isinstance(
            value,
            (list, tuple, dict, set, np.ndarray),
        )

    @staticmethod
    def _is_missing_scalar(value: Any) -> bool:
        if isinstance(
            value,
            (list, tuple, dict, set, np.ndarray),
        ):
            return False

        try:
            return bool(pd.isna(value))
        except (TypeError, ValueError):
            return False

    @classmethod
    def _serialize_complex_columns(
        cls,
        result: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        result = result.copy()

        for column in result.columns:
            if column == "geometry":
                continue

            series = result[column]

            if series.dtype != object:
                continue

            sample_values = [
                value
                for value in series
                if value is not None
                and not cls._is_missing_scalar(value)
            ]

            if not sample_values:
                continue

            if not any(
                cls._is_complex_value(value)
                for value in sample_values[:20]
            ):
                continue

            result[column] = series.apply(cls._serialize_value)

        return result

    @classmethod
    def _serialize_value(cls, value: Any) -> str | None:
        if value is None or cls._is_missing_scalar(value):
            return None

        if isinstance(value, np.ndarray):
            value = value.tolist()
        elif isinstance(value, set):
            value = list(value)
        elif isinstance(value, tuple):
            value = list(value)

        return json.dumps(
            value,
            ensure_ascii=False,
            default=cls._json_default,
        )

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, np.integer):
            return int(value)

        if isinstance(value, np.floating):
            return float(value)

        if isinstance(value, np.ndarray):
            return value.tolist()

        return str(value)

    @classmethod
    def _calculate_null_counts(
        cls,
        result: gpd.GeoDataFrame,
    ) -> dict[str, int]:
        fields = set(cls.SUMMARY_FIELDS) | set(cls.CATEGORY_FIELDS)
        fields.update(
            {
                "time_ns",
                "latitude",
                "longitude",
                "ph_index",
            }
        )

        return {
            field_name: int(result[field_name].isna().sum())
            for field_name in fields
            if field_name in result.columns
        }

    @staticmethod
    def _get_numeric_fields(
        result: gpd.GeoDataFrame,
    ) -> list[str]:
        return [
            str(column)
            for column in result.columns
            if column != "geometry"
            and pd.api.types.is_numeric_dtype(result[column])
        ]

    @classmethod
    def _calculate_summary_statistics(
        cls,
        result: gpd.GeoDataFrame,
    ) -> dict[str, dict[str, float | int | None]]:
        statistics: dict[str, dict[str, float | int | None]] = {}

        for field_name in cls.SUMMARY_FIELDS:
            if field_name not in result.columns:
                continue

            values = pd.to_numeric(
                result[field_name],
                errors="coerce",
            ).dropna()

            if values.empty:
                statistics[field_name] = {
                    "valid_count": 0,
                    "minimum": None,
                    "maximum": None,
                    "mean": None,
                    "median": None,
                }
                continue

            statistics[field_name] = {
                "valid_count": int(values.count()),
                "minimum": float(values.min()),
                "maximum": float(values.max()),
                "mean": float(values.mean()),
                "median": float(values.median()),
            }

        return statistics

    @classmethod
    def _calculate_category_counts(
        cls,
        result: gpd.GeoDataFrame,
    ) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = {}

        for field_name in cls.CATEGORY_FIELDS:
            if field_name not in result.columns:
                continue

            values = pd.to_numeric(
                result[field_name],
                errors="coerce",
            ).dropna()

            field_counts = values.value_counts().sort_index()
            counts[field_name] = {
                str(int(code)): int(count)
                for code, count in field_counts.items()
            }

        return counts

    def _remove_partial_output(self) -> None:
        try:
            if self._working_output.exists():
                self._working_output.unlink()
        except OSError:
            pass

    def _append_output_chunk(
        self,
        result: gpd.GeoDataFrame,
    ) -> None:
        self._working_output.parent.mkdir(parents=True, exist_ok=True)
        result = result.copy()
        if not self._output_initialized:
            self._schema_columns = [str(column) for column in result.columns]
            result.to_file(
                self._working_output,
                layer=self.layer_name,
                driver="GPKG",
                index=False,
            )
            self._output_initialized = True
            return

        additional_fields = [
            str(column) for column in result.columns
            if str(column) not in self._schema_columns
        ]
        if additional_fields:
            self._schema_dropped_fields.update(additional_fields)

        missing_fields = [
            column for column in self._schema_columns
            if column not in result.columns and column != "geometry"
        ]
        for column in missing_fields:
            result[column] = np.nan
        if "geometry" not in result.columns:
            raise RuntimeError(
                "An ATL03 batch was returned without geometry after the "
                "output GeoPackage schema had already been created."
            )
        result = result[self._schema_columns].copy()
        result = gpd.GeoDataFrame(
            result,
            geometry="geometry",
            crs="EPSG:4326",
        )
        result.to_file(
            self._working_output,
            layer=self.layer_name,
            driver="GPKG",
            index=False,
            mode="a",
        )

    def _update_incremental_statistics(
        self,
        result: gpd.GeoDataFrame,
    ) -> None:
        count = len(result)
        self.result_count += count
        for column in result.columns:
            if column == "geometry":
                continue
            column_name = str(column)
            if column_name not in self.returned_columns:
                self.returned_columns.append(column_name)
            if (
                pd.api.types.is_numeric_dtype(result[column])
                and column_name not in self.numeric_fields
            ):
                self.numeric_fields.append(column_name)

        null_fields = set(self.SUMMARY_FIELDS) | set(self.CATEGORY_FIELDS)
        null_fields.update({"time_ns", "latitude", "longitude", "ph_index"})
        for field_name in null_fields:
            if field_name not in result.columns:
                continue
            self.null_counts[field_name] = (
                self.null_counts.get(field_name, 0)
                + int(result[field_name].isna().sum())
            )

        for field_name in self.SUMMARY_FIELDS:
            if field_name not in result.columns:
                continue
            values = pd.to_numeric(
                result[field_name], errors="coerce"
            ).dropna()
            if values.empty:
                continue
            accumulator = self._summary_accumulators.setdefault(
                field_name,
                {"count": 0, "sum": 0.0, "minimum": None, "maximum": None},
            )
            field_count = int(values.count())
            field_minimum = float(values.min())
            field_maximum = float(values.max())
            field_sum = float(values.sum())
            accumulator["count"] += field_count
            accumulator["sum"] += field_sum
            accumulator["minimum"] = (
                field_minimum
                if accumulator["minimum"] is None
                else min(float(accumulator["minimum"]), field_minimum)
            )
            accumulator["maximum"] = (
                field_maximum
                if accumulator["maximum"] is None
                else max(float(accumulator["maximum"]), field_maximum)
            )

            if field_name not in self._median_buffers:
                self._median_buffers[field_name] = []
            median_buffer = self._median_buffers[field_name]
            if median_buffer is not None:
                existing_count = sum(len(array) for array in median_buffer)
                if existing_count + field_count <= self.MEDIAN_BUFFER_LIMIT:
                    median_buffer.append(
                        values.to_numpy(dtype=float, copy=True)
                    )
                else:
                    self._median_buffers[field_name] = None

        for field_name in self.CATEGORY_FIELDS:
            if field_name not in result.columns:
                continue
            values = pd.to_numeric(
                result[field_name], errors="coerce"
            ).dropna()
            field_counter = self._category_accumulators.setdefault(
                field_name, {}
            )
            for code, value_count in values.value_counts().items():
                key = str(int(code))
                field_counter[key] = (
                    field_counter.get(key, 0) + int(value_count)
                )

    def _finalize_incremental_statistics(self) -> None:
        statistics: dict[str, dict[str, float | int | None]] = {}
        median_omitted = []
        for field_name in self.SUMMARY_FIELDS:
            accumulator = self._summary_accumulators.get(field_name)
            if not accumulator:
                statistics[field_name] = {
                    "valid_count": 0,
                    "minimum": None,
                    "maximum": None,
                    "mean": None,
                    "median": None,
                }
                continue
            valid_count = int(accumulator["count"])
            median_buffer = self._median_buffers.get(field_name)
            if median_buffer is None:
                median_value = None
                median_omitted.append(field_name)
            elif median_buffer:
                median_value = float(np.median(np.concatenate(median_buffer)))
            else:
                median_value = None
            statistics[field_name] = {
                "valid_count": valid_count,
                "minimum": accumulator["minimum"],
                "maximum": accumulator["maximum"],
                "mean": (
                    float(accumulator["sum"]) / valid_count
                    if valid_count else None
                ),
                "median": median_value,
            }
        self.summary_statistics = statistics
        self.category_counts = {
            field_name: dict(sorted(
                values.items(), key=lambda item: int(item[0])
            ))
            for field_name, values in self._category_accumulators.items()
        }
        if median_omitted:
            self.statistics_note = (
                "Exact median was intentionally omitted for high-volume "
                "ATL03 fields after the in-memory median buffer exceeded "
                f"{self.MEDIAN_BUFFER_LIMIT:,} valid values. Minimum, "
                "maximum and mean remain exact. Fields: "
                + ", ".join(median_omitted)
            )

    def _commit_partial_output(self) -> None:
        if not self._output_initialized:
            return
        final_output = Path(self.output_path).expanduser()
        final_output.parent.mkdir(parents=True, exist_ok=True)
        if final_output.exists():
            final_output.unlink()
        self._working_output.replace(final_output)

    def _write_query_metadata(
        self,
        output_file: Path | None = None,
    ) -> None:
        output_file = (
            Path(output_file)
            if output_file is not None
            else Path(self.output_path)
        )
        metadata = dict(self.query_metadata)

        metadata.update(
            {
                "request_date_utc": datetime.now(timezone.utc).isoformat(),
                "sliderule_endpoint": "atl03x",
                "sliderule_host": "slideruleearth.io",
                "sliderule_client_version": getattr(
                    sliderule,
                    "__version__",
                    "unknown",
                ),
                "record_count": self.result_count,
                "crs": self.output_crs,
                "returned_field_count": len(self.returned_columns),
                "returned_fields": self.returned_columns,
                "numeric_fields": self.numeric_fields,
                "null_counts": self.null_counts,
                "summary_statistics": self.summary_statistics,
                "category_counts": self.category_counts,
                "request_parameters": self.effective_parameters,
                "request_variant": self.request_variant,
                "request_attempts": self.request_attempts,
                "processing_strategy": self.processing_strategy,
                "resource_discovery": self.discovery_variant,
                "granules_discovered": self.granules_discovered,
                "granules_processed": self.granules_processed,
                "granules_with_data": self.granules_with_data,
                "granules_without_data": self.granules_without_data,
                "retry_count": self.retry_count,
                "beam_split_resources": self.beam_split_resources,
                "diagnostic_resources_checked": self.diagnostic_resources_checked,
                "statistics_note": self.statistics_note,
                "schema_dropped_optional_fields": sorted(
                    self._schema_dropped_fields
                ),
            }
        )

        metadata_rows = [
            (
                str(key),
                self._metadata_value_to_text(value),
            )
            for key, value in metadata.items()
        ]

        connection = sqlite3.connect(str(output_file))

        try:
            cursor = connection.cursor()
            cursor.execute("DROP TABLE IF EXISTS query_metadata")
            cursor.execute(
                """
                CREATE TABLE query_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parameter TEXT NOT NULL,
                    value TEXT
                )
                """
            )
            cursor.executemany(
                """
                INSERT INTO query_metadata (
                    parameter,
                    value
                )
                VALUES (?, ?)
                """,
                metadata_rows,
            )
            cursor.execute(
                """
                DELETE FROM gpkg_contents
                WHERE table_name = 'query_metadata'
                """
            )
            cursor.execute(
                """
                INSERT INTO gpkg_contents (
                    table_name,
                    data_type,
                    identifier,
                    description,
                    last_change,
                    min_x,
                    min_y,
                    max_x,
                    max_y,
                    srs_id
                )
                VALUES (
                    'query_metadata',
                    'attributes',
                    'query_metadata',
                    'ICESat-2 Data Explorer ATL03 query metadata',
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    @classmethod
    def _metadata_value_to_text(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(
            value,
            (dict, list, tuple, set, np.ndarray),
        ):
            if isinstance(value, set):
                value = list(value)
            if isinstance(value, np.ndarray):
                value = value.tolist()

            return json.dumps(
                value,
                ensure_ascii=False,
                default=cls._json_default,
            )

        return str(value)
