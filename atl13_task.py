from __future__ import annotations

import json
import sqlite3
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import sliderule

from qgis.core import QgsTask


class ATL13DownloadTask(QgsTask):
    """
    Background task that requests ATL13 inland-water segments from SlideRule,
    validates the returned fields, writes a GeoPackage and creates a
    query_metadata attribute table.
    """

    SUMMARY_FIELDS = (
        "ht_ortho",
        "ht_water_surf",
        "stdev_water_surf",
        "water_depth",
    )

    def __init__(
        self,
        parameters: dict[str, Any],
        output_path: str,
        layer_name: str,
        query_metadata: dict[str, Any] | None = None,
    ):
        super().__init__(
            "Download ATL13 inland-water segments",
            QgsTask.CanCancel,
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

        self.output_crs = "EPSG:4326"

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

            result = sliderule.run(
                "atl13x",
                self.parameters,
            )

            self.setProgress(60)

            if self.isCanceled():
                return False

            if result is None:
                self.result_count = 0
                return True

            if not isinstance(result, gpd.GeoDataFrame):
                result = gpd.GeoDataFrame(result)

            if result.empty:
                self.result_count = 0
                return True

            result = self._prepare_output(result)

            self.result_count = len(result)
            self.returned_columns = [
                str(column)
                for column in result.columns
            ]
            self.null_counts = self._calculate_null_counts(result)
            self.numeric_fields = self._get_numeric_fields(result)
            self.summary_statistics = self._calculate_summary_statistics(result)

            self.setProgress(75)

            if self.isCanceled():
                return False

            self._write_geopackage(result)

            self.setProgress(90)

            if self.isCanceled():
                return False

            self._write_query_metadata()

            self.setProgress(100)
            return True

        except Exception as error:
            self.error_message = f"{type(error).__name__}: {error}"
            self.error_traceback = traceback.format_exc()
            return False

    def _prepare_output(
        self,
        result: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        result = result.copy()

        if result.index.name is not None:
            result = result.reset_index()

        if "geometry" not in result.columns:
            raise ValueError(
                "SlideRule returned ATL13 data without geometry."
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

        result = self._replace_non_finite_values(result)
        result = self._serialize_complex_columns(result)

        preferred_columns = [
            "time",
            "time_ns",
            "latitude",
            "longitude",
            "ht_ortho",
            "ht_water_surf",
            "stdev_water_surf",
            "water_depth",
            "spot",
            "cycle",
            "region",
            "rgt",
            "gt",
            "refid",
            "name",
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

    @staticmethod
    def _replace_non_finite_values(
        result: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        result = result.copy()

        for column in result.columns:
            if column == "geometry":
                continue

            series = result[column]

            if pd.api.types.is_numeric_dtype(series):
                result[column] = series.replace(
                    [np.inf, -np.inf],
                    np.nan,
                )

        return result

    @staticmethod
    def _is_complex_value(value: Any) -> bool:
        return isinstance(
            value,
            (
                list,
                tuple,
                dict,
                set,
                np.ndarray,
            ),
        )

    @staticmethod
    def _is_missing_scalar(value: Any) -> bool:
        if isinstance(
            value,
            (
                list,
                tuple,
                dict,
                set,
                np.ndarray,
            ),
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
        return {
            field_name: int(result[field_name].isna().sum())
            for field_name in cls.SUMMARY_FIELDS
            if field_name in result.columns
        }

    @staticmethod
    def _get_numeric_fields(
        result: gpd.GeoDataFrame,
    ) -> list[str]:
        numeric_fields = []

        for column in result.columns:
            if column == "geometry":
                continue

            if pd.api.types.is_numeric_dtype(result[column]):
                numeric_fields.append(str(column))

        return numeric_fields

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

    def _write_geopackage(
        self,
        result: gpd.GeoDataFrame,
    ) -> None:
        output_file = Path(self.output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if output_file.exists():
            output_file.unlink()

        result.to_file(
            output_file,
            layer=self.layer_name,
            driver="GPKG",
            index=False,
        )

    def _write_query_metadata(self) -> None:
        output_file = Path(self.output_path)
        metadata = dict(self.query_metadata)

        metadata.update(
            {
                "request_date_utc": datetime.now(timezone.utc).isoformat(),
                "sliderule_endpoint": "atl13x",
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
                "request_parameters": self.parameters,
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
                    'ICESat-2 Data Explorer ATL13 query metadata',
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
            (
                dict,
                list,
                tuple,
                set,
                np.ndarray,
            ),
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
