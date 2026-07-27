"""Lightweight, dependency-free SystemVerilog project intelligence.

This is deliberately not a complete language server.  It provides the high
value beginner features needed by the local FPGA IDE: module/port/instance
outlines, symbol navigation, references, completion words, instance generation,
and actionable project checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Iterable


HDL_SUFFIXES = {".v", ".sv", ".vh", ".svh"}

SYSTEMVERILOG_KEYWORDS = (
    "always_comb", "always_ff", "always_latch", "assign", "begin", "case",
    "default", "else", "end", "endcase", "endfunction", "endgenerate",
    "endmodule", "endtask", "for", "function", "generate", "genvar", "if",
    "initial", "inout", "input", "integer", "localparam", "logic", "module",
    "negedge", "output", "parameter", "posedge", "reg", "repeat", "signed",
    "task", "typedef", "unique", "unsigned", "wire",
)


@dataclass(frozen=True)
class PortSymbol:
    name: str
    direction: str
    width: str
    line: int


@dataclass(frozen=True)
class InstanceSymbol:
    name: str
    module_type: str
    line: int


@dataclass(frozen=True)
class SignalSymbol:
    name: str
    kind: str
    width: str
    line: int


@dataclass
class ModuleSymbol:
    name: str
    path: Path
    line: int
    end_line: int
    ports: list[PortSymbol] = field(default_factory=list)
    instances: list[InstanceSymbol] = field(default_factory=list)
    signals: list[SignalSymbol] = field(default_factory=list)


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    message: str
    path: Path | None = None
    line: int = 1
    suggestion: str = ""


@dataclass(frozen=True)
class SymbolLocation:
    path: Path
    line: int
    column: int
    preview: str
    kind: str = "reference"


@dataclass
class ProjectIndex:
    project_root: Path
    top_name: str
    modules: dict[str, ModuleSymbol]
    diagnostics: list[Diagnostic]
    hdl_files: list[Path]

    @property
    def completions(self) -> list[str]:
        words = set(SYSTEMVERILOG_KEYWORDS)
        words.update(self.modules)
        for module in self.modules.values():
            words.update(port.name for port in module.ports)
            words.update(instance.name for instance in module.instances)
            words.update(signal.name for signal in module.signals)
        return sorted(words, key=str.lower)

    def definition(self, word: str, current_path: Path | None = None) -> tuple[Path, int] | None:
        module = self.modules.get(word)
        if module:
            return module.path, module.line
        search_modules = list(self.modules.values())
        if current_path is not None:
            resolved = current_path.resolve()
            search_modules.sort(key=lambda item: item.path.resolve() != resolved)
        for symbol_module in search_modules:
            for port in symbol_module.ports:
                if port.name == word:
                    return symbol_module.path, port.line
            for signal in symbol_module.signals:
                if signal.name == word:
                    return symbol_module.path, signal.line
            for instance in symbol_module.instances:
                if instance.name == word:
                    return symbol_module.path, instance.line
        return None

    def references(self, word: str) -> list[SymbolLocation]:
        """Find exact project-local identifier references with useful previews."""
        if not re.fullmatch(r"[A-Za-z_]\w*", word):
            return []
        pattern = re.compile(rf"\b{re.escape(word)}\b")
        locations: list[SymbolLocation] = []
        for path in self.hdl_files:
            text = _read_text(path)
            clean = _strip_comments(text)
            lines = text.splitlines()
            for match in pattern.finditer(clean):
                line = _line_number(clean, match.start())
                line_start = clean.rfind("\n", 0, match.start()) + 1
                column = match.start() - line_start + 1
                preview = lines[line - 1].strip() if 0 < line <= len(lines) else word
                kind = "definition" if self.definition(word, path) == (path, line) else "reference"
                locations.append(SymbolLocation(path, line, column, preview, kind))
        return locations

    def module_instantiation(self, module_name: str, instance_name: str | None = None) -> str:
        """Generate a readable named-port module instance from indexed ports."""
        module = self.modules.get(module_name)
        if module is None:
            raise KeyError(f"Unknown project module: {module_name}")
        name = instance_name or f"u_{module_name}"
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError(f"Invalid HDL instance name: {name}")
        if not module.ports:
            return f"{module_name} {name} ();"
        width = max(len(port.name) for port in module.ports)
        connections = ",\n".join(
            f"    .{port.name:<{width}} ({port.name})" for port in module.ports
        )
        return f"{module_name} {name} (\n{connections}\n);"


MODULE_RE = re.compile(r"(?m)^\s*module\s+([A-Za-z_]\w*)\b")
ENDMODULE_RE = re.compile(r"(?m)^\s*endmodule\b")
PORT_RE = re.compile(
    r"\b(?P<direction>input|output|inout)\b\s*"
    r"(?:(?:wire|logic|reg|signed|unsigned)\s+)*"
    r"(?P<width>\[[^\]]+\]\s*)?"
    r"(?P<names>[A-Za-z_]\w*(?:\s*,\s*(?!(?:input|output|inout)\b)[A-Za-z_]\w*)*)",
    re.MULTILINE,
)
INSTANCE_RE = re.compile(
    r"(?m)^\s*(?P<type>[A-Za-z_]\w*)\s*"
    r"(?:#\s*\((?:[^()]|\([^()]*\))*\)\s*)?"
    r"(?P<name>[A-Za-z_]\w*)\s*\("
)
SIGNAL_RE = re.compile(
    r"\b(?P<kind>logic|wire|reg|integer|genvar|parameter|localparam)\b\s*"
    r"(?:(?:signed|unsigned)\s+)?"
    r"(?P<width>\[[^\]]+\]\s*)?"
    r"(?P<names>[A-Za-z_]\w*(?:\s*=\s*[^,;]+)?(?:\s*,\s*[A-Za-z_]\w*(?:\s*=\s*[^,;]+)?)*)\s*;",
    re.MULTILINE,
)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _strip_comments(text: str) -> str:
    """Remove comments while preserving offsets and line numbers."""

    def block_replacement(match: re.Match[str]) -> str:
        value = match.group(0)
        return "".join("\n" if char == "\n" else " " for char in value)

    text = re.sub(r"/\*.*?\*/", block_replacement, text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", lambda match: " " * len(match.group(0)), text)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _hdl_files(project_root: Path) -> list[Path]:
    rtl = project_root / "rtl"
    if not rtl.is_dir():
        return []
    return sorted(
        (path for path in rtl.rglob("*") if path.is_file() and path.suffix.lower() in HDL_SUFFIXES),
        key=lambda path: str(path).lower(),
    )


def _configured_top(project_root: Path) -> str:
    config = project_root / "fpga.config.psd1"
    if not config.exists():
        return "top"
    match = re.search(r"(?m)^\s*Top\s*=\s*['\"]([A-Za-z_]\w*)['\"]", _read_text(config))
    return match.group(1) if match else "top"


def _constraint_file(project_root: Path) -> Path:
    config = project_root / "fpga.config.psd1"
    relative = "constraints/primer20k_dock.cst"
    if config.exists():
        match = re.search(r"(?m)^\s*Constraint\s*=\s*['\"]([^'\"]+)['\"]", _read_text(config))
        if match:
            relative = match.group(1)
    return project_root / Path(relative.replace("\\", "/"))


def _parse_modules(path: Path, text: str) -> list[ModuleSymbol]:
    clean = _strip_comments(text)
    modules: list[ModuleSymbol] = []
    for match in MODULE_RE.finditer(clean):
        end_match = ENDMODULE_RE.search(clean, match.end())
        end_offset = end_match.end() if end_match else len(clean)
        region = clean[match.start():end_offset]
        # Ports belong to the module header only. Scanning the entire module
        # incorrectly treats function/task inputs as physical top-level pins.
        header_end = region.find(");")
        header_region = region[:header_end + 2] if header_end >= 0 else region
        module_line = _line_number(clean, match.start())
        ports: list[PortSymbol] = []
        seen_ports: set[str] = set()
        for port_match in PORT_RE.finditer(header_region):
            for name in re.split(r"\s*,\s*", port_match.group("names")):
                if name and name not in seen_ports:
                    seen_ports.add(name)
                    ports.append(
                        PortSymbol(
                            name=name,
                            direction=port_match.group("direction"),
                            width=(port_match.group("width") or "").strip(),
                            line=module_line + _line_number(region, port_match.start()) - 1,
                        )
                    )
        modules.append(
            ModuleSymbol(
                name=match.group(1),
                path=path,
                line=module_line,
                end_line=_line_number(clean, end_offset),
                ports=ports,
            )
        )
    return modules


def _module_region(path: Path, module: ModuleSymbol) -> str:
    lines = _strip_comments(_read_text(path)).splitlines(keepends=True)
    return "".join(lines[module.line - 1:module.end_line])


def _constraint_ports(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ports = set(re.findall(r'(?m)^\s*IO_LOC\s+"([^"]+)"', _read_text(path)))
    return {re.sub(r"\[.*$", "", port) for port in ports}


def _constraint_io_standards(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ports = set(re.findall(r'(?m)^\s*IO_PORT\s+"([^"]+)"', _read_text(path)))
    return {re.sub(r"\[.*$", "", port) for port in ports}


def _duplicate_physical_pins(path: Path) -> list[tuple[str, str, str, int]]:
    if not path.exists():
        return []
    text = _read_text(path)
    seen: dict[str, tuple[str, int]] = {}
    duplicates: list[tuple[str, str, str, int]] = []
    for match in re.finditer(r'(?m)^\s*IO_LOC\s+"([^"]+)"\s+([A-Za-z0-9_]+)', text):
        port, pin = match.group(1), match.group(2).upper()
        if pin in seen and seen[pin][0] != port:
            duplicates.append((pin, seen[pin][0], port, _line_number(text, match.start())))
        else:
            seen[pin] = (port, _line_number(text, match.start()))
    return duplicates


def _relative(path: Path | None, root: Path) -> str:
    if path is None:
        return "project"
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def scan_project(project_root: Path | str) -> ProjectIndex:
    root = Path(project_root).resolve()
    files = _hdl_files(root)
    top_name = _configured_top(root)
    diagnostics: list[Diagnostic] = []
    modules: dict[str, ModuleSymbol] = {}

    if not files:
        diagnostics.append(
            Diagnostic("error", "PRJ001", "No Verilog/SystemVerilog files were found under rtl/.", root / "rtl")
        )

    texts: dict[Path, str] = {}
    for path in files:
        text = _read_text(path)
        texts[path] = text
        parsed = _parse_modules(path, text)
        if not parsed:
            diagnostics.append(
                Diagnostic("warning", "HDL001", "No module declaration was found in this HDL file.", path)
            )
        for module in parsed:
            if module.name in modules:
                previous = modules[module.name]
                diagnostics.append(
                    Diagnostic(
                        "error", "HDL002", f"Module '{module.name}' is declared more than once.", path, module.line,
                        f"First declaration: {_relative(previous.path, root)}:{previous.line}",
                    )
                )
            else:
                modules[module.name] = module

    # Resolve only project-local module instances; vendor primitives remain out
    # of the beginner outline instead of being reported as missing modules.
    for module in modules.values():
        region = _module_region(module.path, module)
        for match in INSTANCE_RE.finditer(region):
            module_type = match.group("type")
            if module_type in modules and module_type != module.name:
                module.instances.append(
                    InstanceSymbol(
                        name=match.group("name"),
                        module_type=module_type,
                        line=module.line + _line_number(region, match.start()) - 1,
                    )
                )
        port_names = {port.name for port in module.ports}
        seen_signals: set[str] = set()
        for signal_match in SIGNAL_RE.finditer(region):
            for declaration in re.split(r"\s*,\s*", signal_match.group("names")):
                name = declaration.split("=", 1)[0].strip()
                if name and name not in port_names and name not in seen_signals:
                    seen_signals.add(name)
                    module.signals.append(
                        SignalSymbol(
                            name=name,
                            kind=signal_match.group("kind"),
                            width=(signal_match.group("width") or "").strip(),
                            line=module.line + _line_number(region, signal_match.start()) - 1,
                        )
                    )

    top = modules.get(top_name)
    if modules and top is None:
        diagnostics.append(
            Diagnostic(
                "error", "PRJ002", f"Configured top module '{top_name}' was not found.", root / "fpga.config.psd1",
                suggestion="Change Top in fpga.config.psd1 or add the matching module.",
            )
        )

    constraint_path = _constraint_file(root)
    if not constraint_path.exists():
        diagnostics.append(
            Diagnostic("error", "PIN001", "Configured constraint file does not exist.", constraint_path)
        )
    elif top:
        constrained = _constraint_ports(constraint_path)
        standardized = _constraint_io_standards(constraint_path)
        for port in top.ports:
            if port.name not in constrained:
                diagnostics.append(
                    Diagnostic(
                        "error", "PIN002", f"Top-level port '{port.name}' has no IO_LOC constraint.",
                        top.path, port.line,
                        "Add the correct physical pin and voltage standard; do not guess board pins.",
                    )
                )
            elif port.name not in standardized:
                diagnostics.append(
                    Diagnostic(
                        "warning", "PIN003", f"Top-level port '{port.name}' has no IO_PORT electrical standard.",
                        constraint_path, 1,
                        "Add the board-correct IO_TYPE and other electrical properties; never guess bank voltage.",
                    )
                )
        for pin, first_port, second_port, line in _duplicate_physical_pins(constraint_path):
            diagnostics.append(
                Diagnostic(
                    "error", "PIN004", f"Physical pin {pin} is assigned to both '{first_port}' and '{second_port}'.",
                    constraint_path, line, "Give every top-level signal a unique board pin.",
                )
            )

    referenced_modules = {
        instance.module_type
        for module in modules.values()
        for instance in module.instances
    }
    for module in modules.values():
        if module.name != top_name and module.name not in referenced_modules:
            diagnostics.append(
                Diagnostic(
                    "info", "ARCH001", f"Module '{module.name}' is not instantiated by another project module.",
                    module.path, module.line,
                    "Instantiate it from the intended parent or remove it from synthesizable rtl/ sources.",
                )
            )

    dependency_graph = {
        name: {instance.module_type for instance in module.instances}
        for name, module in modules.items()
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module_name: str, trail: list[str]) -> None:
        if module_name in visiting:
            cycle = trail[trail.index(module_name):] + [module_name]
            module = modules[module_name]
            diagnostics.append(
                Diagnostic(
                    "error", "ARCH002", "Recursive module cycle: " + " → ".join(cycle),
                    module.path, module.line, "Hardware module hierarchy must not contain recursive instantiation.",
                )
            )
            return
        if module_name in visited:
            return
        visiting.add(module_name)
        for child in dependency_graph.get(module_name, set()):
            visit(child, trail + [child])
        visiting.remove(module_name)
        visited.add(module_name)

    for module_name in modules:
        visit(module_name, [module_name])

    testbench = root / "sim" / "tb_top.sv"
    if not testbench.exists():
        diagnostics.append(
            Diagnostic("warning", "SIM001", "sim/tb_top.sv is missing.", testbench,
                       suggestion="Add a self-checking tb_top testbench before hardware upload.")
        )
    else:
        tb_text = _read_text(testbench)
        if "$dumpfile" not in tb_text or "$dumpvars" not in tb_text:
            diagnostics.append(
                Diagnostic("warning", "SIM002", "The testbench does not generate a waveform dump.", testbench,
                           suggestion='Add $dumpfile("build/waves.vcd") and $dumpvars(...).')
            )
        if "$fatal" not in tb_text and "$error" not in tb_text:
            diagnostics.append(
                Diagnostic("info", "SIM003", "The testbench may not be self-checking.", testbench,
                           suggestion="Use $fatal or $error when expected behavior is violated.")
            )

    for path, text in texts.items():
        clean = _strip_comments(text)
        if "`default_nettype none" not in text:
            diagnostics.append(
                Diagnostic("info", "STYLE001", "Consider using `default_nettype none to catch mistyped nets.", path)
            )
        delay = re.search(r"(?<![A-Za-z0-9_])#\s*\d", clean)
        if delay:
            diagnostics.append(
                Diagnostic("warning", "SYN001", "Delay syntax was found in synthesizable RTL.", path,
                           _line_number(clean, delay.start()), "Keep # delays in sim/ testbenches only.")
            )
        for clock_match in re.finditer(r"always(?:_ff)?\s*@?\s*\(\s*posedge\s+([A-Za-z_]\w*)", clean):
            clock_name = clock_match.group(1).lower()
            if "clk" not in clock_name and "clock" not in clock_name:
                diagnostics.append(
                    Diagnostic(
                        "warning", "CDC001", f"'{clock_match.group(1)}' is used as a clock but is not named like one.",
                        path, _line_number(clean, clock_match.start()),
                        "Prefer one real clock plus clock-enable pulses; document intentional clock domains.",
                    )
                )
        for todo in re.finditer(r"(?i)\b(?:TODO|FIXME)\b", text):
            diagnostics.append(
                Diagnostic("info", "NOTE001", "Unfinished TODO/FIXME marker.", path, _line_number(text, todo.start()))
            )
        for case_match in re.finditer(r"\bcase(?:x|z)?\s*\([^)]*\)(.*?)\bendcase\b", clean, re.DOTALL):
            if not re.search(r"\bdefault\s*:", case_match.group(1)):
                diagnostics.append(
                    Diagnostic(
                        "warning", "RTL001", "Case statement has no default branch.", path,
                        _line_number(clean, case_match.start()),
                        "Add an explicit default branch so unexpected states cannot infer unintended behavior.",
                    )
                )

    rank = {"error": 0, "warning": 1, "info": 2}
    diagnostics.sort(key=lambda item: (rank.get(item.severity, 3), _relative(item.path, root), item.line, item.code))
    return ProjectIndex(root, top_name, modules, diagnostics, files)


def matching_completions(index: ProjectIndex, prefix: str, extra_words: Iterable[str] = ()) -> list[str]:
    words = set(index.completions)
    words.update(extra_words)
    prefix_lower = prefix.lower()
    return sorted(
        (word for word in words if word.lower().startswith(prefix_lower) and word != prefix),
        key=lambda word: (not word.lower().startswith(prefix_lower), word.lower()),
    )
