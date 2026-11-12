from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import tempfile
import traceback
from pathlib import Path

from qgis.core import QgsTask

from .hdf5_support import managed_site_packages
from .sliderule_support import qgis_base_python


class HDF5ConverterTask(QgsTask):
    """Convert ICESat-2 HDF5 without loading h5py inside the QGIS process."""

    CHUNK_SIZE = 50_000
    PROGRESS_PREFIX = "__ICESAT2_PROGRESS__="
    RESULT_PREFIX = "__ICESAT2_RESULT__="
    ERROR_PREFIX = "__ICESAT2_ERROR__="

    def __init__(self, input_path: str, output_path: str, output_format: str):
        super().__init__(
            "Convert ICESat-2 HDF5 granule",
            QgsTask.Flag.CanCancel,
        )
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
        self._process: subprocess.Popen | None = None
        self._temporary_csv: Path | None = None
        self._temporary_output: Path | None = None

    @staticmethod
    def _creation_flags() -> int:
        if os.name == "nt":
            return subprocess.CREATE_NO_WINDOW
        return 0

    @staticmethod
    def _temp_path(output_path: Path, suffix: str) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            prefix=f".{output_path.stem}_",
            suffix=suffix,
            dir=str(output_path.parent),
            delete=False,
        )
        temp.close()
        path = Path(temp.name)
        path.unlink(missing_ok=True)
        return path

    @staticmethod
    def _commit(source: Path, destination: Path) -> None:
        if destination.exists():
            destination.unlink()
        source.replace(destination)

    def _run_worker(self, csv_path: Path) -> dict:
        worker_path = Path(__file__).with_name("hdf5_converter_worker.py")
        if not worker_path.exists():
            raise RuntimeError("The isolated HDF5 worker file is missing from the plugin.")

        site_packages = managed_site_packages()
        if not site_packages.exists():
            raise RuntimeError(
                "HDF5 support is not installed. Return to the converter and click "
                "'Install HDF5 support'."
            )

        command = [
            str(qgis_base_python()),
            str(worker_path),
            "--site-packages",
            str(site_packages),
            "--input",
            self.input_path,
            "--output-csv",
            str(csv_path),
        ]

        environment = os.environ.copy()
        environment.pop("PYTHONNOUSERSITE", None)

        self._process = subprocess.Popen(  # nosec B603
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            creationflags=self._creation_flags(),
        )

        output_lines: list[str] = []
        result: dict | None = None
        worker_error: dict | None = None
        stdout = self._process.stdout
        if stdout is None:
            raise RuntimeError("The HDF5 worker output stream is unavailable.")

        for raw_line in iter(stdout.readline, ""):
            line = raw_line.rstrip("\r\n")
            output_lines.append(line)

            if line.startswith(self.PROGRESS_PREFIX):
                try:
                    value = float(line[len(self.PROGRESS_PREFIX):])
                    scale = 1.0 if self.output_format == "csv" else 0.85
                    self.setProgress(max(0.0, min(100.0, value * scale)))
                except ValueError:
                    pass
            elif line.startswith(self.RESULT_PREFIX):
                try:
                    result = json.loads(line[len(self.RESULT_PREFIX):])
                except json.JSONDecodeError:
                    result = None
            elif line.startswith(self.ERROR_PREFIX):
                try:
                    worker_error = json.loads(line[len(self.ERROR_PREFIX):])
                except json.JSONDecodeError:
                    worker_error = None

            if self.isCanceled():
                self._process.terminate()
                break

        return_code = self._process.wait()
        self._process = None

        if self.isCanceled():
            raise RuntimeError("Conversion canceled by the user.")

        if return_code != 0:
            if worker_error:
                message = str(worker_error.get("message") or "HDF5 conversion failed.")
                trace = str(worker_error.get("traceback") or "")
                if trace:
                    message += "\n\nTechnical details:\n" + trace
                raise RuntimeError(message)

            tail = "\n".join(output_lines[-30:]).strip()
            raise RuntimeError(tail or f"The HDF5 worker returned exit code {return_code}.")

        if result is None:
            tail = "\n".join(output_lines[-30:]).strip()
            raise RuntimeError(
                "The HDF5 worker finished without returning conversion metadata."
                + ("\n\n" + tail if tail else "")
            )

        return result

    def _csv_to_gpkg(self, csv_path: Path, gpkg_path: Path) -> None:
        try:
            import pandas as pd
            import geopandas as gpd
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "GeoPackage export requires Pandas and GeoPandas from the QGIS "
                "Python environment. CSV export is still available."
            ) from error

        wrote = False
        processed = 0
        total = max(int(self.row_count), 1)

        for frame in pd.read_csv(csv_path, chunksize=self.CHUNK_SIZE, low_memory=False):
            if self.isCanceled():
                raise RuntimeError("Conversion canceled by the user.")

            if "longitude" not in frame or "latitude" not in frame:
                raise RuntimeError(
                    "The isolated HDF5 worker did not return latitude/longitude columns."
                )

            longitude = pd.to_numeric(frame["longitude"], errors="coerce")
            latitude = pd.to_numeric(frame["latitude"], errors="coerce")
            geometry = gpd.points_from_xy(longitude, latitude)
            geodata = gpd.GeoDataFrame(
                frame,
                geometry=geometry,
                crs="EPSG:4326",
            )
            geodata.to_file(
                gpkg_path,
                layer=self.layer_name,
                driver="GPKG",
                mode="a" if wrote else "w",
                index=False,
            )
            wrote = True
            processed += len(frame)
            self.setProgress(85.0 + 15.0 * processed / total)

        if not wrote:
            raise RuntimeError("No records were available for GeoPackage export.")

    def run(self) -> bool:
        try:
            if self.output_format not in {"csv", "gpkg"}:
                raise RuntimeError("Unsupported output format. Choose CSV or GeoPackage.")

            input_path = Path(self.input_path)
            output_path = Path(self.output_path)
            if not input_path.exists() or not input_path.is_file():
                raise RuntimeError("Select an existing ICESat-2 HDF5 file.")
            if input_path.resolve() == output_path.resolve():
                raise RuntimeError("The output cannot overwrite the source HDF5 file.")

            csv_path = self._temp_path(output_path, ".csv")
            self._temporary_csv = csv_path
            result = self._run_worker(csv_path)

            self.product = str(result.get("product") or "")
            self.layer_name = str(result.get("layer_name") or f"{self.product.lower()}_records")
            self.row_count = int(result.get("row_count") or 0)
            self.beam_count = int(result.get("beam_count") or 0)
            skipped = result.get("skipped_datasets") or []
            self.skipped_datasets = [str(item) for item in skipped]

            if self.output_format == "csv":
                self._commit(csv_path, output_path)
                self._temporary_csv = None
                self.setProgress(100)
                return True

            temporary_gpkg = self._temp_path(output_path, ".gpkg")
            self._temporary_output = temporary_gpkg
            self._csv_to_gpkg(csv_path, temporary_gpkg)
            csv_path.unlink(missing_ok=True)
            self._temporary_csv = None

            self._commit(temporary_gpkg, output_path)
            self._temporary_output = None
            self.setProgress(100)
            return True

        except Exception as error:  # noqa: BLE001
            self.error_message = f"{type(error).__name__}: {error}"
            self.error_traceback = traceback.format_exc()
            return False

        finally:
            if self._temporary_csv is not None:
                self._temporary_csv.unlink(missing_ok=True)
                self._temporary_csv = None
            if self._temporary_output is not None:
                self._temporary_output.unlink(missing_ok=True)
                self._temporary_output = None
            if self._process is not None:
                try:
                    self._process.terminate()
                except Exception:  # noqa: BLE001,S110  # nosec B110
                    pass
                self._process = None

    def cancel(self) -> None:
        if self._process is not None:
            try:
                self._process.terminate()
            except Exception:  # noqa: BLE001,S110  # nosec B110
                pass
        super().cancel()
