"""Safe project creation services used by the desktop project wizard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil


PROJECT_NAME_RE = re.compile(r"\d{2}_[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ProjectTemplate:
    key: str
    title: str
    description: str
    source: Path
    level: str = "Beginner"


class ProjectCreationError(ValueError):
    """An actionable project-wizard validation failure."""


def validate_project_name(name: str) -> str:
    """Validate and normalize the repository's sortable project folder format."""
    normalized = name.strip()
    if not PROJECT_NAME_RE.fullmatch(normalized):
        raise ProjectCreationError(
            "Use two digits, an underscore, and lowercase words, for example 04_uart_echo."
        )
    return normalized


def discover_templates(workspace_root: Path | str) -> list[ProjectTemplate]:
    """Return only complete, copyable templates in a stable beginner-first order."""
    root = Path(workspace_root).resolve()
    candidates = [
        ProjectTemplate(
            "starter", "Board I/O starter",
            "Buttons, LEDs, a 27 MHz counter, self-checking simulation, and waveform layout.",
            root / "projects" / "_template",
        ),
        ProjectTemplate(
            "uart", "UART terminal",
            "A tested 115200-baud greeting and echo design with a serial-terminal workflow.",
            root / "projects" / "03_uart_terminal",
            "Beginner +",
        ),
    ]
    return [item for item in candidates if _is_complete_template(item.source)]


def _is_complete_template(path: Path) -> bool:
    required = (
        "fpga.config.psd1", "rtl/top.sv", "rtl/files.f",
        "sim/tb_top.sv", "constraints/primer20k_dock.cst",
    )
    return path.is_dir() and all((path / item).is_file() for item in required)


def create_project(
    projects_root: Path | str,
    name: str,
    template: ProjectTemplate,
    *,
    display_name: str = "",
) -> Path:
    """Copy a verified template without permitting traversal or partial overwrites."""
    normalized = validate_project_name(name)
    root = Path(projects_root).resolve()
    if not _is_complete_template(template.source):
        raise ProjectCreationError(f"Template '{template.title}' is incomplete or unavailable.")
    target = (root / normalized).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ProjectCreationError("The project must stay inside the projects folder.") from error
    if target.exists():
        raise ProjectCreationError(f"A project named '{normalized}' already exists.")

    root.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(
            template.source,
            target,
            ignore=shutil.ignore_patterns("build", "obj_dir", "__pycache__", "*.pyc"),
        )
        title = display_name.strip()
        readme = target / "README.md"
        if title and readme.exists():
            content = readme.read_text(encoding="utf-8", errors="replace")
            content = re.sub(r"(?m)^# .+$", f"# {title}", content, count=1)
            readme.write_text(content, encoding="utf-8", newline="\n")
    except OSError as error:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        raise ProjectCreationError(f"Project creation failed: {error}") from error
    return target
