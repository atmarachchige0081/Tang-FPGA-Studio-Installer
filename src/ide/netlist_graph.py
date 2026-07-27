"""Parse synthesized Yosys JSON into a compact, viewer-friendly graph."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import json
from pathlib import Path
import re


MAX_NETLIST_CELLS = 50_000


class NetlistError(ValueError):
    """A readable synthesized-netlist loading failure."""


@dataclass(frozen=True)
class SourceLocation:
    path: Path
    line: int


@dataclass(frozen=True)
class NetlistPort:
    name: str
    direction: str
    bits: tuple[int | str, ...]


@dataclass(frozen=True)
class NetlistCell:
    name: str
    cell_type: str
    category: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    source: SourceLocation | None = None


@dataclass(frozen=True)
class NetConnection:
    source: str
    target: str
    nets: tuple[str, ...]


@dataclass
class NetlistGraph:
    path: Path
    creator: str
    module_name: str
    ports: dict[str, NetlistPort]
    cells: dict[str, NetlistCell]
    connections: list[NetConnection]
    _incoming: dict[str, list[NetConnection]] = field(default_factory=dict, repr=False)
    _outgoing: dict[str, list[NetConnection]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        incoming: dict[str, list[NetConnection]] = defaultdict(list)
        outgoing: dict[str, list[NetConnection]] = defaultdict(list)
        for connection in self.connections:
            outgoing[connection.source].append(connection)
            incoming[connection.target].append(connection)
        self._incoming = dict(incoming)
        self._outgoing = dict(outgoing)

    @property
    def category_counts(self) -> Counter[str]:
        return Counter(cell.category for cell in self.cells.values())

    @property
    def type_counts(self) -> Counter[str]:
        return Counter(cell.cell_type for cell in self.cells.values())

    def incoming(self, name: str) -> list[NetConnection]:
        return self._incoming.get(name, [])

    def outgoing(self, name: str) -> list[NetConnection]:
        return self._outgoing.get(name, [])


def cell_category(cell_type: str) -> str:
    value = cell_type.upper().lstrip("$")
    if any(marker in value for marker in ("IBUF", "OBUF", "IOBUF", "IOLOGIC")):
        return "I/O"
    if any(marker in value for marker in ("DFF", "LATCH", "DLATCH")):
        return "Sequential"
    if any(marker in value for marker in ("RAM", "MEM", "FIFO", "ROM")):
        return "Memory"
    if any(marker in value for marker in ("PLL", "CLK", "GSR", "DCS", "DQCE")):
        return "Clock/reset"
    if any(marker in value for marker in ("LUT", "MUX", "ALU", "ADD", "SUB", "MUL", "AND", "OR", "XOR", "NOT")):
        return "Logic"
    if value in {"VCC", "GND"}:
        return "Constants"
    return "Other"


def _truthy_attribute(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip("0 ") not in {"", "false", "False"}
    return False


def _source_location(value: object, project_root: Path) -> SourceLocation | None:
    if not isinstance(value, str):
        return None
    for entry in value.split("|"):
        match = re.match(r"^(?P<path>.+\.(?:sv|svh|v|vh)):(?P<line>\d+)", entry, re.IGNORECASE)
        if not match:
            continue
        candidate = Path(match.group("path").replace("\\", "/"))
        if not candidate.is_absolute():
            candidate = project_root / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(project_root)
        except (OSError, ValueError):
            continue
        return SourceLocation(resolved, int(match.group("line")))
    return None


def _named_nets(module: dict[str, object]) -> dict[int, str]:
    result: dict[int, str] = {}
    netnames = module.get("netnames", {})
    if not isinstance(netnames, dict):
        return result
    for name, description in netnames.items():
        if not isinstance(description, dict):
            continue
        hidden = description.get("hide_name", 0)
        bits = description.get("bits", [])
        if not isinstance(bits, list):
            continue
        for bit in bits:
            if isinstance(bit, int) and (bit not in result or not hidden):
                result[bit] = str(name)
    return result


def load_yosys_netlist(
    path: Path | str, project_root: Path | str, top_name: str = "top",
) -> NetlistGraph:
    netlist_path = Path(path).resolve()
    root = Path(project_root).resolve()
    if not netlist_path.is_file():
        raise NetlistError("No synthesized netlist exists yet. Run Build first.")
    try:
        payload = json.loads(netlist_path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise NetlistError(f"The synthesized JSON netlist could not be read: {error}") from error
    modules = payload.get("modules") if isinstance(payload, dict) else None
    if not isinstance(modules, dict) or not modules:
        raise NetlistError("The Yosys JSON file contains no modules.")
    selected_name = top_name if top_name in modules else ""
    if not selected_name:
        selected_name = next(
            (
                name for name, module in modules.items()
                if isinstance(module, dict)
                and isinstance(module.get("attributes"), dict)
                and _truthy_attribute(module["attributes"].get("top"))
            ),
            "",
        )
    if not selected_name:
        raise NetlistError(f"Top module '{top_name}' was not found in the synthesized netlist.")
    module = modules[selected_name]
    if not isinstance(module, dict):
        raise NetlistError(f"Module '{selected_name}' has an invalid JSON representation.")

    raw_cells = module.get("cells", {})
    if not isinstance(raw_cells, dict):
        raw_cells = {}
    if len(raw_cells) > MAX_NETLIST_CELLS:
        raise NetlistError(
            f"This netlist has {len(raw_cells):,} cells; the interactive viewer limit is "
            f"{MAX_NETLIST_CELLS:,}. Use the JSON artifact for batch analysis."
        )

    ports: dict[str, NetlistPort] = {}
    raw_ports = module.get("ports", {})
    if isinstance(raw_ports, dict):
        for name, description in raw_ports.items():
            if not isinstance(description, dict):
                continue
            bits = description.get("bits", [])
            ports[str(name)] = NetlistPort(
                str(name), str(description.get("direction", "unknown")),
                tuple(bits if isinstance(bits, list) else []),
            )

    cells: dict[str, NetlistCell] = {}
    cell_connections: dict[str, dict[str, tuple[int | str, ...]]] = {}
    cell_directions: dict[str, dict[str, str]] = {}
    for name, description in raw_cells.items():
        if not isinstance(description, dict):
            continue
        directions_raw = description.get("port_directions", {})
        directions = {
            str(port): str(direction)
            for port, direction in directions_raw.items()
        } if isinstance(directions_raw, dict) else {}
        connections_raw = description.get("connections", {})
        connections = {
            str(port): tuple(bits if isinstance(bits, list) else [])
            for port, bits in connections_raw.items()
        } if isinstance(connections_raw, dict) else {}
        attributes = description.get("attributes", {})
        source = _source_location(attributes.get("src"), root) if isinstance(attributes, dict) else None
        cell_type = str(description.get("type", "unknown"))
        cells[str(name)] = NetlistCell(
            str(name), cell_type, cell_category(cell_type),
            tuple(sorted(port for port, direction in directions.items() if direction in {"input", "inout"})),
            tuple(sorted(port for port, direction in directions.items() if direction in {"output", "inout"})),
            source,
        )
        cell_connections[str(name)] = connections
        cell_directions[str(name)] = directions

    producers: dict[int, set[str]] = defaultdict(set)
    consumers: dict[int, set[str]] = defaultdict(set)
    for port in ports.values():
        endpoint = f"port:{port.name}"
        for bit in port.bits:
            if not isinstance(bit, int):
                continue
            if port.direction in {"input", "inout"}:
                producers[bit].add(endpoint)
            if port.direction in {"output", "inout"}:
                consumers[bit].add(endpoint)
    for cell_name, connections in cell_connections.items():
        directions = cell_directions[cell_name]
        for port_name, bits in connections.items():
            direction = directions.get(port_name, "input")
            for bit in bits:
                if not isinstance(bit, int):
                    continue
                if direction in {"output", "inout"}:
                    producers[bit].add(cell_name)
                if direction in {"input", "inout"}:
                    consumers[bit].add(cell_name)

    net_names = _named_nets(module)
    edge_nets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for bit, sources in producers.items():
        label = net_names.get(bit, f"net {bit}")
        for source in sources:
            for target in consumers.get(bit, set()):
                if source != target:
                    edge_nets[(source, target)].add(label)
    connections = [
        NetConnection(source, target, tuple(sorted(names)))
        for (source, target), names in sorted(edge_nets.items())
    ]
    return NetlistGraph(
        netlist_path, str(payload.get("creator", "Yosys")), selected_name,
        ports, cells, connections,
    )
