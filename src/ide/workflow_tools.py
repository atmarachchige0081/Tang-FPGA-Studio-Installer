"""Pure workflow helpers for diagnostics and the verification center."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ToolDiagnostic:
    severity: str
    message: str
    path: Path | None = None
    line: int = 1
    column: int = 1


@dataclass(frozen=True)
class VerificationAsset:
    path: Path
    kind: str
    top_module: str = "tb_top"


_LOCATION_PATTERNS = (
    re.compile(
        r"^%(?P<severity>Error|Warning)(?:-[A-Z0-9]+)?:\s+"
        r"(?P<path>.+?):(?P<line>\d+):(?P<column>\d+):\s*(?P<message>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<path>.+?):(?P<line>\d+)(?::(?P<column>\d+))?:\s*"
        r"(?:(?P<severity>error|warning|fatal)\s*:\s*)?(?P<message>.+)$",
        re.IGNORECASE,
    ),
)


def parse_tool_diagnostic(line: str, project_root: Path | str) -> ToolDiagnostic | None:
    """Recognize common Verilator, Icarus, Yosys, and nextpnr locations."""
    value = line.strip()
    root = Path(project_root).resolve()
    for pattern in _LOCATION_PATTERNS:
        match = pattern.match(value)
        if not match:
            continue
        groups = match.groupdict()
        path_value = groups.get("path", "").strip().strip('"')
        candidate = Path(path_value.replace("/", "\\")) if "\\" in str(root) else Path(path_value)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            return None
        severity_value = (groups.get("severity") or "error").lower()
        severity = "error" if severity_value in {"error", "fatal"} else "warning"
        return ToolDiagnostic(
            severity,
            groups.get("message", value).strip(),
            resolved,
            int(groups.get("line") or 1),
            int(groups.get("column") or 1),
        )
    return None


def discover_verification_assets(project_root: Path | str) -> tuple[list[VerificationAsset], list[VerificationAsset]]:
    """Discover testbenches and GTKWave save files without assuming one fixed name."""
    root = Path(project_root).resolve()
    sim = root / "sim"
    if not sim.is_dir():
        return [], []
    benches: list[VerificationAsset] = []
    layouts: list[VerificationAsset] = []
    for path in sorted(sim.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".v", ".sv"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            matches = re.findall(r"(?m)^\s*module\s+([A-Za-z_]\w*)\b", text)
            top = next((name for name in matches if name.startswith("tb_")), matches[0] if matches else "tb_top")
            benches.append(VerificationAsset(path, "testbench", top))
        elif path.suffix.lower() == ".gtkw":
            layouts.append(VerificationAsset(path, "wave-layout"))
    return benches, layouts


def summarize_verification_output(output: str, return_code: int) -> tuple[str, int, int]:
    """Return a friendly state plus visible PASS/FAIL assertion counts."""
    passed = len(re.findall(r"(?im)^\s*(?:PASS|PASSED)\s*:", output))
    failed = len(re.findall(r"(?im)^\s*(?:FAIL|FAILED|FATAL|ERROR)\s*:", output))
    if return_code != 0 or failed:
        state = "Failed"
    elif passed:
        state = "Passed"
    else:
        state = "Completed"
    return state, passed, failed
