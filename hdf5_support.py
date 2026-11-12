from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import traceback
from pathlib import Path

from qgis.core import QgsTask
from qgis.PyQt.QtCore import QStandardPaths

from .sliderule_support import qgis_base_python

H5PY_REQUIREMENT = "h5py>=3.11,<4"


def support_root() -> Path:
    local_data = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )

    if not local_data:
        local_data = os.environ.get(
            "LOCALAPPDATA",
            str(Path.home() / "AppData" / "Local"),
        )

    return (
        Path(local_data)
        / "ICESat2DataExplorer"
        / "hdf5_support"
    ).resolve()


def managed_site_packages() -> Path:
    return support_root() / "site-packages"


def ensure_support_path() -> Path:
    """Return plugin-managed HDF5 support without importing it into QGIS."""
    return managed_site_packages()


def managed_h5py_exists() -> bool:
    path = managed_site_packages()
    return (
        (path / "h5py").exists()
        or any(path.glob("h5py-*.dist-info"))
    )


def _probe_managed_h5py() -> tuple[str, str, str | None]:
    """Probe h5py in a clean QGIS-Python subprocess to avoid DLL conflicts."""
    path = managed_site_packages()
    if not managed_h5py_exists():
        return (
            "missing",
            "h5py has not been installed for this QGIS installation/profile.",
            None,
        )

    probe_code = (
        "import json,sys; "
        f"sys.path.insert(0, {str(path)!r}); "
        "import h5py; "
        "print(json.dumps({'version': getattr(h5py, '__version__', 'unknown'), "
        "'file': getattr(h5py, '__file__', 'unknown')}))"
    )
    environment = os.environ.copy()
    environment.pop("PYTHONNOUSERSITE", None)

    try:
        completed = subprocess.run(  # nosec B603
            [str(qgis_base_python()), "-c", probe_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            timeout=30,
            check=False,
        )
    except Exception as error:  # noqa: BLE001
        return ("broken", f"{type(error).__name__}: {error}", None)

    output = (completed.stdout or "").strip()
    if completed.returncode != 0:
        return (
            "broken",
            output or f"h5py probe returned exit code {completed.returncode}.",
            None,
        )

    try:
        payload = json.loads(output.splitlines()[-1])
        version = str(payload.get("version") or "unknown")
        location = str(payload.get("file") or "unknown")
    except Exception as error:  # noqa: BLE001
        return (
            "broken",
            f"Could not parse the isolated h5py health check: {error}. Output: {output}",
            None,
        )

    return ("ready", f"h5py {version} - {location} (isolated process)", version)


def hdf5_health() -> tuple[str, str, str | None]:
    """Return HDF5-support health without loading h5py inside QGIS."""
    return _probe_managed_h5py()


def activate_managed_hdf5() -> tuple[str, str, str | None]:
    """Validate the plugin-managed h5py installation in an isolated process."""
    importlib.invalidate_caches()
    return hdf5_health()


class HDF5InstallTask(QgsTask):
    """Install a compatible h5py wheel without changing the QGIS installation."""

    def __init__(self):
        super().__init__(
            "Install ICESat-2 HDF5 support",
            QgsTask.Flag.CanCancel,
        )
        self.error_message = ""
        self.error_traceback = ""
        self.process_output = ""
        self.installed_version: str | None = None
        self._process: subprocess.Popen | None = None

    @staticmethod
    def _creation_flags() -> int:
        if os.name == "nt":
            return subprocess.CREATE_NO_WINDOW
        return 0

    def _run_process(
        self,
        command: list[str],
        environment: dict[str, str] | None = None,
    ) -> str:
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

        lines: list[str] = []
        process_stdout = self._process.stdout
        if process_stdout is None:
            raise RuntimeError(
                "The installer process output stream is unavailable."
            )

        for line in iter(process_stdout.readline, ""):
            lines.append(line)
            if self.isCanceled():
                self._process.terminate()
                break

        return_code = self._process.wait()
        output = "".join(lines).strip()
        self._process = None

        if self.isCanceled():
            raise RuntimeError("Installation canceled by the user.")

        if return_code != 0:
            raise RuntimeError(
                output
                or f"The installer returned exit code {return_code}."
            )

        return output

    def run(self) -> bool:
        temporary_target: Path | None = None

        try:
            root = support_root()
            root.mkdir(parents=True, exist_ok=True)
            base_python = qgis_base_python()
            self.setProgress(5)

            self._run_process(
                [
                    str(base_python),
                    "-m",
                    "pip",
                    "--version",
                ]
            )

            if self.isCanceled():
                return False

            self.setProgress(15)
            temporary_target = Path(
                tempfile.mkdtemp(
                    prefix="hdf5_install_",
                    dir=str(root),
                )
            )

            environment = os.environ.copy()
            environment.pop("PYTHONNOUSERSITE", None)

            self.process_output = self._run_process(
                [
                    str(base_python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--only-binary=:all:",
                    "--no-deps",
                    "--upgrade",
                    "--target",
                    str(temporary_target),
                    H5PY_REQUIREMENT,
                ],
                environment=environment,
            )

            self.setProgress(75)
            probe_code = (
                "import sys; "
                f"sys.path.insert(0, {str(temporary_target)!r}); "
                "import h5py; "
                "print(getattr(h5py, '__version__', 'unknown'))"
            )
            version_output = self._run_process(
                [
                    str(base_python),
                    "-c",
                    probe_code,
                ],
                environment=environment,
            )
            self.installed_version = (
                version_output.splitlines()[-1].strip()
                if version_output
                else "unknown"
            )

            self.setProgress(90)
            final_target = managed_site_packages()
            backup_target = root / "site-packages_previous"

            if backup_target.exists():
                shutil.rmtree(backup_target, ignore_errors=True)

            if final_target.exists():
                final_target.rename(backup_target)

            temporary_target.rename(final_target)
            temporary_target = None

            if backup_target.exists():
                shutil.rmtree(backup_target, ignore_errors=True)

            self.setProgress(100)
            return True

        except Exception as error:  # noqa: BLE001
            self.error_message = f"{type(error).__name__}: {error}"
            self.error_traceback = traceback.format_exc()
            return False

        finally:
            if temporary_target is not None and temporary_target.exists():
                shutil.rmtree(temporary_target, ignore_errors=True)

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
