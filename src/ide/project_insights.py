"""Build telemetry and workflow-readiness helpers for the desktop IDE."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import re

from ide.hdl_intelligence import ProjectIndex


@dataclass(frozen=True)
class ResourceMetric:
    name: str
    used: int
    available: int

    @property
    def percent(self) -> float:
        return (100.0 * self.used / self.available) if self.available else 0.0


@dataclass
class ProjectInsights:
    score: int
    grade: str
    summary: str
    achieved_mhz: float | None = None
    target_mhz: float | None = None
    resources: list[ResourceMetric] = field(default_factory=list)
    bitstream_bytes: int | None = None
    waveform_bytes: int | None = None
    build_time: datetime | None = None


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _configured_clock(project_root: Path) -> float | None:
    config = project_root / "fpga.config.psd1"
    if not config.exists():
        return None
    match = re.search(r"\bClockMHz\s*=\s*([0-9.]+)", config.read_text(encoding="utf-8", errors="replace"))
    return float(match.group(1)) if match else None


def load_project_insights(project_root: Path | str, index: ProjectIndex) -> ProjectInsights:
    root = Path(project_root).resolve()
    errors = sum(item.severity == "error" for item in index.diagnostics)
    warnings = sum(item.severity == "warning" for item in index.diagnostics)
    info = sum(item.severity == "info" for item in index.diagnostics)
    score = max(0, min(100, 100 - errors * 24 - warnings * 7 - min(info, 5) * 2))
    grade = "Excellent" if score >= 95 else "Healthy" if score >= 80 else "Needs review" if score >= 60 else "Blocked"
    summary = "Ready for the verified workflow" if not errors else f"Resolve {errors} blocking issue(s)"

    timing_path = root / "build" / "timing.json"
    timing = _read_json(timing_path)
    fmax_values = timing.get("fmax", {}) if isinstance(timing.get("fmax", {}), dict) else {}
    achieved_values = [
        value.get("achieved") for value in fmax_values.values()
        if isinstance(value, dict) and isinstance(value.get("achieved"), (int, float))
    ]
    achieved = min(achieved_values) if achieved_values else None
    target = _configured_clock(root)
    utilization = timing.get("utilization", {}) if isinstance(timing.get("utilization", {}), dict) else {}
    resources: list[ResourceMetric] = []
    for name in ("LUT4", "DFF", "IOB", "BSRAM", "MULT18X18", "rPLL"):
        value = utilization.get(name)
        if isinstance(value, dict):
            used, available = value.get("used"), value.get("available")
            if isinstance(used, int) and isinstance(available, int):
                resources.append(ResourceMetric(name, used, available))

    bitstream = root / "build" / "top.fs"
    waveform = root / "build" / "waves.vcd"
    try:
        build_time = datetime.fromtimestamp(timing_path.stat().st_mtime) if timing_path.exists() else None
    except OSError:
        build_time = None
    return ProjectInsights(
        score=score,
        grade=grade,
        summary=summary,
        achieved_mhz=achieved,
        target_mhz=target,
        resources=resources,
        bitstream_bytes=bitstream.stat().st_size if bitstream.exists() else None,
        waveform_bytes=waveform.stat().st_size if waveform.exists() else None,
        build_time=build_time,
    )


def workflow_steps(project_root: Path | str, index: ProjectIndex, session_passes: set[str] | None = None) -> list[tuple[str, str, str]]:
    root = Path(project_root).resolve()
    passed = session_passes or set()
    clean = not any(item.severity == "error" for item in index.diagnostics)
    return [
        ("Smart checks", "ready" if clean else "blocked", "No blocking project diagnostics" if clean else "Fix red diagnostics"),
        ("Simulation", "ready" if "sim" in passed or (root / "build" / "waves.vcd").exists() else "next", "Self-checking testbench + waveform"),
        ("Lint", "ready" if "lint" in passed or "debug" in passed else "next", "Run Verilator before hardware"),
        ("Bitstream", "ready" if (root / "build" / "top.fs").exists() else "next", "Synthesis, place/route and pack"),
        ("JTAG", "ready" if "detect" in passed else "next", "Detect the attached Tang Primer 20K"),
        ("SRAM test", "ready" if "upload" in passed else "next", "Validate volatile hardware behavior"),
        ("Persistent flash", "ready" if "flash" in passed else "optional", "Only after SRAM testing succeeds"),
    ]
