from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, ClassVar



class HDF5ConverterCore:
    """Convert the primary ICESat-2 record table in one HDF5 granule."""

    BEAM_PATTERN = re.compile(r"^gt[123][lr]$", re.IGNORECASE)
    PRODUCT_PATTERN = re.compile(r"ATL(?:03|08|13|24)", re.IGNORECASE)

    PRODUCT_CONFIG: ClassVar[dict[str, dict[str, Any]]] = {
        "ATL03": {
            "group": "heights",
            "coordinates": [("lat_ph", "lon_ph")],
        },
        "ATL08": {
            "group": "land_segments",
            "coordinates": [("latitude", "longitude")],
        },
        "ATL13": {
            "group": "",
            "coordinates": [
                ("sseg_mean_lat", "sseg_mean_lon"),
                ("segment_lat", "segment_lon"),
                ("latitude", "longitude"),
            ],
        },
        "ATL24": {
            "group": "",
            "coordinates": [
                ("lat_ph", "lon_ph"),
                ("latitude", "longitude"),
            ],
        },
    }

    BASE_COLUMNS: ClassVar[list[str]] = [
        "source_file",
        "product",
        "beam",
        "source_group",
        "record_index",
        "latitude",
        "longitude",
    ]

    GRANULE_CONTEXT_PATHS: ClassVar[dict[str, tuple[str, ...]]] = {
        "atlas_sdp_gps_epoch": (
            "ancillary_data/atlas_sdp_gps_epoch",
        ),
        "granule_start_utc": (
            "ancillary_data/granule_start_utc",
            "ancillary_data/data_start_utc",
        ),
        "granule_end_utc": (
            "ancillary_data/granule_end_utc",
            "ancillary_data/data_end_utc",
        ),
        "release": ("ancillary_data/release", "release"),
        "version": ("ancillary_data/version", "version"),
        "rgt": ("orbit_info/rgt", "ancillary_data/start_rgt"),
        "cycle": ("orbit_info/cycle_number", "ancillary_data/start_cycle"),
        "orbit_number": (
            "orbit_info/orbit_number",
            "ancillary_data/start_orbit",
        ),
        "sc_orient": ("orbit_info/sc_orient",),
        "crossing_time": ("orbit_info/crossing_time",),
        "source_resource": ("resource",),
        "sliderule_version": ("sliderule_version",),
    }

    BEAM_ATTRIBUTE_COLUMNS: ClassVar[dict[str, str]] = {
        "atlas_beam_type": "beam_type",
        "atlas_spot_number": "spot_number",
        "groundtrack_id": "groundtrack_id",
        "atmosphere_profile": "atmosphere_profile",
    }

    STANDARD_COLUMNS: ClassVar[dict[str, tuple[str, ...]]] = {
        "ATL03": ("height", "x_atc", "y_atc", "ph_index", "gps_seconds"),
        "ATL08": (
            "h_te_median",
            "h_te_uncertainty",
            "h_canopy",
            "h_canopy_uncertainty",
            "gps_seconds",
        ),
        "ATL13": ("gps_seconds",),
        "ATL24": ("depth", "gps_seconds"),
    }

    CHUNK_SIZE = 50_000
    MAX_FLATTENED_WIDTH = 32

    def __init__(
        self,
        input_path: str,
        output_path: str,
        output_format: str,
    ):
        self.input_path = str(input_path)
        self.output_path = str(output_path)
        self.output_format = str(output_format).lower()

        self.product = ""
        self.layer_name = ""
        self.row_count = 0
        self.beam_count = 0
        self.skipped_datasets: list[str] = []

        self.error_message = ""
        self.error_traceback = ""

        self._temporary_output: Path | None = None

    @staticmethod
    def isCanceled() -> bool:
        # Cancellation is handled by terminating the isolated worker process.
        return False

    @staticmethod
    def setProgress(value: float) -> None:
        print(f"__ICESAT2_PROGRESS__={float(value):.6f}", flush=True)

    @staticmethod
    def _text_value(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")

        if hasattr(value, "tolist"):
            converted = value.tolist()
            if isinstance(converted, list) and converted:
                return HDF5ConverterCore._text_value(converted[0])
            return HDF5ConverterCore._text_value(converted)

        return str(value)

    def _detect_product(self, handle) -> str:
        filename_match = self.PRODUCT_PATTERN.search(
            Path(self.input_path).name
        )
        if filename_match:
            return filename_match.group(0).upper()

        for attribute_name in (
            "short_name",
            "identifier_product_type",
            "title",
        ):
            if attribute_name not in handle.attrs:
                continue

            attribute_match = self.PRODUCT_PATTERN.search(
                self._text_value(handle.attrs[attribute_name])
            )
            if attribute_match:
                return attribute_match.group(0).upper()

        raise RuntimeError(
            "The file is HDF5, but its ICESat-2 product could not be "
            "identified. Supported products are ATL03, ATL08, ATL13 and "
            "ATL24."
        )

    @staticmethod
    def _is_dataset(value: Any) -> bool:
        return hasattr(value, "shape") and hasattr(value, "dtype")

    def _scalar_dataset_value(self, handle, path: str) -> Any | None:
        if path not in handle:
            return None

        value = handle[path]
        if not self._is_dataset(value):
            return None

        shape = tuple(int(item) for item in value.shape)
        if shape not in {(), (1,)}:
            return None

        raw = value[()] if shape == () else value[0]
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        if hasattr(raw, "item"):
            raw = raw.item()
        return raw

    def _granule_context(self, handle) -> dict[str, Any]:
        context: dict[str, Any] = {}

        for column_name, paths in self.GRANULE_CONTEXT_PATHS.items():
            for path in paths:
                value = self._scalar_dataset_value(handle, path)
                if value is not None:
                    context[column_name] = value
                    break

            if column_name in context:
                continue

            for path in paths:
                attribute_name = path.rsplit("/", 1)[-1]
                if attribute_name in handle.attrs:
                    context[column_name] = self._text_value(
                        handle.attrs[attribute_name]
                    )
                    break

        return context

    def _beam_context(self, beam_group) -> dict[str, Any]:
        context: dict[str, Any] = {}

        for attribute_name, column_name in self.BEAM_ATTRIBUTE_COLUMNS.items():
            if attribute_name not in beam_group.attrs:
                continue

            value = beam_group.attrs[attribute_name]
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            elif hasattr(value, "item"):
                value = value.item()
            context[column_name] = value

        return context

    def _coordinate_pair(self, group, product: str):
        config = self.PRODUCT_CONFIG[product]

        for latitude_name, longitude_name in config["coordinates"]:
            if (
                latitude_name in group
                and longitude_name in group
                and self._is_dataset(group[latitude_name])
                and self._is_dataset(group[longitude_name])
            ):
                return (
                    latitude_name,
                    longitude_name,
                    group[latitude_name],
                    group[longitude_name],
                )

        return None

    def _record_groups(self, handle, product: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        granule_context = self._granule_context(handle)
        configured_group = str(
            self.PRODUCT_CONFIG[product]["group"]
        )

        for beam_name in sorted(handle.keys()):
            if not self.BEAM_PATTERN.fullmatch(str(beam_name)):
                continue

            beam_group = handle[beam_name]
            group = beam_group

            if configured_group:
                if configured_group not in beam_group:
                    continue
                group = beam_group[configured_group]

            coordinates = self._coordinate_pair(group, product)
            if coordinates is None:
                continue

            latitude_name, longitude_name, latitude, longitude = coordinates
            if (
                len(latitude.shape) != 1
                or len(longitude.shape) != 1
                or latitude.shape[0] != longitude.shape[0]
            ):
                continue

            row_count = int(latitude.shape[0])
            if row_count <= 0:
                continue

            records.append(
                {
                    "beam": str(beam_name),
                    "beam_group": beam_group,
                    "group": group,
                    "group_path": str(group.name),
                    "latitude_name": latitude_name,
                    "longitude_name": longitude_name,
                    "latitude": latitude,
                    "longitude": longitude,
                    "row_count": row_count,
                    "context": {
                        **granule_context,
                        **self._beam_context(beam_group),
                    },
                }
            )

        if records:
            return records

        raise RuntimeError(
            f"No supported {product} per-photon or per-segment record "
            "groups were found in this granule."
        )

    @staticmethod
    def _safe_column_name(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", name.replace("/", "__"))
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned or "value"

    def _dataset_specs(
        self,
        group,
        row_count: int,
        used_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        if used_names is None:
            used_names = set(self.BASE_COLUMNS)

        def visitor(relative_name: str, value: Any) -> None:
            if not self._is_dataset(value):
                return

            shape = tuple(int(item) for item in value.shape)
            if not shape:
                return

            if len(shape) == 1 and shape[0] == row_count:
                width = 1
                record_axis = 0
            elif (
                len(shape) == 2
                and shape[0] == row_count
                and shape[1] <= self.MAX_FLATTENED_WIDTH
            ):
                width = int(shape[1])
                record_axis = 0
            elif (
                len(shape) == 2
                and shape[1] == row_count
                and shape[0] <= self.MAX_FLATTENED_WIDTH
            ):
                width = int(shape[0])
                record_axis = 1
            else:
                if row_count in shape:
                    self.skipped_datasets.append(str(value.name))
                return

            base_name = self._safe_column_name(relative_name)

            if base_name == "signal_conf_ph" and width == 5:
                column_names = [
                    "signal_conf_ph_land",
                    "signal_conf_ph_ocean",
                    "signal_conf_ph_sea_ice",
                    "signal_conf_ph_land_ice",
                    "signal_conf_ph_inland_water",
                ]
            elif width == 1:
                column_names = [base_name]
            else:
                column_names = [
                    f"{base_name}_{index}"
                    for index in range(width)
                ]

            final_names: list[str] = []
            for column_name in column_names:
                candidate = column_name
                suffix = 2
                while candidate in used_names:
                    candidate = f"{column_name}_{suffix}"
                    suffix += 1
                used_names.add(candidate)
                final_names.append(candidate)

            specs.append(
                {
                    "dataset": value,
                    "columns": final_names,
                    "width": width,
                    "record_axis": record_axis,
                    "relative_name": relative_name,
                    "fill_value": self._fill_value(value),
                }
            )

        group.visititems(visitor)
        return specs

    def _atl03_auxiliary_specs(
        self,
        beam_group,
        used_names: set[str],
    ) -> dict[str, Any] | None:
        import numpy as np

        if "geolocation" not in beam_group:
            return None

        geolocation = beam_group["geolocation"]
        if (
            "ph_index_beg" not in geolocation
            or "segment_ph_cnt" not in geolocation
        ):
            return None

        starts = np.asarray(geolocation["ph_index_beg"][:], dtype="int64") - 1
        counts = np.asarray(geolocation["segment_ph_cnt"][:], dtype="int64")
        if starts.ndim != 1 or counts.ndim != 1 or starts.size != counts.size:
            return None

        valid = (starts >= 0) & (counts > 0)
        if not np.any(valid):
            return None

        source_indices = np.flatnonzero(valid).astype("int64")
        starts = starts[valid]
        counts = counts[valid]
        order = np.argsort(starts, kind="stable")
        starts = starts[order]
        counts = counts[order]
        source_indices = source_indices[order]
        segment_count = int(geolocation["ph_index_beg"].shape[0])

        specs: list[dict[str, Any]] = []

        def collect(group, prefix: str) -> None:
            def visitor(relative_name: str, value: Any) -> None:
                if not self._is_dataset(value):
                    return

                shape = tuple(int(item) for item in value.shape)
                if len(shape) == 1 and shape[0] == segment_count:
                    width = 1
                    record_axis = 0
                elif (
                    len(shape) == 2
                    and shape[0] == segment_count
                    and shape[1] <= self.MAX_FLATTENED_WIDTH
                ):
                    width = int(shape[1])
                    record_axis = 0
                elif (
                    len(shape) == 2
                    and shape[1] == segment_count
                    and shape[0] <= self.MAX_FLATTENED_WIDTH
                ):
                    width = int(shape[0])
                    record_axis = 1
                else:
                    if segment_count in shape:
                        self.skipped_datasets.append(str(value.name))
                    return

                leaf_name = self._safe_column_name(
                    relative_name.rsplit("/", 1)[-1]
                )
                relative_column = self._safe_column_name(relative_name)
                base_name = leaf_name
                if base_name in used_names:
                    base_name = f"{prefix}_{relative_column}"

                column_names = (
                    [base_name]
                    if width == 1
                    else [f"{base_name}_{index}" for index in range(width)]
                )

                final_names: list[str] = []
                for column_name in column_names:
                    candidate = column_name
                    suffix = 2
                    while candidate in used_names:
                        candidate = f"{column_name}_{suffix}"
                        suffix += 1
                    used_names.add(candidate)
                    final_names.append(candidate)

                specs.append(
                    {
                        "dataset": value,
                        "columns": final_names,
                        "width": width,
                        "record_axis": record_axis,
                        "fill_value": self._fill_value(value),
                    }
                )

            group.visititems(visitor)

        collect(geolocation, "geolocation")
        if "geophys_corr" in beam_group:
            collect(beam_group["geophys_corr"], "geophys_corr")

        return {
            "starts": starts,
            "counts": counts,
            "source_indices": source_indices,
            "specs": specs,
        }

    @staticmethod
    def _dataset_chunk(spec: dict[str, Any], start: int, stop: int):
        dataset = spec["dataset"]
        if spec["record_axis"] == 0:
            return dataset[start:stop]
        return dataset[:, start:stop].T

    def _mapped_series(
        self,
        values,
        valid_positions,
        length: int,
        fill_value,
        pd,
    ):
        import numpy as np

        converted = self._series(values, fill_value, pd).reset_index(drop=True)
        if (
            len(valid_positions) == length
            and np.array_equal(valid_positions, np.arange(length))
        ):
            return converted

        array = np.asarray(values)
        if array.dtype.kind in "iufb":
            result = pd.Series(np.full(length, np.nan, dtype="float64"))
        else:
            result = pd.Series([None] * length, dtype=object)

        result.iloc[valid_positions] = converted.to_numpy()
        return result

    def _append_atl03_auxiliary(
        self,
        frame,
        auxiliary: dict[str, Any] | None,
        start: int,
        stop: int,
        pd,
    ) -> None:
        import numpy as np

        if not auxiliary:
            return

        photon_indices = np.arange(start, stop, dtype="int64")
        positions = np.searchsorted(
            auxiliary["starts"],
            photon_indices,
            side="right",
        ) - 1
        valid = positions >= 0
        bounded_positions = np.maximum(positions, 0)
        valid &= photon_indices < (
            auxiliary["starts"][bounded_positions]
            + auxiliary["counts"][bounded_positions]
        )

        valid_positions = np.flatnonzero(valid)
        if valid_positions.size == 0:
            return

        source_indices = auxiliary["source_indices"][positions[valid]]
        unique_indices, inverse = np.unique(
            source_indices,
            return_inverse=True,
        )

        for spec in auxiliary["specs"]:
            if spec["record_axis"] == 0:
                selected = spec["dataset"][unique_indices]
            else:
                selected = spec["dataset"][:, unique_indices].T
            selected = selected[inverse]

            if spec["width"] == 1:
                frame[spec["columns"][0]] = self._mapped_series(
                    selected,
                    valid_positions,
                    stop - start,
                    spec["fill_value"],
                    pd,
                )
                continue

            for index, column_name in enumerate(spec["columns"]):
                frame[column_name] = self._mapped_series(
                    selected[:, index],
                    valid_positions,
                    stop - start,
                    spec["fill_value"],
                    pd,
                )

    def _add_standard_columns(self, frame) -> None:
        if (
            "delta_time" in frame
            and "atlas_sdp_gps_epoch" in frame
            and "gps_seconds" not in frame
        ):
            frame["gps_seconds"] = (
                frame["atlas_sdp_gps_epoch"] + frame["delta_time"]
            )

        if self.product == "ATL03":
            if "h_ph" in frame and "height" not in frame:
                frame["height"] = frame["h_ph"]
            if "dist_ph_across" in frame and "y_atc" not in frame:
                frame["y_atc"] = frame["dist_ph_across"]
            if (
                "segment_dist_x" in frame
                and "dist_ph_along" in frame
                and "x_atc" not in frame
            ):
                frame["x_atc"] = (
                    frame["segment_dist_x"] + frame["dist_ph_along"]
                )
            if "ph_index" not in frame:
                frame["ph_index"] = frame["record_index"]

        elif self.product == "ATL08":
            aliases = {
                "terrain_h_te_median": "h_te_median",
                "terrain_h_te_uncertainty": "h_te_uncertainty",
                "canopy_h_canopy": "h_canopy",
                "canopy_h_canopy_uncertainty": "h_canopy_uncertainty",
            }
            for source_name, target_name in aliases.items():
                if source_name in frame and target_name not in frame:
                    frame[target_name] = frame[source_name]

        elif self.product == "ATL24":
            if (
                "depth" not in frame
                and "surface_h" in frame
                and "ortho_h" in frame
            ):
                frame["depth"] = frame["surface_h"] - frame["ortho_h"]

    @staticmethod
    def _fill_value(dataset) -> Any:
        if "_FillValue" in dataset.attrs:
            return dataset.attrs["_FillValue"]

        if "fill_value" in dataset.attrs:
            return dataset.attrs["fill_value"]

        # h5py reports a datatype default (often zero) through
        # dataset.fillvalue even when the source did not define a science
        # fill value. Only explicit HDF5 attributes are safe to mask here.
        return None

    @staticmethod
    def _series(values, fill_value, pd):
        import numpy as np

        array = np.asarray(values)

        if array.dtype.kind == "S":
            array = np.char.decode(
                array,
                "utf-8",
                errors="replace",
            )
        elif array.dtype.kind == "O":
            array = np.asarray(
                [
                    item.decode("utf-8", errors="replace")
                    if isinstance(item, bytes)
                    else item
                    for item in array
                ],
                dtype=object,
            )

        result = pd.Series(array)

        if fill_value is not None:
            try:
                fill_scalar = (
                    fill_value.item()
                    if hasattr(fill_value, "item")
                    else fill_value
                )
                result = result.mask(result == fill_scalar)
            except (TypeError, ValueError):
                pass

        if array.dtype.kind == "f":
            result = result.mask(~np.isfinite(array))

        return result

    def _chunk_frame(
        self,
        record: dict[str, Any],
        specs: list[dict[str, Any]],
        auxiliary: dict[str, Any] | None,
        start: int,
        stop: int,
        pd,
    ):
        import numpy as np

        length = stop - start
        latitude = self._series(
            record["latitude"][start:stop],
            self._fill_value(record["latitude"]),
            pd,
        )
        longitude = self._series(
            record["longitude"][start:stop],
            self._fill_value(record["longitude"]),
            pd,
        )

        frame = pd.DataFrame(
            {
                "source_file": np.repeat(
                    Path(self.input_path).name,
                    length,
                ),
                "product": np.repeat(self.product, length),
                "beam": np.repeat(record["beam"], length),
                "source_group": np.repeat(record["group_path"], length),
                "record_index": np.arange(start, stop, dtype="int64"),
                "latitude": latitude,
                "longitude": longitude,
            }
        )

        for column_name, value in record["context"].items():
            frame[column_name] = np.repeat(value, length)

        for spec in specs:
            values = self._dataset_chunk(spec, start, stop)

            if spec["width"] == 1:
                frame[spec["columns"][0]] = self._series(
                    values,
                    spec["fill_value"],
                    pd,
                )
                continue

            for index, column_name in enumerate(spec["columns"]):
                frame[column_name] = self._series(
                    values[:, index],
                    spec["fill_value"],
                    pd,
                )

        self._append_atl03_auxiliary(
            frame,
            auxiliary,
            start,
            stop,
            pd,
        )
        self._add_standard_columns(frame)
        return frame

    def _temporary_path(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.NamedTemporaryFile(  # noqa: SIM115
            prefix=f".{output_path.stem}_",
            suffix=output_path.suffix,
            dir=str(output_path.parent),
            delete=False,
        )
        temporary.close()

        path = Path(temporary.name)
        path.unlink(missing_ok=True)
        return path

    def _commit_output(self, temporary_path: Path, output_path: Path) -> None:
        if output_path.exists():
            output_path.unlink()
        temporary_path.replace(output_path)

    def run(self) -> bool:
        try:
            if self.output_format != "csv":
                raise RuntimeError("The isolated HDF5 worker writes CSV only.")

            input_path = Path(self.input_path)
            output_path = Path(self.output_path)

            if not input_path.exists() or not input_path.is_file():
                raise RuntimeError("Select an existing ICESat-2 HDF5 file.")

            if input_path.resolve() == output_path.resolve():
                raise RuntimeError("The output cannot overwrite the source HDF5 file.")

            try:
                import h5py
            except ModuleNotFoundError as error:
                raise RuntimeError(
                    "HDF5 support is not installed in the isolated worker."
                ) from error

            import pandas as pd

            temporary_path = self._temporary_path(output_path)
            self._temporary_output = temporary_path

            with h5py.File(input_path, "r") as handle:
                self.product = self._detect_product(handle)
                self.layer_name = f"{self.product.lower()}_records"
                records = self._record_groups(handle, self.product)
                self.beam_count = len(records)

                all_columns = list(self.BASE_COLUMNS)
                for record in records:
                    for column_name in record["context"]:
                        if column_name not in all_columns:
                            all_columns.append(column_name)

                    used_names = set(self.BASE_COLUMNS)
                    used_names.update(record["context"])
                    specs = self._dataset_specs(
                        record["group"],
                        int(record["row_count"]),
                        used_names,
                    )
                    auxiliary = None
                    if self.product == "ATL03":
                        auxiliary = self._atl03_auxiliary_specs(
                            record["beam_group"],
                            used_names,
                        )

                    record["specs"] = specs
                    record["auxiliary"] = auxiliary

                    for spec in specs:
                        for column_name in spec["columns"]:
                            if column_name not in all_columns:
                                all_columns.append(column_name)

                    if auxiliary:
                        for spec in auxiliary["specs"]:
                            for column_name in spec["columns"]:
                                if column_name not in all_columns:
                                    all_columns.append(column_name)

                for column_name in self.STANDARD_COLUMNS[self.product]:
                    if column_name not in all_columns:
                        all_columns.append(column_name)

                total_rows = sum(
                    int(record["row_count"])
                    for record in records
                )
                processed_rows = 0
                wrote_output = False

                for record in records:
                    for start in range(
                        0,
                        int(record["row_count"]),
                        self.CHUNK_SIZE,
                    ):
                        if self.isCanceled():
                            return False

                        stop = min(
                            start + self.CHUNK_SIZE,
                            int(record["row_count"]),
                        )
                        frame = self._chunk_frame(
                            record,
                            record["specs"],
                            record["auxiliary"],
                            start,
                            stop,
                            pd,
                        )
                        frame = frame.reindex(columns=all_columns)

                        frame.to_csv(
                            temporary_path,
                            mode="a" if wrote_output else "w",
                            header=not wrote_output,
                            index=False,
                            na_rep="",
                        )

                        wrote_output = True
                        processed_rows += len(frame)
                        self.row_count = processed_rows
                        self.setProgress(
                            100.0 * processed_rows / max(total_rows, 1)
                        )

                if not wrote_output:
                    raise RuntimeError(
                        "No convertible per-photon or per-segment records "
                        "were found."
                    )

            if self.isCanceled():
                return False

            self._commit_output(temporary_path, output_path)
            self._temporary_output = None
            self.setProgress(100)
            return True

        except Exception as error:  # noqa: BLE001
            self.error_message = f"{type(error).__name__}: {error}"
            self.error_traceback = traceback.format_exc()
            return False

        finally:
            if self._temporary_output is not None:
                self._temporary_output.unlink(missing_ok=True)
                self._temporary_output = None


def _main() -> int:
    parser = argparse.ArgumentParser(description="Isolated ICESat-2 HDF5 conversion worker")
    parser.add_argument("--site-packages", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()

    managed_path = str(Path(args.site_packages).resolve())
    if managed_path not in sys.path:
        sys.path.insert(0, managed_path)

    converter = HDF5ConverterCore(
        input_path=args.input,
        output_path=args.output_csv,
        output_format="csv",
    )
    if not converter.run():
        payload = {
            "message": converter.error_message or "HDF5 conversion failed.",
            "traceback": converter.error_traceback,
        }
        print("__ICESAT2_ERROR__=" + json.dumps(payload, ensure_ascii=False), flush=True)
        return 1

    payload = {
        "product": converter.product,
        "layer_name": converter.layer_name,
        "row_count": converter.row_count,
        "beam_count": converter.beam_count,
        "skipped_datasets": converter.skipped_datasets,
    }
    print("__ICESAT2_RESULT__=" + json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
