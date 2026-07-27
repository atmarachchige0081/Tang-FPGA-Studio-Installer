"""Installed entry point for Tang Primer FPGA Studio.

The frozen application is read-only under Program Files. This launcher creates
and maintains a separate, writable HDL workspace in the user's Documents
folder before handing control to the existing IDE.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from build_version import APP_VERSION


APP_NAME = "Tang Primer FPGA Studio"
WORKSPACE_FOLDER = "Tang Primer FPGA Studio"
STATE_FOLDER = "TangPrimerFPGAStudio"

MANAGED_FILES = {
    Path("fpga.ps1"),
    Path("scripts/setup-toolchain.ps1"),
    Path("INSTALL.md"),
    Path("LICENSE"),
}


def bundle_root() -> Path:
    """Return PyInstaller's bundle folder or this source tree while developing."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def workspace_template() -> Path:
    packaged = bundle_root() / "workspace-template"
    if packaged.is_dir():
        return packaged
    development = Path(__file__).resolve().parents[1] / "payload" / "workspace"
    if development.is_dir():
        return development
    raise RuntimeError("The packaged FPGA workspace template is missing.")


def windows_documents_folder() -> Path:
    """Resolve the Windows Documents known folder, including OneDrive redirection."""
    if os.name == "nt":
        try:
            import winreg

            key_name = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
                configured, _ = winreg.QueryValueEx(key, "Personal")
            return Path(os.path.expandvars(configured)).resolve()
        except (OSError, ValueError):
            pass
    return (Path.home() / "Documents").resolve()


def default_workspace() -> Path:
    override = os.environ.get("TANG_FPGA_WORKSPACE")
    if override:
        return Path(override).expanduser().resolve()
    return windows_documents_folder() / WORKSPACE_FOLDER


def state_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"
    return (base / STATE_FOLDER).resolve()


def copy_workspace_file(source: Path, destination: Path, relative: Path) -> None:
    if destination.exists() and relative not in MANAGED_FILES:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".installing")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def ensure_workspace(target: Path) -> Path:
    """Install missing examples while preserving every user-created project file."""
    template = workspace_template()
    target.mkdir(parents=True, exist_ok=True)

    for source in template.rglob("*"):
        relative = source.relative_to(template)
        destination = target / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            copy_workspace_file(source, destination, relative)

    marker = target / ".fpga-studio-install.json"
    marker_payload = {
        "application": APP_NAME,
        "version": APP_VERSION,
        "workspace": str(target),
    }
    temporary_marker = marker.with_suffix(".tmp")
    temporary_marker.write_text(json.dumps(marker_payload, indent=2), encoding="utf-8")
    os.replace(temporary_marker, marker)
    return target


def install_toolchain(workspace: Path) -> int:
    script = workspace / "scripts" / "setup-toolchain.ps1"
    if not script.is_file():
        raise RuntimeError(f"Dependency installer is missing: {script}")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-SkipVsCodeExtension",
    ]
    completed = subprocess.run(command, cwd=workspace, check=False)
    return completed.returncode


def run_ide(workspace: Path, ide_arguments: list[str]) -> int:
    os.environ["TANG_FPGA_WORKSPACE"] = str(workspace)
    runtime_state = state_root()
    runtime_state.mkdir(parents=True, exist_ok=True)

    from ide import fpga_ide

    # The original repository remains usable from source. Only the installed
    # launcher redirects its globals to writable per-user locations.
    fpga_ide.WORKSPACE_ROOT = workspace
    fpga_ide.STATE_ROOT = runtime_state
    fpga_ide.LOG_PATH = runtime_state / "logs" / "studio.log"
    fpga_ide.SETTINGS_PATH = runtime_state / "settings.json"
    fpga_ide.APP_VERSION = APP_VERSION

    sys.argv = [sys.argv[0], *ide_arguments]
    return fpga_ide.main()


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", metavar="PATH")
    parser.add_argument("--prepare-workspace", action="store_true")
    parser.add_argument("--install-toolchain", action="store_true")
    parser.add_argument("--print-workspace", action="store_true")
    launcher_args, ide_args = parser.parse_known_args()

    workspace = Path(launcher_args.workspace).resolve() if launcher_args.workspace else default_workspace()
    ensure_workspace(workspace)

    if launcher_args.print_workspace:
        print(workspace)
    if launcher_args.install_toolchain:
        return install_toolchain(workspace)
    if launcher_args.prepare_workspace:
        return 0
    return run_ide(workspace, ide_args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        if os.name == "nt":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    None,
                    f"{error}\n\nReinstall the application or review the diagnostic log.",
                    f"{APP_NAME} could not start",
                    0x10,
                )
            except (AttributeError, OSError):
                pass
        raise
