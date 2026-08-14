from __future__ import annotations

import importlib
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import traceback

from pathlib import Path

from qgis.PyQt.QtCore import QStandardPaths
from qgis.core import QgsApplication, QgsTask


SLIDERULE_VERSION = "5.5.0"


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
        / "download_support"
    ).resolve()


def managed_site_packages() -> Path:
    return support_root() / "site-packages"


def logs_directory() -> Path:
    return support_root() / "logs"


def ensure_support_path() -> Path:
    """Put the plugin-managed pure-Python package directory first."""
    path = managed_site_packages()
    path_text = str(path)

    if path.exists() and path_text not in sys.path:
        sys.path.insert(0, path_text)

    return path


def managed_sliderule_exists() -> bool:
    path = managed_site_packages()
    return (
        (path / "sliderule").exists()
        or any(path.glob("sliderule-*.dist-info"))
    )


def qgis_base_python() -> Path:
    """Locate the actual Python interpreter bundled with QGIS."""
    candidates: list[Path] = []

    for prefix in (
        getattr(sys, "prefix", None),
        getattr(sys, "base_prefix", None),
        os.environ.get("PYTHONHOME"),
    ):
        if not prefix:
            continue

        prefix_path = Path(str(prefix)).expanduser()

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
        qgis_prefix = Path(QgsApplication.prefixPath())
        apps_directory = qgis_prefix.parent

        if os.name == "nt":
            for python_directory in sorted(
                apps_directory.glob("Python*"),
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

    current_executable = Path(sys.executable)
    if current_executable.name.lower() in {
        "python.exe",
        "python3.exe",
        "python",
        "python3",
    }:
        candidates.append(current_executable)

    checked: list[str] = []

    for candidate in candidates:
        try:
            candidate = candidate.expanduser()
            checked.append(str(candidate))

            if (
                candidate.exists()
                and candidate.is_file()
                and "python" in candidate.name.lower()
            ):
                return candidate.resolve()
        except OSError:
            continue

    raise RuntimeError(
        "The Python interpreter bundled with QGIS could not be found. "
        "Checked paths:\n"
        + "\n".join(checked)
    )


def sliderule_health() -> tuple[str, str, str | None]:
    """
    Return (state, details, version).

    state is one of: missing, broken, ready.
    """
    ensure_support_path()

    try:
        module = importlib.import_module("sliderule")
        version = str(getattr(module, "__version__", "unknown"))

        # These are already supplied by QGIS and are required by the plugin's
        # SlideRule-to-GeoPackage workflow. They are checked, never installed.
        importlib.import_module("numpy")
        importlib.import_module("pandas")
        importlib.import_module("geopandas")

        location = str(
            Path(getattr(module, "__file__", "unknown"))
        )

        return (
            "ready",
            f"SlideRule {version} — {location}",
            version,
        )
    except ModuleNotFoundError as error:
        if error.name == "sliderule":
            return (
                "missing",
                "The SlideRule Python client has not been installed for this QGIS profile.",
                None,
            )

        return (
            "broken",
            f"A required Python package is missing: {error.name}",
            None,
        )
    except Exception as error:
        return (
            "broken",
            f"{type(error).__name__}: {error}",
            None,
        )


def activate_managed_sliderule() -> tuple[str, str, str | None]:
    """Reload SlideRule from the managed directory after installation."""
    ensure_support_path()
    importlib.invalidate_caches()

    for name in list(sys.modules):
        if name == "sliderule" or name.startswith("sliderule."):
            sys.modules.pop(name, None)

    return sliderule_health()


class SlideruleInstallTask(QgsTask):
    """Install only the pure-Python SlideRule client into plugin storage."""

    def __init__(self):
        super().__init__(
            "Install ICESat-2 download support",
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
            logs_directory().mkdir(parents=True, exist_ok=True)

            base_python = qgis_base_python()
            self.setProgress(5)

            # Confirm pip without upgrading it or changing QGIS packages.
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
                    prefix="sliderule_install_",
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
                    "--no-deps",
                    "--upgrade",
                    "--target",
                    str(temporary_target),
                    f"sliderule=={SLIDERULE_VERSION}",
                ],
                environment=environment,
            )

            self.setProgress(75)

            # Verify the downloaded package in a separate Python process.
            probe_code = (
                "import sys; "
                f"sys.path.insert(0, {str(temporary_target)!r}); "
                "import sliderule; "
                "print(getattr(sliderule, '__version__', 'unknown'))"
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
                else SLIDERULE_VERSION
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

        except Exception as error:
            self.error_message = f"{type(error).__name__}: {error}"
            self.error_traceback = traceback.format_exc()
            return False

        finally:
            if temporary_target is not None and temporary_target.exists():
                shutil.rmtree(temporary_target, ignore_errors=True)

            if self._process is not None:
                try:
                    self._process.terminate()
                except Exception:  # nosec B110
                    pass
                self._process = None

    def cancel(self) -> None:
        if self._process is not None:
            try:
                self._process.terminate()
            except Exception:  # nosec B110
                pass

        super().cancel()
