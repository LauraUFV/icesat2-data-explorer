from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import traceback

from pathlib import Path


MODEL_DOWNLOAD_NAME = "GOT4.10"
MODEL_ID = "GOT4.10_nc"


def emit(kind: str, payload: dict) -> None:
    print(
        kind + " " + json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def import_engine():
    import numpy as np
    import dask
    import dask.array
    import h5py
    import h5netcdf
    import pyTMD
    import pyTMD.compute
    import pyTMD.datasets
    import pyTMD.io

    return (
        pyTMD,
        np,
        h5py,
        h5netcdf,
        dask,
    )


def verify_model(
    pyTMD,
    model_directory: Path,
) -> None:
    """
    Verify GOT4.10c without validating the same paths twice.

    from_database(..., verify=True) already resolves every constituent path
    and raises FileNotFoundError when a required file is absent. Calling
    validate_model() afterwards makes pyTMD 3.0.9 pass already-resolved Path
    objects back to Path.glob(), which fails on Python 3.12 for Windows.
    """
    model = pyTMD.io.model(
        directory=model_directory,
        verify=True,
    ).from_database(
        MODEL_ID,
        group="z",
    )

    model_files = list(
        getattr(
            model.z,
            "model_file",
            [],
        )
    )

    if not model_files:
        raise FileNotFoundError(
            "GOT4.10c constituent files were not found."
        )

    missing = [
        str(path)
        for path in model_files
        if not Path(path).exists()
        or Path(path).stat().st_size <= 0
    ]

    if missing:
        raise FileNotFoundError(
            "GOT4.10c is incomplete. Missing or empty files:\n"
            + "\n".join(missing)
        )


def action_status(args) -> int:
    pyTMD, _, h5py, h5netcdf, dask = import_engine()

    model_directory = Path(
        args.models_dir
    ).expanduser().resolve()

    installed = False
    model_error = None

    try:
        verify_model(
            pyTMD,
            model_directory,
        )
        installed = True
    except Exception as error:
        model_error = (
            f"{type(error).__name__}: {error}"
        )

    emit(
        "RESULT",
        {
            "engine_installed": True,
            "pytmd_version": getattr(
                pyTMD,
                "__version__",
                "unknown",
            ),
            "h5py_version": getattr(
                h5py,
                "__version__",
                "unknown",
            ),
            "h5netcdf_version": getattr(
                h5netcdf,
                "__version__",
                "unknown",
            ),
            "dask_version": getattr(
                dask,
                "__version__",
                "unknown",
            ),
            "model_installed": installed,
            "model_id": MODEL_ID,
            "models_dir": str(model_directory),
            "model_error": model_error,
        },
    )

    return 0


def action_download(args) -> int:
    pyTMD, _, h5py, h5netcdf, dask = import_engine()

    model_directory = Path(
        args.models_dir
    ).expanduser().resolve()

    model_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    emit(
        "PROGRESS",
        {
            "value": 5,
            "message": "Downloading GOT4.10c from NASA GSFC",
        },
    )

    pyTMD.datasets.fetch_gsfc_got(
        model=MODEL_DOWNLOAD_NAME,
        directory=model_directory,
        format="netcdf",
        compressed=False,
        timeout=600,
    )

    emit(
        "PROGRESS",
        {
            "value": 90,
            "message": "Verifying model files",
        },
    )

    verify_model(
        pyTMD,
        model_directory,
    )

    emit(
        "RESULT",
        {
            "model_installed": True,
            "model_id": MODEL_ID,
            "model_distribution": "GOT4.10c",
            "models_dir": str(model_directory),
            "pytmd_version": getattr(
                pyTMD,
                "__version__",
                "unknown",
            ),
            "h5py_version": getattr(
                h5py,
                "__version__",
                "unknown",
            ),
            "h5netcdf_version": getattr(
                h5netcdf,
                "__version__",
                "unknown",
            ),
            "dask_version": getattr(
                dask,
                "__version__",
                "unknown",
            ),
        },
    )

    return 0


def read_chunk(reader, chunk_size: int):
    rows = []

    for row in reader:
        rows.append(row)

        if len(rows) >= chunk_size:
            yield rows
            rows = []

    if rows:
        yield rows


def values_from_result(
    np,
    result,
):
    if hasattr(result, "to_numpy"):
        values = result.to_numpy()
    elif hasattr(result, "values"):
        values = result.values
    else:
        values = np.asarray(result)

    if np.ma.isMaskedArray(values):
        values = values.filled(np.nan)

    return np.asarray(
        values,
        dtype=float,
    ).reshape(-1)


def action_compute(args) -> int:
    pyTMD, np, h5py, h5netcdf, dask = import_engine()

    model_directory = Path(
        args.models_dir
    ).expanduser().resolve()

    verify_model(
        pyTMD,
        model_directory,
    )

    input_csv = Path(
        args.input_csv
    ).expanduser().resolve()

    output_csv = Path(
        args.output_csv
    ).expanduser().resolve()

    output_csv.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    total = int(args.total)
    processed = 0
    valid = 0
    invalid = 0
    all_valid_values = []

    first_time = None
    last_time = None

    with input_csv.open(
        mode="r",
        encoding="utf-8",
        newline="",
    ) as source, output_csv.open(
        mode="w",
        encoding="utf-8",
        newline="",
    ) as target:
        reader = csv.DictReader(source)

        writer = csv.DictWriter(
            target,
            fieldnames=[
                "fid",
                "tide_ocean_model_m",
                "tide_time_utc",
                "tide_valid",
            ],
        )
        writer.writeheader()

        for chunk in read_chunk(
            reader,
            int(args.chunk_size),
        ):
            fids = []
            longitudes = []
            latitudes = []
            times = []
            time_strings = []
            valid_positions = []

            output_rows = [
                {
                    "fid": row["fid"],
                    "tide_ocean_model_m": "",
                    "tide_time_utc": row.get(
                        "time_utc",
                        "",
                    ),
                    "tide_valid": 0,
                }
                for row in chunk
            ]

            for position, row in enumerate(chunk):
                try:
                    longitude = float(
                        row["longitude"]
                    )
                    latitude = float(
                        row["latitude"]
                    )
                    time_string = str(
                        row["time_utc"]
                    ).strip()

                    if (
                        not math.isfinite(longitude)
                        or not math.isfinite(latitude)
                        or not time_string
                    ):
                        raise ValueError(
                            "Invalid coordinate or time"
                        )

                    normalized = time_string.replace(
                        "Z",
                        "",
                    ).replace(
                        "+00:00",
                        "",
                    )

                    time_value = np.datetime64(
                        normalized,
                        "ns",
                    )

                    fids.append(row["fid"])
                    longitudes.append(longitude)
                    latitudes.append(latitude)
                    times.append(time_value)
                    time_strings.append(time_string)
                    valid_positions.append(position)

                    if first_time is None:
                        first_time = time_string
                    last_time = time_string

                except Exception:
                    invalid += 1

            if valid_positions:
                result = pyTMD.compute.tide_elevations(
                    np.asarray(
                        longitudes,
                        dtype=float,
                    ),
                    np.asarray(
                        latitudes,
                        dtype=float,
                    ),
                    np.asarray(
                        times,
                        dtype="datetime64[ns]",
                    ),
                    directory=model_directory,
                    model=MODEL_ID,
                    crs=4326,
                    standard="datetime",
                    type="trajectory",
                    method=args.method,
                    extrapolate=bool(
                        int(args.extrapolate)
                    ),
                    crop=True,
                    buffer=1.0,
                )

                tide_values = values_from_result(
                    np,
                    result,
                )

                if len(tide_values) != len(
                    valid_positions
                ):
                    raise RuntimeError(
                        "pyTMD returned a different number "
                        "of results than input observations."
                    )

                for local_index, position in enumerate(
                    valid_positions
                ):
                    value = float(
                        tide_values[local_index]
                    )

                    if math.isfinite(value):
                        output_rows[position][
                            "tide_ocean_model_m"
                        ] = repr(value)
                        output_rows[position][
                            "tide_valid"
                        ] = 1

                        valid += 1
                        all_valid_values.append(value)
                    else:
                        invalid += 1

            writer.writerows(output_rows)

            processed += len(chunk)

            progress = (
                100.0 * processed / total
                if total
                else 100.0
            )

            emit(
                "PROGRESS",
                {
                    "value": progress,
                    "processed": processed,
                    "total": total,
                },
            )

    if all_valid_values:
        array = np.asarray(
            all_valid_values,
            dtype=float,
        )

        minimum = float(np.min(array))
        maximum = float(np.max(array))
        mean = float(np.mean(array))
        median = float(np.median(array))
    else:
        minimum = None
        maximum = None
        mean = None
        median = None

    emit(
        "RESULT",
        {
            "total_records": total,
            "processed_records": processed,
            "valid_records": valid,
            "invalid_records": invalid,
            "minimum_tide_m": minimum,
            "maximum_tide_m": maximum,
            "mean_tide_m": mean,
            "median_tide_m": median,
            "first_time_utc": first_time,
            "last_time_utc": last_time,
            "model_id": MODEL_ID,
            "model_distribution": "GOT4.10c",
            "method": args.method,
            "extrapolate": bool(
                int(args.extrapolate)
            ),
            "pytmd_version": getattr(
                pyTMD,
                "__version__",
                "unknown",
            ),
            "h5py_version": getattr(
                h5py,
                "__version__",
                "unknown",
            ),
            "h5netcdf_version": getattr(
                h5netcdf,
                "__version__",
                "unknown",
            ),
            "dask_version": getattr(
                dask,
                "__version__",
                "unknown",
            ),
        },
    )

    return 0


def build_parser():
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(
        dest="action",
        required=True,
    )

    status = subparsers.add_parser(
        "status"
    )
    status.add_argument(
        "--models-dir",
        required=True,
    )
    status.set_defaults(
        function=action_status
    )

    download = subparsers.add_parser(
        "download-model"
    )
    download.add_argument(
        "--models-dir",
        required=True,
    )
    download.set_defaults(
        function=action_download
    )

    compute = subparsers.add_parser(
        "compute"
    )
    compute.add_argument(
        "--models-dir",
        required=True,
    )
    compute.add_argument(
        "--input-csv",
        required=True,
    )
    compute.add_argument(
        "--output-csv",
        required=True,
    )
    compute.add_argument(
        "--total",
        required=True,
        type=int,
    )
    compute.add_argument(
        "--chunk-size",
        default=50000,
        type=int,
    )
    compute.add_argument(
        "--method",
        choices=(
            "linear",
            "nearest",
        ),
        default="linear",
    )
    compute.add_argument(
        "--extrapolate",
        choices=(
            "0",
            "1",
        ),
        default="0",
    )
    compute.set_defaults(
        function=action_compute
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return int(
            args.function(args)
        )
    except Exception as error:
        emit(
            "ERROR",
            {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
