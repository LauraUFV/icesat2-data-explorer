from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import subprocess  # nosec B404
import struct
import sys
import tempfile
import traceback

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qgis.PyQt.QtCore import QStandardPaths
from qgis.core import QgsApplication, QgsTask

from .model_tide_report import export_model_tide_report


PYTMD_VERSION = "3.0.9"
H5PY_VERSION = "3.16.0"
H5NETCDF_VERSION = "1.8.1"
DASK_VERSION = "2026.7.1"
MODEL_ID = "GOT4.10_nc"
MODEL_DISTRIBUTION = "GOT4.10c"


def support_root() -> Path:
    local_data = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )

    if not local_data:
        local_data = os.environ.get(
            "LOCALAPPDATA",
            str(
                Path.home()
                / "AppData"
                / "Local"
            ),
        )

    return (
        Path(local_data)
        / "ICESat2DataExplorer"
        / "tide_support"
    ).resolve()


def venv_directory() -> Path:
    return support_root() / "venv"


def models_directory() -> Path:
    return support_root() / "models"


def logs_directory() -> Path:
    return support_root() / "logs"


def venv_python() -> Path:
    if os.name == "nt":
        return (
            venv_directory()
            / "Scripts"
            / "python.exe"
        )

    return (
        venv_directory()
        / "bin"
        / "python"
    )


def qgis_base_python() -> Path:
    """
    Return the actual Python interpreter bundled with QGIS.

    In an embedded QGIS session, sys.executable can point to qgis-bin.exe.
    Passing "-m venv" to qgis-bin.exe makes QGIS interpret command-line
    arguments as layer paths. This function explicitly locates python.exe.
    """
    candidates: list[Path] = []

    executable_name = (
        "python.exe"
        if os.name == "nt"
        else "python3"
    )

    for prefix in (
        getattr(sys, "prefix", None),
        getattr(sys, "base_prefix", None),
        os.environ.get("PYTHONHOME"),
    ):
        if not prefix:
            continue

        prefix_path = Path(
            str(prefix)
        ).expanduser()

        if os.name == "nt":
            candidates.extend(
                [
                    prefix_path / "python.exe",
                    prefix_path / "python3.exe",
                ]
            )
        else:
            candidates.extend(
                [
                    prefix_path / "bin" / "python3",
                    prefix_path / "bin" / "python",
                ]
            )

    try:
        qgis_prefix = Path(
            QgsApplication.prefixPath()
        )

        apps_directory = qgis_prefix.parent

        if os.name == "nt":
            for python_directory in sorted(
                apps_directory.glob(
                    "Python*"
                ),
                reverse=True,
            ):
                candidates.extend(
                    [
                        python_directory / "python.exe",
                        python_directory / "python3.exe",
                    ]
                )

            install_root = apps_directory.parent
            candidates.extend(
                [
                    install_root / "bin" / "python.exe",
                    install_root / "bin" / "python3.exe",
                ]
            )
        else:
            candidates.extend(
                [
                    apps_directory / "bin" / "python3",
                    apps_directory / "bin" / "python",
                ]
            )
    except Exception:  # nosec B110
        pass

    # sys.executable is only accepted when it really is a Python binary.
    current_executable = Path(
        sys.executable
    )

    if (
        current_executable.name.lower()
        in {
            "python.exe",
            "python3.exe",
            "python",
            "python3",
        }
    ):
        candidates.append(
            current_executable
        )

    checked: list[str] = []

    for candidate in candidates:
        try:
            resolved = candidate.expanduser()
            checked.append(str(resolved))

            if (
                resolved.exists()
                and resolved.is_file()
                and "python" in resolved.name.lower()
            ):
                return resolved.resolve()
        except OSError:
            continue

    raise RuntimeError(
        "The Python interpreter bundled with QGIS could not be found. "
        "Checked paths:\n"
        + "\n".join(checked)
    )


def runner_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "tide_engine_runner.py"
    )


def engine_environment_exists() -> bool:
    """
    Return whether a tide virtual-environment folder already exists.

    This is deliberately different from engine_installed(): a virtual
    environment can exist while being unusable after QGIS is reinstalled,
    upgraded or moved to a different directory.
    """
    return venv_directory().exists()


def _python_probe_command(
    include_packages: bool = True,
) -> str:
    imports = (
        "import pyTMD, h5py, h5netcdf, dask, dask.array; "
        if include_packages
        else ""
    )

    return (
        "import sys; "
        + imports
        + "print(sys.executable)"
    )


def probe_python_interpreter(
    python_path: Path,
    include_packages: bool = True,
    timeout: int = 20,
) -> tuple[bool, str]:
    """
    Test whether a Python executable can start and import tide dependencies.

    Windows virtual environments store an absolute reference to the base
    Python installation. After QGIS is reinstalled or moved, Scripts/python.exe
    may still exist but fail with a message such as:

        No Python at 'C:\\Program Files\\QGIS ...\\python.exe'
    """
    candidate = Path(
        python_path
    ).expanduser()

    if not candidate.exists():
        return (
            False,
            f"Python executable not found: {candidate}",
        )

    environment = os.environ.copy()
    environment["PYTHONNOUSERSITE"] = "1"

    try:
        completed = subprocess.run(  # nosec B603
            [
                str(candidate),
                "-c",
                _python_probe_command(
                    include_packages=include_packages
                ),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(
                5,
                int(timeout),
            ),
            env=environment,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if os.name == "nt"
                else 0
            ),
            check=False,
        )
    except Exception as error:
        return (
            False,
            f"{type(error).__name__}: {error}",
        )

    output = (
        completed.stdout
        or ""
    ).strip()

    if completed.returncode != 0:
        return (
            False,
            output
            or (
                "The Python interpreter returned exit code "
                f"{completed.returncode}."
            ),
        )

    return (
        True,
        output
        or str(candidate),
    )


def engine_health() -> tuple[str, str]:
    """
    Return (status, details) for the isolated tide environment.

    status is one of:
        missing
        broken
        ready
    """
    python_path = venv_python()

    if not engine_environment_exists():
        return (
            "missing",
            "The isolated tide environment has not been created.",
        )

    interpreter_ready, interpreter_details = (
        probe_python_interpreter(
            python_path,
            include_packages=False,
        )
    )

    if not interpreter_ready:
        return (
            "broken",
            interpreter_details,
        )

    packages_ready, package_details = (
        probe_python_interpreter(
            python_path,
            include_packages=True,
        )
    )

    if not packages_ready:
        return (
            "broken",
            package_details,
        )

    return (
        "ready",
        package_details,
    )


def engine_installed() -> bool:
    status, _ = engine_health()
    return status == "ready"


def expected_model_files() -> list[Path]:
    base = (
        models_directory()
        / "GOT4.10c"
        / "grids_oceantide_netcdf"
    )

    return [
        base / name
        for name in (
            "q1.nc",
            "o1.nc",
            "p1.nc",
            "k1.nc",
            "n2.nc",
            "m2.nc",
            "s2.nc",
            "k2.nc",
            "s1.nc",
            "m4.nc",
        )
    ]


def model_files_present() -> bool:
    return all(
        path.exists()
        and path.stat().st_size > 0
        for path in expected_model_files()
    )


def quote_identifier(value: str) -> str:
    return (
        '"'
        + str(value).replace('"', '""')
        + '"'
    )


def identifier_sql(
    template: str,
    **identifiers: str,
) -> str:
    """Insert only SQLite-quoted identifiers into an internal SQL template."""
    quoted = {
        name: quote_identifier(value)
        for name, value in identifiers.items()
    }
    return template.format(**quoted)


def _gpkg_geometry_bounds(
    geometry_blob,
) -> tuple[
    float | None,
    float | None,
    float | None,
    float | None,
]:
    """
    Read a bounding box from a GeoPackage geometry blob.

    ATL24 layers contain point geometries. The parser first uses the
    GeoPackage envelope when present and otherwise reads the X/Y values
    from the embedded WKB point. No external spatial extension is needed.
    """
    if geometry_blob is None:
        return (
            None,
            None,
            None,
            None,
        )

    data = bytes(geometry_blob)

    if len(data) < 8 or data[:2] != b"GP":
        return (
            None,
            None,
            None,
            None,
        )

    flags = data[3]
    byte_order = (
        "<"
        if flags & 0x01
        else ">"
    )

    # GeoPackageBinary empty-geometry flag.
    if flags & 0x10:
        return (
            None,
            None,
            None,
            None,
        )

    envelope_indicator = (
        flags >> 1
    ) & 0x07

    envelope_lengths = {
        0: 0,
        1: 4,  # XY
        2: 6,  # XYZ
        3: 6,  # XYM
        4: 8,  # XYZM
    }

    envelope_value_count = (
        envelope_lengths.get(
            envelope_indicator,
            0,
        )
    )

    if envelope_value_count:
        envelope_size = (
            envelope_value_count
            * 8
        )

        if len(data) >= 8 + envelope_size:
            values = struct.unpack(
                byte_order
                + (
                    "d"
                    * envelope_value_count
                ),
                data[
                    8:
                    8 + envelope_size
                ],
            )

            return (
                float(values[0]),
                float(values[1]),
                float(values[2]),
                float(values[3]),
            )

    # Without a GeoPackage envelope, parse the embedded WKB point.
    wkb_offset = (
        8
        + envelope_value_count
        * 8
    )

    if len(data) < wkb_offset + 21:
        return (
            None,
            None,
            None,
            None,
        )

    wkb_byte_order = (
        "<"
        if data[wkb_offset] == 1
        else ">"
    )

    geometry_type = struct.unpack(
        wkb_byte_order + "I",
        data[
            wkb_offset + 1:
            wkb_offset + 5
        ],
    )[0]

    # Strip EWKB dimension/SRID flags and ISO Z/M offsets.
    base_type = (
        geometry_type
        & 0x000000FF
    )

    if base_type != 1:
        base_type = (
            geometry_type
            % 1000
        )

    if base_type != 1:
        return (
            None,
            None,
            None,
            None,
        )

    x, y = struct.unpack(
        wkb_byte_order + "dd",
        data[
            wkb_offset + 5:
            wkb_offset + 21
        ],
    )

    if (
        x != x
        or y != y
    ):
        return (
            None,
            None,
            None,
            None,
        )

    return (
        float(x),
        float(x),
        float(y),
        float(y),
    )


def register_geopackage_sql_functions(
    connection: sqlite3.Connection,
) -> None:
    """
    Register spatial functions referenced by OGR GeoPackage triggers.

    Python's built-in sqlite3 connection does not automatically load the
    GeoPackage/SpatiaLite SQL extension. OGR RTree triggers can call these
    functions even when only a non-spatial attribute is updated.
    """

    def st_is_empty(
        geometry_blob,
    ) -> int:
        bounds = _gpkg_geometry_bounds(
            geometry_blob
        )

        return int(
            all(
                value is None
                for value in bounds
            )
        )

    def st_min_x(
        geometry_blob,
    ):
        return _gpkg_geometry_bounds(
            geometry_blob
        )[0]

    def st_max_x(
        geometry_blob,
    ):
        return _gpkg_geometry_bounds(
            geometry_blob
        )[1]

    def st_min_y(
        geometry_blob,
    ):
        return _gpkg_geometry_bounds(
            geometry_blob
        )[2]

    def st_max_y(
        geometry_blob,
    ):
        return _gpkg_geometry_bounds(
            geometry_blob
        )[3]

    connection.create_function(
        "ST_IsEmpty",
        1,
        st_is_empty,
    )
    connection.create_function(
        "ST_MinX",
        1,
        st_min_x,
    )
    connection.create_function(
        "ST_MaxX",
        1,
        st_max_x,
    )
    connection.create_function(
        "ST_MinY",
        1,
        st_min_y,
    )
    connection.create_function(
        "ST_MaxY",
        1,
        st_max_y,
    )


def parse_engine_line(
    line: str,
) -> tuple[str | None, dict[str, Any] | None]:
    text = line.strip()

    for prefix in (
        "PROGRESS",
        "RESULT",
        "ERROR",
    ):
        marker = prefix + " "

        if text.startswith(marker):
            try:
                return (
                    prefix,
                    json.loads(
                        text[len(marker):]
                    ),
                )
            except json.JSONDecodeError:
                return (
                    prefix,
                    {
                        "message": text[
                            len(marker):
                        ]
                    },
                )

    return None, None


def normalize_utc_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(
        value,
        (
            int,
            float,
        ),
    ):
        number = float(value)
        absolute = abs(number)

        if absolute >= 1e17:
            seconds = number / 1e9
        elif absolute >= 1e14:
            seconds = number / 1e6
        elif absolute >= 1e11:
            seconds = number / 1e3
        else:
            seconds = number

        try:
            dt = datetime.fromtimestamp(
                seconds,
                tz=timezone.utc,
            )
        except (
            OverflowError,
            OSError,
            ValueError,
        ):
            return None
    else:
        text = str(value).strip()

        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(
                text
            )
        except ValueError:
            dt = None

            for format_string in (
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(
                        text,
                        format_string,
                    )
                    break
                except ValueError:
                    continue

            if dt is None:
                return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )
    else:
        dt = dt.astimezone(
            timezone.utc
        )

    return (
        dt.isoformat(
            timespec="milliseconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
    )


class ExternalProcessTask(QgsTask):
    """
    QgsTask helper for commands executed outside the QGIS Python process.
    """

    def __init__(
        self,
        description: str,
    ):
        super().__init__(
            description,
            QgsTask.Flag.CanCancel,
        )

        self.error_message: str | None = None
        self.error_traceback: str | None = None
        self.result_data: dict[str, Any] = {}
        self.process: subprocess.Popen | None = None
        self.console_lines: list[str] = []

    def _run_process(
        self,
        command: list[str],
        progress_start: float = 0.0,
        progress_span: float = 100.0,
    ) -> dict[str, Any]:
        environment = os.environ.copy()
        environment["PYTHONNOUSERSITE"] = "1"

        logs_directory().mkdir(
            parents=True,
            exist_ok=True,
        )

        self.process = subprocess.Popen(  # nosec B603
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=environment,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if os.name == "nt"
                else 0
            ),
        )

        result: dict[str, Any] = {}
        engine_error: dict[str, Any] | None = None

        process_stdout = self.process.stdout
        if process_stdout is None:
            raise RuntimeError(
                "The model tide process output stream is unavailable."
            )

        for line in process_stdout:
            self.console_lines.append(
                line.rstrip()
            )

            kind, payload = parse_engine_line(
                line
            )

            if kind == "PROGRESS" and payload:
                raw = float(
                    payload.get(
                        "value",
                        0.0,
                    )
                )

                self.setProgress(
                    progress_start
                    + progress_span
                    * raw
                    / 100.0
                )
            elif kind == "RESULT" and payload:
                result = dict(payload)
            elif kind == "ERROR" and payload:
                engine_error = dict(payload)

            if self.isCanceled():
                self._terminate_process()
                raise RuntimeError(
                    "Task cancelled."
                )

        return_code = self.process.wait()
        self.process = None

        if return_code != 0:
            if engine_error:
                raise RuntimeError(
                    engine_error.get(
                        "message",
                        "Tide engine failed.",
                    )
                    + "\n\n"
                    + engine_error.get(
                        "traceback",
                        "",
                    )
                )

            tail = "\n".join(
                self.console_lines[-30:]
            )

            raise RuntimeError(
                "External tide process failed.\n\n"
                + tail
            )

        return result

    def _terminate_process(self) -> None:
        if (
            self.process is not None
            and self.process.poll() is None
        ):
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:  # nosec B110
                    pass


class TideSupportInstallTask(ExternalProcessTask):
    """
    Create an isolated virtual environment and install pyTMD.
    """

    def __init__(self):
        super().__init__(
            "Install tide support"
        )

    def run(self) -> bool:
        try:
            root = support_root()
            root.mkdir(
                parents=True,
                exist_ok=True,
            )

            logs_directory().mkdir(
                parents=True,
                exist_ok=True,
            )

            python_path = venv_python()

            interpreter_ready, _ = (
                probe_python_interpreter(
                    python_path,
                    include_packages=False,
                )
            )

            if not interpreter_ready:
                # A Windows venv is linked to the absolute path of the Python
                # installation that created it. Recreate it automatically when
                # QGIS was reinstalled, upgraded or installed elsewhere.
                if venv_directory().exists():
                    shutil.rmtree(
                        venv_directory(),
                        ignore_errors=True,
                    )

                base_python = qgis_base_python()

                base_ready, base_details = (
                    probe_python_interpreter(
                        base_python,
                        include_packages=False,
                    )
                )

                if not base_ready:
                    raise RuntimeError(
                        "The current QGIS Python interpreter could not be "
                        "started.\n\n"
                        + base_details
                    )

                self.setProgress(5)

                self._run_process(
                    [
                        str(base_python),
                        "-m",
                        "venv",
                        "--copies",
                        str(
                            venv_directory()
                        ),
                    ],
                    progress_start=5,
                    progress_span=20,
                )

                python_path = venv_python()

                recreated_ready, recreated_details = (
                    probe_python_interpreter(
                        python_path,
                        include_packages=False,
                    )
                )

                if not recreated_ready:
                    raise RuntimeError(
                        "The virtual environment was recreated, but its "
                        "Python interpreter could not be started.\n\n"
                        + recreated_details
                    )

            if self.isCanceled():
                return False

            self.setProgress(30)

            self._run_process(
                [
                    str(python_path),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--upgrade",
                    "pip",
                    "setuptools",
                    "wheel",
                ],
                progress_start=30,
                progress_span=15,
            )

            if self.isCanceled():
                return False

            self._run_process(
                [
                    str(python_path),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--upgrade",
                    f"pyTMD=={PYTMD_VERSION}",
                    f"h5py=={H5PY_VERSION}",
                    f"h5netcdf=={H5NETCDF_VERSION}",
                    f"dask[array]=={DASK_VERSION}",
                ],
                progress_start=45,
                progress_span=45,
            )

            result = self._run_process(
                [
                    str(python_path),
                    str(runner_path()),
                    "status",
                    "--models-dir",
                    str(models_directory()),
                ],
                progress_start=90,
                progress_span=10,
            )

            self.result_data = result
            self.setProgress(100)
            return True

        except Exception as error:
            self.error_message = (
                f"{type(error).__name__}: {error}"
            )
            self.error_traceback = traceback.format_exc()
            return False

        finally:
            self._terminate_process()


class TideModelDownloadTask(ExternalProcessTask):
    """
    Download and verify GOT4.10c in the managed model directory.
    """

    def __init__(self):
        super().__init__(
            "Download GOT4.10c tide model"
        )

    def run(self) -> bool:
        try:
            if not engine_installed():
                status, details = engine_health()
                raise RuntimeError(
                    "The isolated tide environment is not ready. "
                    "Open Model Tide Values and click Repair tide support.\n\n"
                    f"Environment status: {status}\n"
                    f"{details}"
                )

            models_directory().mkdir(
                parents=True,
                exist_ok=True,
            )

            self.result_data = self._run_process(
                [
                    str(venv_python()),
                    str(runner_path()),
                    "download-model",
                    "--models-dir",
                    str(models_directory()),
                ]
            )

            self.setProgress(100)
            return True

        except Exception as error:
            self.error_message = (
                f"{type(error).__name__}: {error}"
            )
            self.error_traceback = traceback.format_exc()
            return False

        finally:
            self._terminate_process()


class ModelTideComputeTask(ExternalProcessTask):
    """
    Compute GOT4.10c values and append them to a copied ATL24 GeoPackage.
    """

    OUTPUT_FIELDS = {
        "tide_ocean_model_m": "REAL",
        "depth_tide_corrected_m": "REAL",
        "tide_time_utc": "TEXT",
        "tide_valid": "INTEGER",
        "tide_model": "TEXT",
        "tide_method": "TEXT",
    }

    def __init__(
        self,
        source_path: str,
        source_table: str,
        output_path: str,
        output_table: str,
        method: str,
        extrapolate: bool,
        chunk_size: int,
    ):
        super().__init__(
            "Add model tide values"
        )

        self.source_path = str(source_path)
        self.source_table = str(source_table)
        self.output_path = str(output_path)
        self.output_table = str(output_table)

        self.method = str(method)
        self.extrapolate = bool(
            extrapolate
        )
        self.chunk_size = int(
            chunk_size
        )

        self.total_records = 0
        self.valid_records = 0
        self.invalid_records = 0
        self.corrected_depth_records = 0
        self.minimum_corrected_depth_m: float | None = None
        self.maximum_corrected_depth_m: float | None = None
        self.mean_corrected_depth_m: float | None = None
        self.report_path: str | None = None

    def run(self) -> bool:
        temporary_directory = None

        try:
            if not engine_installed():
                status, details = engine_health()
                raise RuntimeError(
                    "The isolated tide environment is not ready. "
                    "Open Model Tide Values and click Repair tide support.\n\n"
                    f"Environment status: {status}\n"
                    f"{details}"
                )

            if not model_files_present():
                raise RuntimeError(
                    "GOT4.10c is not installed or is incomplete."
                )

            source_file = Path(
                self.source_path
            ).expanduser().resolve()

            output_file = Path(
                self.output_path
            ).expanduser().resolve()

            if not source_file.exists():
                raise FileNotFoundError(
                    f"Source GeoPackage not found: {source_file}"
                )

            if source_file == output_file:
                raise ValueError(
                    "Choose an output different from "
                    "the source GeoPackage."
                )

            output_file.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            if output_file.exists():
                output_file.unlink()

            self.setProgress(2)

            shutil.copy2(
                source_file,
                output_file,
            )

            connection = sqlite3.connect(
                str(output_file),
                timeout=120,
            )

            try:
                register_geopackage_sql_functions(
                    connection
                )

                connection.execute(
                    "PRAGMA busy_timeout = 120000"
                )

                columns = self._table_columns(
                    connection
                )

                required = {
                    "longitude",
                    "latitude",
                    "time_ns",
                    "depth",
                }

                missing = sorted(
                    required.difference(
                        columns
                    )
                )

                if missing:
                    raise ValueError(
                        "The source layer is missing fields: "
                        + ", ".join(missing)
                    )

                primary_key = self._primary_key(
                    connection
                )

                self._prepare_output_fields(
                    connection
                )

                count_sql = identifier_sql(
                    """
                    SELECT COUNT(*)
                    FROM {source_table}
                    """,
                    source_table=self.source_table,
                )
                self.total_records = int(
                    connection.execute(
                        count_sql
                    ).fetchone()[0]
                )

                temporary_directory = Path(
                    tempfile.mkdtemp(
                        prefix="icesat2_tide_"
                    )
                )

                input_csv = (
                    temporary_directory
                    / "tide_input.csv"
                )
                result_csv = (
                    temporary_directory
                    / "tide_output.csv"
                )

                invalid_inputs = self._export_input_csv(
                    connection=connection,
                    primary_key=primary_key,
                    input_csv=input_csv,
                )

                self.setProgress(12)

                engine_result = self._run_process(
                    [
                        str(venv_python()),
                        str(runner_path()),
                        "compute",
                        "--models-dir",
                        str(models_directory()),
                        "--input-csv",
                        str(input_csv),
                        "--output-csv",
                        str(result_csv),
                        "--total",
                        str(self.total_records),
                        "--chunk-size",
                        str(self.chunk_size),
                        "--method",
                        self.method,
                        "--extrapolate",
                        "1"
                        if self.extrapolate
                        else "0",
                    ],
                    progress_start=12,
                    progress_span=70,
                )

                self.result_data = dict(
                    engine_result
                )

                self._import_results(
                    connection=connection,
                    primary_key=primary_key,
                    result_csv=result_csv,
                )

                self._calculate_tide_corrected_depth(
                    connection
                )

                self.valid_records = int(
                    engine_result.get(
                        "valid_records",
                        0,
                    )
                )

                self.invalid_records = int(
                    engine_result.get(
                        "invalid_records",
                        0,
                    )
                )

                if invalid_inputs:
                    self.result_data.setdefault(
                        "warnings",
                        []
                    ).append(
                        f"{invalid_inputs} input records had "
                        "invalid coordinates or timestamps."
                    )

                self._write_metadata(
                    connection=connection,
                    engine_result=engine_result,
                )

                connection.commit()

            finally:
                connection.close()

            self.setProgress(92)

            report_data = {
                "status": "Completed",
                "source_path": str(source_file),
                "source_layer": self.source_table,
                "output_layer": self.output_table,
                "total_records": self.total_records,
                "valid_records": self.valid_records,
                "invalid_records": self.invalid_records,
                "model_id": MODEL_ID,
                "model_distribution": MODEL_DISTRIBUTION,
                "method": self.method,
                "extrapolate": self.extrapolate,
                "pytmd_version": engine_result.get(
                    "pytmd_version",
                    "unknown",
                ),
                "minimum_tide_m": engine_result.get(
                    "minimum_tide_m"
                ),
                "maximum_tide_m": engine_result.get(
                    "maximum_tide_m"
                ),
                "mean_tide_m": engine_result.get(
                    "mean_tide_m"
                ),
                "median_tide_m": engine_result.get(
                    "median_tide_m"
                ),
                "corrected_depth_records": (
                    self.corrected_depth_records
                ),
                "minimum_corrected_depth_m": (
                    self.minimum_corrected_depth_m
                ),
                "maximum_corrected_depth_m": (
                    self.maximum_corrected_depth_m
                ),
                "mean_corrected_depth_m": (
                    self.mean_corrected_depth_m
                ),
                "corrected_depth_formula": (
                    "depth - tide_ocean_model_m"
                ),
                "first_time_utc": engine_result.get(
                    "first_time_utc"
                ),
                "last_time_utc": engine_result.get(
                    "last_time_utc"
                ),
                "warnings": self.result_data.get(
                    "warnings",
                    [],
                ),
                "field_schema": self._read_field_schema(
                    output_file
                ),
                "engine_summary": engine_result,
            }

            report = export_model_tide_report(
                output_path=str(output_file),
                data=report_data,
            )

            self.report_path = str(report)

            self.setProgress(100)
            return True

        except Exception as error:
            self.error_message = (
                f"{type(error).__name__}: {error}"
            )
            self.error_traceback = traceback.format_exc()
            return False

        finally:
            self._terminate_process()

            if (
                temporary_directory is not None
                and temporary_directory.exists()
            ):
                shutil.rmtree(
                    temporary_directory,
                    ignore_errors=True,
                )

    def _read_field_schema(
        self,
        output_file: Path,
    ) -> list[dict[str, str]]:
        connection = sqlite3.connect(
            str(output_file)
        )

        try:
            geometry_row = connection.execute(
                """
                SELECT column_name
                FROM gpkg_geometry_columns
                WHERE table_name = ?
                """,
                (self.source_table,),
            ).fetchone()

            geometry_name = (
                str(geometry_row[0])
                if geometry_row
                else "geom"
            )

            rows = connection.execute(
                f"""
                PRAGMA table_info(
                    {quote_identifier(self.source_table)}
                )
                """
            ).fetchall()

            return [
                {
                    "name": str(row[1]),
                    "type": str(row[2] or "—"),
                }
                for row in rows
                if str(row[1]) != geometry_name
            ]
        finally:
            connection.close()

    def _table_columns(
        self,
        connection: sqlite3.Connection,
    ) -> set[str]:
        rows = connection.execute(
            f"""
            PRAGMA table_info(
                {quote_identifier(self.source_table)}
            )
            """
        ).fetchall()

        if not rows:
            raise ValueError(
                f"GeoPackage table not found: {self.source_table}"
            )

        return {
            str(row[1])
            for row in rows
        }

    def _primary_key(
        self,
        connection: sqlite3.Connection,
    ) -> str:
        rows = connection.execute(
            f"""
            PRAGMA table_info(
                {quote_identifier(self.source_table)}
            )
            """
        ).fetchall()

        primary = [
            str(row[1])
            for row in rows
            if int(row[5]) > 0
        ]

        if primary:
            return primary[0]

        columns = {
            str(row[1])
            for row in rows
        }

        if "fid" in columns:
            return "fid"

        raise ValueError(
            "No primary-key field was found."
        )

    def _prepare_output_fields(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        existing = self._table_columns(
            connection
        )

        for field, sql_type in (
            self.OUTPUT_FIELDS.items()
        ):
            if field not in existing:
                connection.execute(
                    f"""
                    ALTER TABLE {quote_identifier(self.source_table)}
                    ADD COLUMN {quote_identifier(field)}
                    {sql_type}
                    """
                )

        for field in self.OUTPUT_FIELDS:
            clear_sql = identifier_sql(
                """
                UPDATE {source_table}
                SET {field} = NULL
                """,
                source_table=self.source_table,
                field=field,
            )
            connection.execute(
                clear_sql
            )

        connection.commit()

    def _export_input_csv(
        self,
        connection: sqlite3.Connection,
        primary_key: str,
        input_csv: Path,
    ) -> int:
        invalid = 0

        select_sql = identifier_sql(
            """
            SELECT
                {primary_key},
                {longitude},
                {latitude},
                {time_ns}
            FROM {source_table}
            ORDER BY {primary_key}
            """,
            primary_key=primary_key,
            longitude="longitude",
            latitude="latitude",
            time_ns="time_ns",
            source_table=self.source_table,
        )
        cursor = connection.execute(
            select_sql
        )

        with input_csv.open(
            mode="w",
            encoding="utf-8",
            newline="",
        ) as target:
            writer = csv.DictWriter(
                target,
                fieldnames=[
                    "fid",
                    "longitude",
                    "latitude",
                    "time_utc",
                ],
            )
            writer.writeheader()

            for row in cursor:
                utc_text = normalize_utc_text(
                    row[3]
                )

                try:
                    longitude = float(
                        row[1]
                    )
                    latitude = float(
                        row[2]
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    longitude = ""
                    latitude = ""

                if (
                    utc_text is None
                    or longitude == ""
                    or latitude == ""
                ):
                    invalid += 1

                writer.writerow(
                    {
                        "fid": row[0],
                        "longitude": longitude,
                        "latitude": latitude,
                        "time_utc": utc_text or "",
                    }
                )

        return invalid

    def _import_results(
        self,
        connection: sqlite3.Connection,
        primary_key: str,
        result_csv: Path,
    ) -> None:
        updates = []

        with result_csv.open(
            mode="r",
            encoding="utf-8",
            newline="",
        ) as source:
            reader = csv.DictReader(
                source
            )

            for row in reader:
                value_text = str(
                    row.get(
                        "tide_ocean_model_m",
                        "",
                    )
                ).strip()

                value = (
                    float(value_text)
                    if value_text
                    else None
                )

                updates.append(
                    (
                        value,
                        row.get(
                            "tide_time_utc"
                        )
                        or None,
                        int(
                            row.get(
                                "tide_valid",
                                0,
                            )
                        ),
                        MODEL_ID,
                        self.method,
                        row["fid"],
                    )
                )

                if len(updates) >= 50000:
                    self._write_updates(
                        connection,
                        primary_key,
                        updates,
                    )
                    updates = []

        if updates:
            self._write_updates(
                connection,
                primary_key,
                updates,
            )

    def _write_updates(
        self,
        connection: sqlite3.Connection,
        primary_key: str,
        updates: list[tuple],
    ) -> None:
        update_sql = identifier_sql(
            """
            UPDATE {source_table}
            SET
                {tide_ocean_model_m} = ?,
                {tide_time_utc} = ?,
                {tide_valid} = ?,
                {tide_model} = ?,
                {tide_method} = ?
            WHERE
                {primary_key} = ?
            """,
            source_table=self.source_table,
            tide_ocean_model_m="tide_ocean_model_m",
            tide_time_utc="tide_time_utc",
            tide_valid="tide_valid",
            tide_model="tide_model",
            tide_method="tide_method",
            primary_key=primary_key,
        )
        connection.executemany(
            update_sql,
            updates,
        )

        connection.commit()

    def _calculate_tide_corrected_depth(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        Create a tide-reduced depth without modifying the ATL24 depth field.

        ATL24 depth is an instantaneous positive-down water depth. The GOT
        ocean-tide value is treated as a positive-up elevation relative to
        the model mean tide level. Therefore:

            depth_tide_corrected_m = depth - tide_ocean_model_m

        The result is a modeled mean-tide-level reduction, not a chart-datum
        transformation. A NULL result is retained when depth or model tide is
        unavailable.
        """
        depth_sql = identifier_sql(
            """
            UPDATE {source_table}
            SET
                {depth_tide_corrected_m} =
                    CASE
                        WHEN
                            {tide_valid} = 1
                            AND {depth} IS NOT NULL
                            AND {tide_ocean_model_m} IS NOT NULL
                        THEN
                            CAST(
                                {depth}
                                AS REAL
                            )
                            -
                            {tide_ocean_model_m}
                        ELSE NULL
                    END
            """,
            source_table=self.source_table,
            depth_tide_corrected_m="depth_tide_corrected_m",
            tide_valid="tide_valid",
            depth="depth",
            tide_ocean_model_m="tide_ocean_model_m",
        )
        connection.execute(
            depth_sql
        )
        connection.commit()

        statistics_sql = identifier_sql(
            """
            SELECT
                COUNT(
                    {depth_tide_corrected_m}
                ),
                MIN(
                    {depth_tide_corrected_m}
                ),
                MAX(
                    {depth_tide_corrected_m}
                ),
                AVG(
                    {depth_tide_corrected_m}
                )
            FROM {source_table}
            WHERE
                {depth_tide_corrected_m}
                IS NOT NULL
            """,
            depth_tide_corrected_m="depth_tide_corrected_m",
            source_table=self.source_table,
        )
        statistics = connection.execute(
            statistics_sql
        ).fetchone()

        self.corrected_depth_records = int(
            statistics[0]
            if statistics
            else 0
        )
        self.minimum_corrected_depth_m = (
            float(statistics[1])
            if statistics
            and statistics[1] is not None
            else None
        )
        self.maximum_corrected_depth_m = (
            float(statistics[2])
            if statistics
            and statistics[2] is not None
            else None
        )
        self.mean_corrected_depth_m = (
            float(statistics[3])
            if statistics
            and statistics[3] is not None
            else None
        )

    def _write_metadata(
        self,
        connection: sqlite3.Connection,
        engine_result: dict[str, Any],
    ) -> None:
        metadata = {
            "tool": "ICESat-2 Data Explorer model tide",
            "processing_date_utc": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "source_table": self.source_table,
            "time_input_field": "time_ns",
            "time_standard": "UTC datetime",
            "coordinate_fields": "longitude, latitude",
            "input_crs": "EPSG:4326",
            "tide_output_field": "tide_ocean_model_m",
            "tide_units": "m",
            "corrected_depth_output_field": (
                "depth_tide_corrected_m"
            ),
            "corrected_depth_formula": (
                "depth - tide_ocean_model_m"
            ),
            "corrected_depth_reference": (
                "modeled mean tide level; not chart datum"
            ),
            "tide_model": MODEL_ID,
            "model_distribution": MODEL_DISTRIBUTION,
            "model_format": "NetCDF",
            "interpolation_method": self.method,
            "spatial_extrapolation": str(
                self.extrapolate
            ),
            "depth_modified": "False",
            "corrected_depth_records": str(
                self.corrected_depth_records
            ),
            "pytmd_version": engine_result.get(
                "pytmd_version",
                "unknown",
            ),
            "total_records": str(
                self.total_records
            ),
            "valid_records": str(
                self.valid_records
            ),
            "invalid_records": str(
                self.invalid_records
            ),
            "model_storage": "managed external cache",
        }

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tide_model_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parameter TEXT NOT NULL,
                value TEXT
            )
            """
        )

        connection.execute(
            """
            DELETE FROM tide_model_metadata
            """
        )

        connection.executemany(
            """
            INSERT INTO tide_model_metadata (
                parameter,
                value
            )
            VALUES (?, ?)
            """,
            [
                (
                    str(key),
                    str(value),
                )
                for key, value in metadata.items()
            ],
        )

        try:
            connection.execute(
                """
                DELETE FROM gpkg_contents
                WHERE table_name = 'tide_model_metadata'
                """
            )

            connection.execute(
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
                    'tide_model_metadata',
                    'attributes',
                    'tide_model_metadata',
                    'ATL24 model-tide prediction metadata',
                    strftime(
                        '%Y-%m-%dT%H:%M:%fZ',
                        'now'
                    ),
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL
                )
                """
            )
        except sqlite3.Error:
            pass
