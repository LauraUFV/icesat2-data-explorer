from __future__ import annotations

import copy
import json
import traceback
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import sliderule

from qgis.core import QgsTask


class ATL24DownloadTask(QgsTask):
    """
    Background task for ATL24 acquisition through SlideRule.

    All returned columns are preserved. In particular, ancillary ATL24 fields
    such as index_ph are retained when requested by the plugin.
    """

    def __init__(
        self,
        parameters: dict[str, Any],
        output_path: str,
        layer_name: str,
    ):
        super().__init__(
            "Download ATL24 bathymetry",
            QgsTask.Flag.CanCancel,
        )

        self.parameters = parameters
        self.output_path = output_path
        self.layer_name = layer_name

        self.result_count = 0
        self.error_message: str | None = None
        self.error_traceback: str | None = None

        self.returned_columns: list[str] = []
        self.null_counts: dict[str, int] = {}
        self.output_crs = "EPSG:4326"

        self.requested_release = str(
            parameters.get(
                "granule",
                {},
            ).get(
                "version",
                "002",
            )
        )
        self.request_variant = "not_started"
        self.request_attempts: list[str] = []
        self.effective_parameters = copy.deepcopy(
            parameters
        )

    def run(self) -> bool:
        try:
            self.setProgress(5)

            if self.isCanceled():
                return False

            initialized = sliderule.init(
                url="slideruleearth.io",
                verbose=False,
                rethrow=True,
            )

            if initialized is False:
                raise RuntimeError(
                    "SlideRule initialization failed."
                )

            self.setProgress(15)

            if self.isCanceled():
                return False

            result = self._download_with_diagnostics()

            self.setProgress(65)

            if self.isCanceled():
                return False

            if result is None:
                return True

            if not isinstance(result, gpd.GeoDataFrame):
                result = gpd.GeoDataFrame(result)

            if result.empty:
                return True

            result = self._prepare_output(result)

            self.result_count = len(result)
            self.returned_columns = [
                str(column)
                for column in result.columns
                if column != "geometry"
            ]
            self.null_counts = self._calculate_null_counts(
                result
            )

            self.setProgress(80)

            if self.isCanceled():
                return False

            self._write_geopackage(result)

            self.setProgress(100)
            return True

        except Exception as error:
            self.error_message = (
                f"{type(error).__name__}: {error}"
            )
            self.error_traceback = traceback.format_exc()
            return False

    @staticmethod
    def _coerce_result(
        result,
    ) -> gpd.GeoDataFrame:
        if result is None:
            return gpd.GeoDataFrame()

        if isinstance(
            result,
            gpd.GeoDataFrame,
        ):
            return result

        return gpd.GeoDataFrame(
            result
        )

    def _run_atl24_request(
        self,
        parameters: dict[str, Any],
        variant: str,
    ) -> gpd.GeoDataFrame:
        self.request_attempts.append(
            variant
        )

        result = sliderule.run(
            "atl24x",
            parameters,
        )

        return self._coerce_result(
            result
        )

    @staticmethod
    def _class_code_series(
        result: gpd.GeoDataFrame,
    ) -> pd.Series:
        if "class_ph" not in result.columns:
            return pd.Series(
                index=result.index,
                dtype="float64",
            )

        raw = result["class_ph"]

        numeric = pd.to_numeric(
            raw,
            errors="coerce",
        )

        text_mapping = {
            "unclassified": 0,
            "bathymetry": 40,
            "sea_surface": 41,
            "sea surface": 41,
        }

        missing_mask = numeric.isna()

        if missing_mask.any():
            normalized_text = (
                raw.astype(str)
                .str.strip()
                .str.lower()
            )
            numeric.loc[
                missing_mask
            ] = normalized_text.loc[
                missing_mask
            ].map(
                text_mapping
            )

        return numeric

    @classmethod
    def _class_counts(
        cls,
        result: gpd.GeoDataFrame,
    ) -> dict[str, int]:
        codes = cls._class_code_series(
            result
        )

        return {
            "unclassified": int(
                (codes == 0).sum()
            ),
            "bathymetry": int(
                (codes == 40).sum()
            ),
            "sea_surface": int(
                (codes == 41).sum()
            ),
            "unknown": int(
                codes.isna().sum()
            ),
        }

    @classmethod
    def _client_filter_bathymetry(
        cls,
        result: gpd.GeoDataFrame,
        atl24_parameters: dict[str, Any],
    ) -> gpd.GeoDataFrame:
        if result.empty:
            return result

        mask = (
            cls._class_code_series(
                result
            )
            == 40
        )

        confidence_threshold = float(
            atl24_parameters.get(
                "confidence_threshold",
                0.0,
            )
            or 0.0
        )

        if (
            confidence_threshold > 0.0
            and "confidence" in result.columns
        ):
            confidence = pd.to_numeric(
                result["confidence"],
                errors="coerce",
            )
            mask &= (
                confidence
                >= confidence_threshold
            )

        flag_rules = {
            "low_confidence": "low_confidence_flag",
            "sensor_depth_exceeded": "sensor_depth_exceeded",
            "invalid_kd": "invalid_kd",
            "invalid_wind_speed": "invalid_wind_speed",
        }

        for parameter_name, column_name in flag_rules.items():
            if (
                atl24_parameters.get(
                    parameter_name
                )
                == "off"
                and column_name in result.columns
            ):
                flag_values = pd.to_numeric(
                    result[column_name],
                    errors="coerce",
                )
                mask &= (
                    flag_values == 0
                )

        return result.loc[
            mask
        ].copy()

    @staticmethod
    def _common_request(
        parameters: dict[str, Any],
        release: str,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "granule": {
                "version": release,
            },
        }

        for field_name in (
            "poly",
            "t0",
            "t1",
            "rgt",
            "cycle",
            "beams",
        ):
            if field_name in parameters:
                request[field_name] = copy.deepcopy(
                    parameters[field_name]
                )

        return request

    def _broad_release_request(
        self,
        original: dict[str, Any],
        release: str,
        label: str,
    ) -> gpd.GeoDataFrame:
        broad = self._common_request(
            original,
            release,
        )
        broad["atl24"] = {
            "compact": False,
            "class_ph": [
                0,
                40,
                41,
            ],
            "confidence_threshold": 0.0,
        }

        return self._run_atl24_request(
            broad,
            label,
        )

    def _download_with_diagnostics(
        self,
    ) -> gpd.GeoDataFrame:
        """
        Download ATL24 while handling current and historical parameter syntax.

        The routine first uses Version 2/current numeric class codes and
        top-level anc_fields. It then tests the historical string class label
        and nested ancillary-field placement. A broad class request determines
        whether granules intersect the AOI but contain no bathymetry after the
        selected filters. Finally, the alternate ATL24 release is checked for
        comparison.
        """
        original = copy.deepcopy(
            self.parameters
        )
        release = self.requested_release
        requested_atl24 = copy.deepcopy(
            original.get(
                "atl24",
                {},
            )
        )

        primary = copy.deepcopy(
            original
        )
        primary.setdefault(
            "granule",
            {},
        )
        primary["granule"][
            "version"
        ] = release
        primary.setdefault(
            "atl24",
            {},
        )
        primary["atl24"][
            "class_ph"
        ] = [
            40,
        ]

        primary_result = self._run_atl24_request(
            primary,
            (
                "release_"
                + release
                + "_numeric_class_top_level_ancillary"
            ),
        )

        if not primary_result.empty:
            self.request_variant = (
                "numeric_class_top_level_ancillary"
            )
            self.effective_parameters = primary
            self.parameters = primary
            return primary_result

        compatibility = copy.deepcopy(
            original
        )
        compatibility.setdefault(
            "granule",
            {},
        )
        compatibility["granule"][
            "version"
        ] = release

        ancillary_fields = compatibility.pop(
            "anc_fields",
            [
                "index_ph",
            ],
        )

        compatibility.setdefault(
            "atl24",
            {},
        )
        compatibility["atl24"][
            "class_ph"
        ] = [
            "bathymetry",
        ]
        compatibility["atl24"][
            "anc_fields"
        ] = ancillary_fields

        compatibility_result = self._run_atl24_request(
            compatibility,
            (
                "release_"
                + release
                + "_string_class_nested_ancillary"
            ),
        )

        if not compatibility_result.empty:
            self.request_variant = (
                "string_class_nested_ancillary"
            )
            self.effective_parameters = compatibility
            self.parameters = compatibility
            return compatibility_result

        broad_result = self._broad_release_request(
            original,
            release,
            (
                "release_"
                + release
                + "_all_classes_no_quality_filters"
            ),
        )

        if not broad_result.empty:
            class_counts = self._class_counts(
                broad_result
            )
            locally_filtered = self._client_filter_bathymetry(
                broad_result,
                requested_atl24,
            )

            if not locally_filtered.empty:
                self.request_variant = (
                    "all_classes_with_client_side_bathymetry_filter"
                )
                self.effective_parameters = self._common_request(
                    original,
                    release,
                )
                self.effective_parameters[
                    "atl24"
                ] = {
                    "compact": False,
                    "class_ph": [
                        0,
                        40,
                        41,
                    ],
                    "confidence_threshold": 0.0,
                }
                self.parameters = self.effective_parameters
                return locally_filtered

            count_text = (
                f"unclassified={class_counts['unclassified']:,}, "
                f"bathymetry={class_counts['bathymetry']:,}, "
                f"sea_surface={class_counts['sea_surface']:,}, "
                f"unknown={class_counts['unknown']:,}"
            )

            if class_counts[
                "bathymetry"
            ] > 0:
                raise RuntimeError(
                    "ATL24 records intersect the selected AOI and dates, "
                    "but the active confidence/quality filters removed all "
                    "bathymetry photons. Broad class counts: "
                    + count_text
                    + ". Set Minimum confidence to 0 and uncheck all ATL24 "
                    "exclusion options for the next test."
                )

            raise RuntimeError(
                "ATL24 granules intersect the selected AOI and dates, but "
                "the selected release contains no photons classified as "
                "bathymetry (class 40). Broad class counts: "
                + count_text
                + ". This can occur when Version 2 reclassifies photons that "
                "were present in Version 1."
            )

        alternate_release = (
            "001"
            if release == "002"
            else "002"
        )
        alternate_result = self._broad_release_request(
            original,
            alternate_release,
            (
                "release_"
                + alternate_release
                + "_comparison_diagnostic"
            ),
        )

        if not alternate_result.empty:
            alternate_counts = self._class_counts(
                alternate_result
            )
            alternate_bathymetry = alternate_counts[
                "bathymetry"
            ]

            alternate_label = (
                "Version 1"
                if alternate_release == "001"
                else "Version 2"
            )
            requested_label = (
                "Version 2"
                if release == "002"
                else "Version 1"
            )

            if alternate_bathymetry > 0:
                raise RuntimeError(
                    f"No ATL24 {requested_label} records were returned, but "
                    f"the {alternate_label} comparison found "
                    f"{alternate_bathymetry:,} bathymetry photons. Select "
                    f"{alternate_label} in ATL24 settings and run again. "
                    "Do not mix releases silently in the same analysis."
                )

            raise RuntimeError(
                f"No ATL24 {requested_label} records were returned. The "
                f"{alternate_label} comparison found ATL24 records, but none "
                "were classified as bathymetry."
            )

        self.request_variant = (
            "no_records_after_release_diagnostics"
        )
        self.effective_parameters = primary
        self.parameters = primary
        return gpd.GeoDataFrame()

    def _prepare_output(
        self,
        result: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        result = result.copy()

        # SlideRule normally places time_ns in the DataFrame index.
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

        if "geometry" not in result.columns:
            if {
                "longitude",
                "latitude",
            }.issubset(result.columns):
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
                    "SlideRule returned ATL24 data without geometry."
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

        if (
            "depth" not in result.columns
            and {
                "surface_h",
                "ortho_h",
            }.issubset(result.columns)
        ):
            result["depth"] = (
                pd.to_numeric(
                    result["surface_h"],
                    errors="coerce",
                )
                - pd.to_numeric(
                    result["ortho_h"],
                    errors="coerce",
                )
            )

        if (
            "class_ph" in result.columns
            and "class_name" not in result.columns
        ):
            class_names = {
                0: "unclassified",
                40: "bathymetry",
                41: "sea_surface",
            }

            numeric_class = pd.to_numeric(
                result["class_ph"],
                errors="coerce",
            )

            result["class_name"] = numeric_class.map(
                class_names
            ).fillna("unknown")

        result = self._replace_non_finite_values(
            result
        )
        result = self._serialize_complex_columns(
            result
        )

        preferred_columns = [
            "time_ns",
            "latitude",
            "longitude",
            "ellipse_h",
            "ortho_h",
            "surface_h",
            "depth",
            "class_ph",
            "class_name",
            "confidence",
            "low_confidence_flag",
            "sensor_depth_exceeded",
            "night_flag",
            "invalid_kd",
            "invalid_wind_speed",
            "sigma_thu",
            "sigma_tvu",
            "x_atc",
            "y_atc",
            "index_ph",
            "srcid",
            "spot",
            "cycle",
            "region",
            "rgt",
            "gt",
        ]

        ordered = [
            column
            for column in preferred_columns
            if column in result.columns
        ]

        ordered.extend(
            column
            for column in result.columns
            if column not in ordered
            and column != "geometry"
        )

        ordered.append("geometry")

        return result[ordered].copy()

    @staticmethod
    def _replace_non_finite_values(
        result: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        result = result.copy()

        for column in result.columns:
            if column == "geometry":
                continue

            if pd.api.types.is_numeric_dtype(
                result[column]
            ):
                result[column] = result[column].replace(
                    [np.inf, -np.inf],
                    np.nan,
                )

        return result

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

            complex_found = False

            for value in series.head(25):
                if isinstance(
                    value,
                    (
                        dict,
                        list,
                        tuple,
                        set,
                        np.ndarray,
                    ),
                ):
                    complex_found = True
                    break

            if complex_found:
                result[column] = series.apply(
                    cls._serialize_value
                )

        return result

    @staticmethod
    def _serialize_value(value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, np.ndarray):
            value = value.tolist()
        elif isinstance(value, set):
            value = list(value)
        elif isinstance(value, tuple):
            value = list(value)

        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                default=str,
            )
        except TypeError:
            return str(value)

    @staticmethod
    def _calculate_null_counts(
        result: gpd.GeoDataFrame,
    ) -> dict[str, int]:
        fields_to_check = [
            "index_ph",
            "depth",
            "ellipse_h",
            "ortho_h",
            "surface_h",
            "confidence",
            "sigma_thu",
            "sigma_tvu",
        ]

        return {
            field_name: int(
                result[field_name].isna().sum()
            )
            for field_name in fields_to_check
            if field_name in result.columns
        }

    def _write_geopackage(
        self,
        result: gpd.GeoDataFrame,
    ) -> None:
        output_file = Path(
            self.output_path
        ).expanduser().resolve()

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if output_file.exists():
            output_file.unlink()

        result.to_file(
            output_file,
            layer=self.layer_name,
            driver="GPKG",
            index=False,
        )
