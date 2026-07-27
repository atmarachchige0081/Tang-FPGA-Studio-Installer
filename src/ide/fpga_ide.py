"""Tang Primer 20K beginner FPGA design workspace.

A dependency-free desktop front end for the repository's verified PowerShell
FPGA workflow.  The application intentionally runs only local processes and
opens only projects contained inside this repository.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from ide.hdl_intelligence import (  # noqa: E402
    Diagnostic,
    HDL_SUFFIXES,
    ProjectIndex,
    SYSTEMVERILOG_KEYWORDS,
    matching_completions,
    scan_project,
)
from ide.hdl_patterns import (  # noqa: E402
    CATEGORIES,
    DIFFICULTIES,
    HDLPattern,
    HDL_SNIPPETS,
    HDL_SNIPPET_ALIASES,
    PATTERNS,
    search_patterns,
)
from ide.netlist_graph import NetlistError, NetlistGraph, load_yosys_netlist  # noqa: E402
from ide.netlist_viewer import open_netlist_viewer  # noqa: E402
from ide.project_insights import load_project_insights, workflow_steps  # noqa: E402
from ide.project_wizard import (  # noqa: E402
    ProjectCreationError,
    create_project,
    discover_templates,
)
from ide.release_notes import (  # noqa: E402
    mark_release_notes_seen,
    notes_for_version,
    release_notes_pending,
)
from ide.serial_backend import (  # noqa: E402
    SerialConnection,
    encode_terminal_input,
    format_terminal_bytes,
    list_serial_ports,
    preferred_serial_port,
)
from ide.themes import (  # noqa: E402
    DEFAULT_THEME,
    HEX_COLOR,
    THEMES,
    contrast_ratio,
    normalize_theme,
    theme_colors,
    validate_themes,
)
from ide.workflow_tools import (  # noqa: E402
    ToolDiagnostic,
    discover_verification_assets,
    parse_tool_diagnostic,
    summarize_verification_output,
)


APP_NAME = "Tang Primer FPGA Studio"
APP_VERSION = "1.2.0"
STATE_ROOT = WORKSPACE_ROOT / ".fpga-studio"
LOG_PATH = STATE_ROOT / "logs" / "studio.log"
SETTINGS_PATH = STATE_ROOT / "settings.json"
LOGGER = logging.getLogger("fpga_studio")

COLORS = theme_colors(DEFAULT_THEME)

ICON_COLOR_TOKENS = {
    "chip": "cyan", "play": "green", "wave": "cyan", "lint": "yellow",
    "bug": "orange", "build": "blue", "upload": "green", "flash": "yellow",
    "target": "cyan", "doctor": "red", "search": "muted", "sparkle": "purple",
    "plus": "cyan", "save": "blue", "folder": "yellow", "file": "muted",
    "code": "purple", "refresh": "muted", "stop": "red", "terminal": "cyan",
    "dashboard": "green", "bulb": "yellow", "command": "purple", "close": "muted",
    "theme": "orange",
}

BACKGROUND_COLOR_TOKENS = (
    "bg", "header", "panel", "panel_alt", "panel_hover", "editor", "console",
    "border", "border_soft", "selection", "tooltip", "current_line",
    "accent", "accent_hover", "success_button", "success_hover",
    "danger_button", "danger_hover",
)
FOREGROUND_COLOR_TOKENS = (
    "text", "muted", "muted_2", "on_accent", "selection_text", "cursor", "accent_text",
    "blue", "green", "yellow", "red", "purple", "cyan", "orange",
    "editor_signal", "editor_comment", "editor_string",
)

EDITABLE_SUFFIXES = {
    ".v", ".sv", ".vh", ".svh", ".cst", ".psd1", ".ps1", ".md",
    ".txt", ".f", ".gtkw", ".json", ".ys",
}
IGNORED_TREE_NAMES = {".git", "__pycache__", ".pytest_cache", "obj_dir"}

def configure_runtime_logging() -> None:
    if LOGGER.handlers:
        return
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def load_user_settings() -> dict[str, object]:
    try:
        value = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_user_settings(value: dict[str, object]) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8", newline="\n")
        temporary.replace(SETTINGS_PATH)
    except OSError as error:
        LOGGER.warning("Unable to save settings: %s", error)


class IconFactory:
    """Small dependency-free vector-like icons rendered into Tk images."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self.cache: dict[tuple[str, str, int], tk.PhotoImage] = {}

    def get(self, name: str, color: str | None = None, size: int = 18) -> tk.PhotoImage:
        color = color or COLORS["text"]
        key = (name, color, size)
        if key in self.cache:
            return self.cache[key]
        image = tk.PhotoImage(master=self.root, width=size, height=size)
        scale = size / 18.0

        def point(x: float, y: float, shade: str = color) -> None:
            px, py = int(round(x * scale)), int(round(y * scale))
            if 0 <= px < size and 0 <= py < size:
                image.put(shade, (px, py))

        def line(x1: float, y1: float, x2: float, y2: float, width: int = 2, shade: str = color) -> None:
            dx, dy = x2 - x1, y2 - y1
            steps = max(1, int(max(abs(dx), abs(dy)) * scale * 1.5))
            for step in range(steps + 1):
                x = x1 + dx * step / steps
                y = y1 + dy * step / steps
                for offset in range(width):
                    point(x + offset / scale, y, shade)
                    if width > 1:
                        point(x, y + offset / scale, shade)

        def rect(x1: int, y1: int, x2: int, y2: int, fill: bool = False, shade: str = color) -> None:
            if fill:
                for y in range(y1, y2 + 1):
                    line(x1, y, x2, y, 1, shade)
            else:
                line(x1, y1, x2, y1, 1, shade)
                line(x2, y1, x2, y2, 1, shade)
                line(x2, y2, x1, y2, 1, shade)
                line(x1, y2, x1, y1, 1, shade)

        if name == "chip":
            rect(4, 4, 13, 13)
            rect(7, 7, 10, 10, True, COLORS["accent"])
            for value in (6, 9, 12):
                line(value, 2, value, 4, 1); line(value, 13, value, 15, 1)
                line(2, value, 4, value, 1); line(13, value, 15, value, 1)
        elif name == "play":
            for x in range(5, 13):
                half = min(x - 5, 12 - x)
                line(x, 7 - half, x, 10 + half, 1)
        elif name == "wave":
            for values in ((2, 10, 5, 10), (5, 10, 7, 5), (7, 5, 10, 13), (10, 13, 13, 7), (13, 7, 16, 7)):
                line(*values)
        elif name in {"check", "lint"}:
            line(3, 9, 7, 13); line(7, 13, 15, 4)
        elif name == "bug":
            rect(5, 5, 12, 13); line(7, 3, 8, 5); line(10, 3, 9, 5)
            for y in (7, 10, 13): line(2, y, 5, y); line(12, y, 15, y)
        elif name == "build":
            line(4, 3, 14, 13, 3); line(3, 4, 7, 2, 2); rect(11, 11, 15, 15, True)
        elif name == "upload":
            line(9, 3, 9, 12, 2); line(5, 7, 9, 3); line(9, 3, 13, 7); line(3, 14, 15, 14, 2)
        elif name == "flash":
            line(10, 2, 5, 10, 2); line(5, 10, 10, 9, 2); line(10, 9, 7, 16, 2); line(7, 16, 14, 7, 2)
        elif name == "target":
            for values in ((3, 6, 3, 12), (15, 6, 15, 12), (6, 3, 12, 3), (6, 15, 12, 15)):
                line(*values)
            rect(7, 7, 11, 11); point(9, 9, COLORS["green"])
        elif name == "doctor":
            line(2, 10, 5, 10); line(5, 10, 7, 5); line(7, 5, 10, 14); line(10, 14, 12, 8); line(12, 8, 16, 8)
        elif name == "search":
            rect(4, 4, 11, 11); line(11, 11, 16, 16, 2)
        elif name == "sparkle":
            line(9, 2, 9, 16); line(2, 9, 16, 9); line(5, 5, 13, 13); line(13, 5, 5, 13)
        elif name == "plus":
            line(9, 3, 9, 15, 2); line(3, 9, 15, 9, 2)
        elif name == "save":
            rect(3, 2, 15, 16); rect(6, 3, 12, 7); rect(6, 11, 12, 15)
        elif name == "folder":
            line(2, 5, 7, 5); line(7, 5, 9, 7); line(9, 7, 16, 7); rect(2, 7, 16, 15)
        elif name == "file":
            rect(4, 2, 14, 16); line(10, 2, 14, 6); line(10, 2, 10, 6); line(10, 6, 14, 6)
        elif name == "code":
            line(7, 4, 2, 9); line(2, 9, 7, 14); line(11, 4, 16, 9); line(16, 9, 11, 14)
        elif name == "refresh":
            line(4, 7, 7, 4); line(7, 4, 13, 5); line(13, 5, 15, 8); line(13, 3, 13, 6)
            line(14, 11, 11, 14); line(11, 14, 5, 13); line(5, 13, 3, 10); line(5, 15, 5, 12)
        elif name == "stop":
            rect(4, 4, 14, 14, True)
        elif name == "terminal":
            rect(2, 3, 16, 15); line(4, 6, 7, 9); line(7, 9, 4, 12); line(9, 12, 14, 12)
        elif name == "dashboard":
            rect(2, 10, 5, 15, True); rect(7, 6, 10, 15, True); rect(12, 2, 15, 15, True)
        elif name == "bulb":
            rect(6, 4, 12, 11); line(7, 13, 11, 13); line(8, 15, 10, 15)
        elif name == "theme":
            rect(7, 7, 11, 11, True)
            for values in ((9, 2, 9, 4), (9, 14, 9, 16), (2, 9, 4, 9), (14, 9, 16, 9),
                           (4, 4, 5, 5), (13, 13, 14, 14), (13, 5, 14, 4), (4, 14, 5, 13)):
                line(*values)
        elif name == "command":
            rect(2, 3, 16, 15); line(5, 7, 8, 10); line(8, 10, 5, 13); line(10, 13, 14, 13)
        elif name == "close":
            line(4, 4, 14, 14); line(14, 4, 4, 14)
        else:
            rect(4, 4, 14, 14)
        self.cache[key] = image
        return image


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        self.job: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self.job = self.widget.after(450, self._show)

    def _show(self) -> None:
        if self.window or not self.text:
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 7
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.window, text=self.text, bg=COLORS["tooltip"], fg=COLORS["on_accent"],
            padx=9, pady=5, font=("Segoe UI", 9), relief="solid", borderwidth=1,
        ).pack()

    def _hide(self, _event=None) -> None:
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.window:
            self.window.destroy()
            self.window = None


class LineNumberCanvas(tk.Canvas):
    def __init__(self, master: tk.Misc, text_widget: tk.Text, **kwargs):
        super().__init__(master, highlightthickness=0, width=52, **kwargs)
        self.text_widget = text_widget

    def redraw(self, *_args) -> None:
        self.delete("all")
        index = self.text_widget.index("@0,0")
        while True:
            line_info = self.text_widget.dlineinfo(index)
            if line_info is None:
                break
            y = line_info[1]
            line_number = str(index).split(".")[0]
            self.create_text(
                44, y, anchor="ne", text=line_number,
                fill=COLORS["muted"], font=("Consolas", 10),
            )
            index = self.text_widget.index(f"{index}+1line")


class FPGAStudio:
    def __init__(
        self, root: tk.Tk, initial_project: str | None = None,
        initial_theme: str | None = None,
    ):
        configure_runtime_logging()
        self.root = root
        self.settings = load_user_settings()
        requested_theme = initial_theme if initial_theme is not None else self.settings.get("theme")
        self.theme_name = normalize_theme(requested_theme)
        COLORS.clear()
        COLORS.update(theme_colors(self.theme_name))
        self.theme_var = tk.StringVar(master=root, value=self.theme_name)
        self.theme_button_text = tk.StringVar(master=root)
        self.theme_button_text.set("Light mode" if self.theme_name == "dark" else "Dark mode")
        self.release_notes_window: tk.Toplevel | None = None
        self.menus: list[tk.Menu] = []
        self.root.report_callback_exception = self._report_callback_exception
        self.root.title(f"{APP_NAME} — {APP_VERSION}")
        self.root.geometry("1560x940")
        self.root.minsize(1180, 740)
        self.root.configure(bg=COLORS["bg"])
        self.icon_factory, self.icons = self._create_icons()
        self.root.iconphoto(True, self.icons["chip"])

        self.current_project = WORKSPACE_ROOT
        self.current_file: Path | None = None
        self.current_index = ProjectIndex(WORKSPACE_ROOT, "top", {}, [], [])
        self.dirty = False
        self.highlight_job: str | None = None
        self.process: subprocess.Popen[str] | None = None
        self.process_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.runner_buttons: list[ttk.Button] = []
        self.tree_paths: dict[str, Path] = {}
        self.outline_locations: dict[str, tuple[Path, int]] = {}
        self.problem_items: dict[str, Diagnostic] = {}
        self.project_map: dict[str, Path] = {}
        self.open_files: list[Path] = []
        self.session_passes: set[str] = set()
        self.command_history: list[tuple[str, int, datetime]] = []
        self.active_command = ""
        self.active_output: list[str] = []
        self.console_diagnostics: dict[str, ToolDiagnostic] = {}
        self.console_diagnostic_sequence = 0
        self.serial_windows: list[tk.Toplevel] = []
        self.uart_history: list[str] = []
        self.verification_summary = tk.StringVar(master=root, value="No verification run in this session yet.")

        self._configure_styles()
        self._build_menu()
        self._build_layout()
        self._bind_shortcuts()
        remembered_project = self.settings.get("last_project")
        selected_project = initial_project or (remembered_project if isinstance(remembered_project, str) else None)
        self._refresh_projects(selected_project)
        self.root.after(60, self._poll_process_queue)
        self.root.after(180, self._bring_to_front)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        LOGGER.info("Studio %s started; project=%s", APP_VERSION, self._project_relative())

    # ------------------------------------------------------------------ UI
    def _create_icons(self) -> tuple[IconFactory, dict[str, tk.PhotoImage]]:
        factory = IconFactory(self.root)
        icons = {
            name: factory.get(name, COLORS[token])
            for name, token in ICON_COLOR_TOKENS.items()
        }
        icons["chip_large"] = factory.get("chip", COLORS["cyan"], 30)
        return factory, icons

    @staticmethod
    def _translated_color(value: object, old_theme: str, tokens: tuple[str, ...]) -> str | None:
        current = str(value).lower()
        old_palette = THEMES[old_theme]
        for token in tokens:
            if current == old_palette[token].lower():
                return COLORS[token]
        return None

    def _walk_widgets(self) -> list[tk.Misc]:
        widgets: list[tk.Misc] = [self.root]
        for widget in widgets:
            try:
                widgets.extend(widget.winfo_children())
            except tk.TclError:
                continue
        return widgets

    def _image_reference(self, value: object) -> str:
        """Normalize Tk's string/one-element Tcl tuple image representations."""
        try:
            values = self.root.tk.splitlist(value)
            return str(values[0]) if values else ""
        except (TypeError, tk.TclError):
            return str(value)

    def _refresh_widget_images(
        self, widget: tk.Misc, old_image_names: dict[str, str],
    ) -> None:
        try:
            configuration = widget.configure()
            if "image" in configuration:
                current = self._image_reference(widget.cget("image"))
                if current in old_image_names:
                    widget.configure(image=self.icons[old_image_names[current]])
        except (AttributeError, KeyError, tk.TclError):
            pass

        if isinstance(widget, ttk.Notebook):
            for tab_id in widget.tabs():
                try:
                    current = self._image_reference(widget.tab(tab_id, "image"))
                    if current in old_image_names:
                        widget.tab(tab_id, image=self.icons[old_image_names[current]])
                except (KeyError, tk.TclError):
                    continue

        if isinstance(widget, ttk.Treeview):
            pending = list(widget.get_children(""))
            while pending:
                item = pending.pop()
                pending.extend(widget.get_children(item))
                try:
                    current = self._image_reference(widget.item(item, "image"))
                    if current in old_image_names:
                        widget.item(item, image=self.icons[old_image_names[current]])
                except (KeyError, tk.TclError):
                    continue

    def _refresh_widget_colors(self, widget: tk.Misc, old_theme: str) -> None:
        option_tokens = {
            "background": BACKGROUND_COLOR_TOKENS,
            "activebackground": BACKGROUND_COLOR_TOKENS,
            "disabledbackground": BACKGROUND_COLOR_TOKENS,
            "fieldbackground": BACKGROUND_COLOR_TOKENS,
            "highlightbackground": BACKGROUND_COLOR_TOKENS,
            "highlightcolor": BACKGROUND_COLOR_TOKENS,
            "selectbackground": BACKGROUND_COLOR_TOKENS,
            "troughcolor": BACKGROUND_COLOR_TOKENS,
            "foreground": FOREGROUND_COLOR_TOKENS,
            "activeforeground": FOREGROUND_COLOR_TOKENS,
            "disabledforeground": FOREGROUND_COLOR_TOKENS,
            "insertbackground": ("cursor", "text", "on_accent"),
            "selectforeground": ("selection_text", "text", "on_accent"),
        }
        try:
            configuration = widget.configure()
        except (AttributeError, tk.TclError):
            configuration = {}
        for option, tokens in option_tokens.items():
            if option not in configuration:
                continue
            try:
                translated = self._translated_color(widget.cget(option), old_theme, tokens)
                if translated:
                    widget.configure(**{option: translated})
            except (AttributeError, tk.TclError):
                continue

        if isinstance(widget, tk.Text):
            for tag in widget.tag_names():
                for option, tokens in (("foreground", FOREGROUND_COLOR_TOKENS),
                                       ("background", BACKGROUND_COLOR_TOKENS)):
                    try:
                        translated = self._translated_color(widget.tag_cget(tag, option), old_theme, tokens)
                        if translated:
                            widget.tag_configure(tag, **{option: translated})
                    except tk.TclError:
                        continue

        if isinstance(widget, tk.Canvas):
            for item in widget.find_all():
                for option, tokens in (("fill", FOREGROUND_COLOR_TOKENS + BACKGROUND_COLOR_TOKENS),
                                       ("outline", BACKGROUND_COLOR_TOKENS + FOREGROUND_COLOR_TOKENS)):
                    try:
                        translated = self._translated_color(widget.itemcget(item, option), old_theme, tokens)
                        if translated:
                            widget.itemconfigure(item, **{option: translated})
                    except tk.TclError:
                        continue

        if isinstance(widget, ttk.Treeview):
            tags: set[str] = set()
            pending = list(widget.get_children(""))
            while pending:
                item = pending.pop()
                pending.extend(widget.get_children(item))
                tags.update(str(tag) for tag in widget.item(item, "tags"))
            for tag in tags:
                for option, tokens in (("foreground", FOREGROUND_COLOR_TOKENS),
                                       ("background", BACKGROUND_COLOR_TOKENS)):
                    try:
                        translated = self._translated_color(widget.tag_configure(tag, option), old_theme, tokens)
                        if translated:
                            widget.tag_configure(tag, **{option: translated})
                    except tk.TclError:
                        continue

    def _refresh_menu_theme(self, menu: tk.Menu, old_image_names: dict[str, str]) -> None:
        try:
            menu.configure(
                bg=COLORS["panel"], fg=COLORS["text"], activebackground=COLORS["selection"],
                activeforeground=COLORS["selection_text"], selectcolor=COLORS["accent"],
            )
            end = menu.index("end")
            if end is None:
                return
            for index in range(end + 1):
                try:
                    current = self._image_reference(menu.entrycget(index, "image"))
                    if current in old_image_names:
                        menu.entryconfigure(index, image=self.icons[old_image_names[current]])
                except tk.TclError:
                    continue
        except tk.TclError:
            LOGGER.debug("A closing menu could not be rethemed", exc_info=True)

    def _configure_semantic_tags(self) -> None:
        if hasattr(self, "console"):
            self.console.tag_configure("command", foreground=COLORS["cyan"])
            self.console.tag_configure("success", foreground=COLORS["green"])
            self.console.tag_configure("warning", foreground=COLORS["yellow"])
            self.console.tag_configure("error", foreground=COLORS["red"])
            self.console.tag_configure("muted", foreground=COLORS["muted"])
        if hasattr(self, "problems_tree"):
            self.problems_tree.tag_configure("error", foreground=COLORS["red"])
            self.problems_tree.tag_configure("warning", foreground=COLORS["yellow"])
            self.problems_tree.tag_configure("info", foreground=COLORS["cyan"])
        if hasattr(self, "coach"):
            self.coach.tag_configure("title", foreground=COLORS["cyan"])
            self.coach.tag_configure("heading", foreground=COLORS["accent_text"])
            self.coach.tag_configure("good", foreground=COLORS["green"])
            self.coach.tag_configure("warning", foreground=COLORS["yellow"])
            self.coach.tag_configure("muted", foreground=COLORS["muted"])
        if hasattr(self, "insights"):
            self.insights.tag_configure("score", foreground=COLORS["green"])
            self.insights.tag_configure("title", foreground=COLORS["text"])
            self.insights.tag_configure("heading", foreground=COLORS["cyan"])
            self.insights.tag_configure("good", foreground=COLORS["green"])
            self.insights.tag_configure("next", foreground=COLORS["yellow"])
            self.insights.tag_configure("blocked", foreground=COLORS["red"])
            self.insights.tag_configure("muted", foreground=COLORS["muted"])
        if hasattr(self, "editor"):
            self._configure_editor_tags()

    def _sync_theme_controls(self) -> None:
        self.theme_var.set(self.theme_name)
        self.theme_button_text.set("Light mode" if self.theme_name == "dark" else "Dark mode")

    def _apply_theme_visuals(
        self, target: str, previous: str,
        legacy_icon_sets: tuple[dict[str, tk.PhotoImage], ...] = (),
    ) -> None:
        old_icons = self.icons
        old_image_names = {str(image): name for name, image in old_icons.items()}
        for icon_set in legacy_icon_sets:
            old_image_names.update({str(image): name for name, image in icon_set.items()})
        COLORS.clear()
        COLORS.update(theme_colors(target))
        new_factory, new_icons = self._create_icons()
        self.icon_factory = new_factory
        self.icons = new_icons
        self.root.configure(bg=COLORS["bg"])
        self.root.iconphoto(True, self.icons["chip"])
        self._configure_styles()
        for widget in self._walk_widgets():
            self._refresh_widget_colors(widget, previous)
            self._refresh_widget_images(widget, old_image_names)
        for menu in self.menus:
            self._refresh_menu_theme(menu, old_image_names)
        self._configure_semantic_tags()
        if hasattr(self, "line_numbers"):
            self.line_numbers.redraw()
        # Keep the replaced PhotoImages alive until Tk has processed every update.
        self.root.after_idle(lambda retained=old_icons: retained.clear())

    def set_theme(self, name: str, *, persist: bool = True, announce: bool = True) -> bool:
        """Apply a theme atomically; recover the previous palette on failure."""
        target = name.strip().lower() if isinstance(name, str) else ""
        if target not in THEMES:
            LOGGER.warning("Rejected unknown theme: %r", name)
            self._sync_theme_controls()
            return False
        if target == self.theme_name:
            self._sync_theme_controls()
            return True

        previous = self.theme_name
        previous_setting = self.settings.get("theme")
        original_icons = self.icons
        try:
            self._apply_theme_visuals(target, previous)
            self.theme_name = target
            self._sync_theme_controls()
            if persist:
                self.settings["theme"] = target
                save_user_settings(self.settings)
            if announce and hasattr(self, "status_text"):
                self.status_text.set(f"{target.title()} theme enabled")
            LOGGER.info("Theme switched from %s to %s", previous, target)
            return True
        except Exception as error:  # UI recovery boundary: Tk can raise many platform-specific errors.
            LOGGER.exception("Theme switch from %s to %s failed", previous, target)
            try:
                current = target
                self._apply_theme_visuals(previous, current, (original_icons,))
            except Exception:
                LOGGER.critical("Theme rollback also failed", exc_info=True)
                COLORS.clear()
                COLORS.update(theme_colors(previous))
            self.theme_name = previous
            self._sync_theme_controls()
            if previous_setting is None:
                self.settings.pop("theme", None)
            else:
                self.settings["theme"] = previous_setting
            if announce:
                try:
                    messagebox.showerror(
                        "Theme switch recovered",
                        f"The {target} theme could not be applied. The IDE restored {previous} mode.\n\n"
                        f"Details: {LOG_PATH}\n\n{error}",
                        parent=self.root,
                    )
                except tk.TclError:
                    pass
            return False

    def toggle_theme(self, _event=None) -> str | None:
        target = "light" if self.theme_name == "dark" else "dark"
        self.set_theme(target)
        return "break" if _event is not None else None

    def _configure_styles(self) -> None:
        # ttk combobox pop-down lists are native Tk children, not ttk style
        # elements, so their colors must follow the palette via the option DB.
        for pattern, value in (
            ("*TCombobox*Listbox.background", COLORS["panel_alt"]),
            ("*TCombobox*Listbox.foreground", COLORS["text"]),
            ("*TCombobox*Listbox.selectBackground", COLORS["selection"]),
            ("*TCombobox*Listbox.selectForeground", COLORS["selection_text"]),
        ):
            self.root.option_add(pattern, value, 80)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=COLORS["panel"], foreground=COLORS["text"],
                        fieldbackground=COLORS["panel_alt"], bordercolor=COLORS["border"],
                        font=("Segoe UI", 10))
        style.configure("TFrame", background=COLORS["panel"])
        style.configure("Top.TFrame", background=COLORS["bg"])
        style.configure("Header.TFrame", background=COLORS["header"])
        style.configure("Card.TFrame", background=COLORS["panel"])
        style.configure("TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"],
                        font=("Segoe UI Semibold", 17))
        style.configure("Brand.TLabel", background=COLORS["header"], foreground=COLORS["text"],
                        font=("Segoe UI Semibold", 18))
        style.configure("HeaderMuted.TLabel", background=COLORS["header"], foreground=COLORS["muted"],
                        font=("Segoe UI", 9))
        style.configure("Eyebrow.TLabel", background=COLORS["panel"], foreground=COLORS["muted_2"],
                        font=("Segoe UI Semibold", 8))
        style.configure("Muted.TLabel", foreground=COLORS["muted"])
        style.configure("Accent.TLabel", background=COLORS["panel"], foreground=COLORS["accent_text"],
                        font=("Segoe UI Semibold", 10))
        style.configure("Status.TLabel", background=COLORS["bg"], foreground=COLORS["muted"])
        style.configure("TButton", background=COLORS["panel_alt"], foreground=COLORS["text"],
                        padding=(9, 6), borderwidth=1)
        style.map("TButton", background=[("active", COLORS["border"]), ("disabled", COLORS["panel"])],
                  foreground=[("disabled", COLORS["muted"])])
        style.configure("Accent.TButton", background=COLORS["accent"], foreground=COLORS["on_accent"])
        style.map("Accent.TButton", background=[("active", COLORS["accent_hover"]),
                                                ("disabled", COLORS["border"])])
        style.configure("Success.TButton", background=COLORS["success_button"], foreground=COLORS["on_accent"])
        style.map("Success.TButton", background=[("active", COLORS["success_hover"])])
        style.configure("Danger.TButton", background=COLORS["danger_button"], foreground=COLORS["on_accent"])
        style.map(
            "Danger.TButton",
            background=[("active", COLORS["danger_hover"]), ("disabled", COLORS["panel_alt"])],
            foreground=[("disabled", COLORS["muted_2"])],
        )
        style.configure("Toolbar.TButton", background=COLORS["header"], foreground=COLORS["text"],
                        padding=(10, 7), borderwidth=0)
        style.map("Toolbar.TButton", background=[("active", COLORS["panel_hover"]),
                                                  ("pressed", COLORS["selection"]),
                                                  ("disabled", COLORS["header"])],
                  foreground=[("disabled", COLORS["muted_2"])])
        style.configure("Ghost.TButton", background=COLORS["panel"], foreground=COLORS["muted"],
                        padding=(6, 5), borderwidth=0)
        style.map("Ghost.TButton", background=[("active", COLORS["panel_hover"])],
                  foreground=[("active", COLORS["text"])])
        style.configure("Tab.TButton", background=COLORS["panel_alt"], foreground=COLORS["muted"],
                        padding=(9, 5), borderwidth=0)
        style.map("Tab.TButton", background=[("active", COLORS["panel_hover"]),
                                              ("pressed", COLORS["selection"])])
        style.configure("Treeview", background=COLORS["panel"], fieldbackground=COLORS["panel"],
                        foreground=COLORS["text"], rowheight=24, borderwidth=0)
        style.map("Treeview", background=[("selected", COLORS["selection"])])
        style.configure("Treeview.Heading", background=COLORS["panel_alt"],
                        foreground=COLORS["muted"], relief="flat")
        style.configure("TNotebook", background=COLORS["panel"], borderwidth=0)
        style.configure("TNotebook.Tab", background=COLORS["panel_alt"], foreground=COLORS["muted"],
                        padding=(2, 4), font=("Segoe UI", 9))
        style.map("TNotebook.Tab", background=[("selected", COLORS["panel"])],
                  foreground=[("selected", COLORS["text"])])
        style.configure("TCombobox", fieldbackground=COLORS["panel_alt"], foreground=COLORS["text"],
                        arrowcolor=COLORS["text"])
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["panel_alt"]), ("disabled", COLORS["panel"])],
            foreground=[("readonly", COLORS["text"]), ("disabled", COLORS["muted"])],
            selectbackground=[("readonly", COLORS["selection"])],
            selectforeground=[("readonly", COLORS["selection_text"])],
        )
        style.configure("TEntry", fieldbackground=COLORS["panel_alt"], foreground=COLORS["text"],
                        insertcolor=COLORS["cursor"], bordercolor=COLORS["border"])
        style.map("TEntry", fieldbackground=[("disabled", COLORS["panel"]), ("focus", COLORS["panel_alt"])])
        style.configure("Horizontal.TProgressbar", background=COLORS["accent"],
                        troughcolor=COLORS["panel_alt"], borderwidth=0, thickness=7)

    def _bring_to_front(self) -> None:
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(180, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def _report_callback_exception(self, exception_type, exception_value, exception_traceback) -> None:
        LOGGER.error(
            "Unhandled UI callback exception",
            exc_info=(exception_type, exception_value, exception_traceback),
        )
        if hasattr(self, "console"):
            try:
                self._append_console(
                    f"\nUnexpected IDE error: {exception_value}\nDetails: {LOG_PATH}\n", "error",
                )
            except tk.TclError:
                LOGGER.debug("The console was unavailable while reporting an error", exc_info=True)
        try:
            messagebox.showerror(
                "Tang Primer Studio recovered from an error",
                f"The operation could not finish, but the IDE is still running.\n\n"
                f"{exception_value}\n\nDiagnostic log: {LOG_PATH}",
                parent=self.root,
            )
        except tk.TclError:
            LOGGER.debug("The error dialog could not be shown during shutdown", exc_info=True)

    def _action_button(
        self, parent: tk.Misc, text: str, icon: str, command, style: str = "Toolbar.TButton",
        tooltip: str = "", width: int | None = None,
    ) -> ttk.Button:
        options: dict[str, object] = {
            "text": text, "image": self.icons[icon], "compound": "left",
            "command": command, "style": style,
        }
        if width is not None:
            options["width"] = width
        button = ttk.Button(parent, **options)
        if tooltip:
            Tooltip(button, tooltip)
        return button

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=False, bg=COLORS["panel"], fg=COLORS["text"],
                       activebackground=COLORS["selection"], activeforeground=COLORS["text"])
        file_menu = tk.Menu(menu, tearoff=False, bg=COLORS["panel"], fg=COLORS["text"],
                            activebackground=COLORS["selection"])
        file_menu.add_command(label="New Project…", image=self.icons["plus"], compound="left", command=self.new_project)
        file_menu.add_command(label="New HDL Module…", image=self.icons["code"], compound="left", command=self.new_module)
        file_menu.add_separator()
        file_menu.add_command(label="Save", image=self.icons["save"], compound="left",
                              accelerator="Ctrl+S", command=self.save_file)
        file_menu.add_command(label="Open Project Folder", image=self.icons["folder"], compound="left",
                              command=self.open_project_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menu.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menu, tearoff=False, bg=COLORS["panel"], fg=COLORS["text"],
                            activebackground=COLORS["selection"])
        edit_menu.add_command(label="Command Palette…", image=self.icons["command"], compound="left",
                              accelerator="Ctrl+Shift+P", command=self.show_command_palette)
        edit_menu.add_command(label="Search Project…", image=self.icons["search"], compound="left",
                              accelerator="Ctrl+Shift+F", command=self.show_project_search)
        edit_menu.add_command(label="HDL Snippets…", image=self.icons["sparkle"], compound="left",
                              accelerator="Ctrl+Alt+S", command=self.show_snippets)
        edit_menu.add_command(label="Find symbol references…", image=self.icons["search"], compound="left",
                              accelerator="Shift+F12", command=self.show_symbol_references)
        edit_menu.add_command(label="Generate module instance…", image=self.icons["code"], compound="left",
                              command=self.generate_module_instance)
        edit_menu.add_separator()
        edit_menu.add_command(label="Toggle line comment", accelerator="Ctrl+/", command=self.toggle_line_comment)
        edit_menu.add_command(label="Duplicate line", accelerator="Ctrl+D", command=self.duplicate_line)
        menu.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menu, tearoff=False, bg=COLORS["panel"], fg=COLORS["text"],
                            activebackground=COLORS["selection"])
        view_menu.add_radiobutton(
            label="Dark mode", value="dark", variable=self.theme_var,
            command=lambda: self.set_theme(self.theme_var.get()),
        )
        view_menu.add_radiobutton(
            label="Light mode", value="light", variable=self.theme_var,
            command=lambda: self.set_theme(self.theme_var.get()),
        )
        view_menu.add_separator()
        view_menu.add_command(label="Toggle theme", accelerator="Ctrl+Alt+T", command=self.toggle_theme)
        menu.add_cascade(label="View", menu=view_menu)

        run_menu = tk.Menu(menu, tearoff=False, bg=COLORS["panel"], fg=COLORS["text"],
                           activebackground=COLORS["selection"])
        for label, command, accelerator in (
            ("Simulate", "sim", "F5"), ("Open GTKWave", "wave", "F6"),
            ("Lint", "lint", "F7"), ("Debug", "debug", "F8"),
            ("Build", "build", "Ctrl+B"), ("Upload SRAM", "upload", "F9"),
            ("Flash persistent", "flash", ""), ("Detect FPGA", "detect", ""),
            ("Doctor", "doctor", ""),
        ):
            icon = {
                "sim": "play", "wave": "wave", "lint": "lint", "debug": "bug",
                "build": "build", "upload": "upload", "flash": "flash",
                "detect": "target", "doctor": "doctor",
            }[command]
            run_menu.add_command(label=label, image=self.icons[icon], compound="left", accelerator=accelerator,
                                 command=lambda value=command: self.run_fpga(value))
        run_menu.add_separator()
        run_menu.add_command(
            label="Upload existing bitstream (no rebuild)",
            command=lambda: self.run_fpga("upload", ["-NoBuild"]),
        )
        run_menu.add_command(
            label="Flash existing bitstream (no rebuild)",
            command=lambda: self.run_fpga("flash", ["-NoBuild"]),
        )
        run_menu.add_separator()
        run_menu.add_command(label="UART Terminal…", command=self.open_serial_monitor)
        run_menu.add_command(label="Stop running command", command=self.stop_process)
        menu.add_cascade(label="Run", menu=run_menu)

        tools_menu = tk.Menu(menu, tearoff=False, bg=COLORS["panel"], fg=COLORS["text"],
                             activebackground=COLORS["selection"])
        tools_menu.add_command(label="Smart project check", command=lambda: self.analyze_project(True))
        tools_menu.add_command(label="Project insights", image=self.icons["dashboard"], compound="left",
                               command=self.show_project_insights)
        tools_menu.add_command(label="Synthesized netlist viewer…", image=self.icons["dashboard"], compound="left",
                               command=self.show_netlist_viewer)
        tools_menu.add_command(label="Pin assignment inspector", image=self.icons["target"], compound="left",
                               command=self.show_pin_inspector)
        tools_menu.add_command(label="Verification center…", image=self.icons["bug"], compound="left",
                               command=self.show_verification_center)
        tools_menu.add_command(label="Hardware setup guide…", image=self.icons["doctor"], compound="left",
                               command=self.show_hardware_setup)
        tools_menu.add_command(label="Quick fix selected problem", image=self.icons["bulb"], compound="left",
                               command=self.apply_quick_fix)
        tools_menu.add_command(label="Refresh file tree", command=self.populate_file_tree)
        tools_menu.add_separator()
        tools_menu.add_command(label="Install/verify toolchain", command=lambda: self.run_fpga("setup"))
        tools_menu.add_command(label="Configure JTAG driver", command=lambda: self.run_fpga("driver"))
        tools_menu.add_command(label="Clean generated build", command=self.clean_project)
        menu.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menu, tearoff=False, bg=COLORS["panel"], fg=COLORS["text"],
                            activebackground=COLORS["selection"])
        help_menu.add_command(label="What's new in 1.2.0…", image=self.icons["sparkle"], compound="left",
                              command=self.show_release_notes)
        help_menu.add_separator()
        help_menu.add_command(label="Interactive first-project tutorial…", image=self.icons["bulb"], compound="left",
                              command=self.show_first_project_tutorial)
        help_menu.add_command(label="Project guide", command=self.show_beginner_guide)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.menus = [menu, file_menu, edit_menu, view_menu, run_menu, tools_menu, help_menu]
        for current_menu in self.menus:
            self._refresh_menu_theme(current_menu, {})
        self.root.configure(menu=menu)

    def _build_layout(self) -> None:
        top = ttk.Frame(self.root, style="Header.TFrame", padding=(16, 10, 16, 9))
        top.pack(fill="x")
        brand = ttk.Frame(top, style="Header.TFrame")
        brand.grid(row=0, column=0, sticky="w")
        logo = self.icon_factory.get("chip", COLORS["cyan"], 30)
        self.icons["chip_large"] = logo
        ttk.Label(brand, image=logo, style="Brand.TLabel").pack(side="left", padx=(0, 10))
        brand_copy = ttk.Frame(brand, style="Header.TFrame")
        brand_copy.pack(side="left")
        ttk.Label(brand_copy, text="Tang Primer Studio", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand_copy, text="Design, verify, and program your Tang Primer 20K",
                  style="HeaderMuted.TLabel").pack(anchor="w")

        project_area = ttk.Frame(top, style="Header.TFrame")
        project_area.grid(row=0, column=1, sticky="w", padx=(36, 20))
        ttk.Label(project_area, text="Project", style="HeaderMuted.TLabel").pack(anchor="w", pady=(0, 3))
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(project_area, textvariable=self.project_var, state="readonly", width=29)
        self.project_combo.pack(fill="x")
        self.project_combo.bind("<<ComboboxSelected>>", self._project_selected)

        top.columnconfigure(2, weight=1)
        self.theme_button = self._action_button(
            top, "", "theme", self.toggle_theme, tooltip="Switch between accessible dark and light modes",
        )
        self.theme_button.configure(textvariable=self.theme_button_text)
        self.theme_button.grid(row=0, column=2, sticky="e")

        tk.Frame(self.root, bg=COLORS["accent"], height=2).pack(fill="x")
        toolbar = ttk.Frame(self.root, style="Header.TFrame", padding=(14, 6, 14, 7))
        toolbar.pack(fill="x")
        design_row = ttk.Frame(toolbar, style="Header.TFrame")
        design_row.pack(fill="x")
        # Reserve the right-side utilities before packing the longer action
        # groups so they remain fully visible on supported laptop widths.
        self._action_button(
            design_row, "Commands", "command", self.show_command_palette,
            tooltip="Search every IDE action (Ctrl+Shift+P)",
        ).pack(side="right", padx=2)
        self._action_button(
            design_row, "", "search", self.show_project_search, "Toolbar.TButton",
            "Search this project (Ctrl+Shift+F)", width=2,
        ).pack(side="right", padx=2)
        self._action_button(
            design_row, "", "save", self.save_file, "Toolbar.TButton", "Save current file (Ctrl+S)", width=2,
        ).pack(side="right", padx=2)
        ttk.Label(design_row, text="Create", style="HeaderMuted.TLabel").pack(side="left", padx=(0, 5))
        create_group = ttk.Frame(design_row, style="Header.TFrame")
        create_group.pack(side="left")
        self._action_button(create_group, "Project", "plus", self.new_project, tooltip="Create from the verified template").pack(side="left", padx=2)
        self._action_button(create_group, "Module", "code", self.new_module, tooltip="Create a SystemVerilog module").pack(side="left", padx=2)
        self._action_button(create_group, "Snippets", "sparkle", self.show_snippets, tooltip="Insert a safe HDL pattern").pack(side="left", padx=2)
        ttk.Separator(design_row, orient="vertical").pack(side="left", fill="y", padx=9)
        ttk.Label(design_row, text="Verify", style="HeaderMuted.TLabel").pack(side="left", padx=(0, 5))

        verify_actions = (
            ("Simulate", "sim", "play", "Run the self-checking testbench (F5)"),
            ("Waveform", "wave", "wave", "Simulate and open the prepared GTKWave view (F6)"),
            ("Lint", "lint", "lint", "Run Verilator design checks (F7)"),
            ("Debug", "debug", "bug", "Lint, simulate and inspect waveforms (F8)"),
        )
        hardware_actions = (
            ("Build", "build", "build", "Create the FPGA bitstream (Ctrl+B)"),
            ("SRAM", "upload", "upload", "Build and upload volatile SRAM (F9)"),
            ("Flash", "flash", "flash", "Write persistent configuration after SRAM validation"),
            ("Detect", "detect", "target", "Scan the attached JTAG chain"),
            ("Doctor", "doctor", "doctor", "Check tools, USB interfaces and COM ports"),
        )
        for label, command, icon, tip in verify_actions:
            button = self._action_button(
                design_row, label, icon, lambda value=command: self.run_fpga(value),
                tooltip=tip,
            )
            button.pack(side="left", padx=2)
            self.runner_buttons.append(button)

        hardware_row = ttk.Frame(toolbar, style="Header.TFrame")
        hardware_row.pack(fill="x", pady=(3, 0))
        ttk.Label(hardware_row, text="Hardware", style="HeaderMuted.TLabel").pack(side="left", padx=(0, 5))
        for label, command, icon, tip in hardware_actions:
            button = self._action_button(
                hardware_row, label, icon, lambda value=command: self.run_fpga(value), tooltip=tip,
            )
            button.pack(side="left", padx=2)
            self.runner_buttons.append(button)
        self._action_button(
            hardware_row, "UART terminal", "terminal", self.open_serial_monitor,
            tooltip="Connect, send, receive, inspect, and save UART data",
        ).pack(side="left", padx=(8, 2))
        self._action_button(
            hardware_row, "Setup guide", "doctor", self.show_hardware_setup,
            tooltip="Check the board, JTAG driver, UART port, and DIP switches",
        ).pack(side="left", padx=2)
        ttk.Separator(hardware_row, orient="vertical").pack(side="left", fill="y", padx=9)
        self._action_button(
            hardware_row, "Analyze", "sparkle", lambda: self.analyze_project(True),
            tooltip="Refresh intelligent project diagnostics",
        ).pack(side="left", padx=2)
        self._action_button(
            hardware_row, "Netlist", "dashboard", self.show_netlist_viewer,
            tooltip="Explore synthesized components and local connectivity",
        ).pack(side="left", padx=2)
        self.stop_button = self._action_button(
            hardware_row, "Stop", "stop", self.stop_process, "Danger.TButton", "Stop the running command tree",
        )
        self.stop_button.configure(state="disabled")
        self.stop_button.pack(side="right", padx=2)
        self.run_state = ttk.Label(hardware_row, text="● READY", style="HeaderMuted.TLabel")
        self.run_state.pack(side="right", padx=(0, 12))

        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=9, pady=(8, 5))

        left = ttk.Frame(main, style="Card.TFrame", padding=6)
        center = ttk.Frame(main, style="Card.TFrame")
        right = ttk.Frame(main, style="Card.TFrame")
        main.add(left, weight=1)
        main.add(center, weight=5)
        main.add(right, weight=2)
        self._build_file_explorer(left)
        self._build_center(center)
        self._build_intelligence_panel(right)

        status = ttk.Frame(self.root, style="Top.TFrame", padding=(12, 6))
        status.pack(fill="x")
        self.status_text = tk.StringVar(value="Ready")
        self.device_text = tk.StringVar(value="GW2A-18  •  27 MHz")
        ttk.Label(status, image=self.icons["chip"], textvariable=self.device_text, compound="left",
                  style="Status.TLabel").pack(side="left", padx=(0, 18))
        self.health_text = tk.StringVar(value="Health —")
        ttk.Label(status, image=self.icons["dashboard"], textvariable=self.health_text, compound="left",
                  style="Status.TLabel").pack(side="left", padx=(0, 18))
        ttk.Label(status, textvariable=self.status_text, style="Status.TLabel").pack(side="left")
        self.cursor_text = tk.StringVar(value="Ln 1, Col 1")
        ttk.Label(status, text="UTF-8  •  SystemVerilog", style="Status.TLabel").pack(side="right", padx=(12, 0))
        ttk.Label(status, textvariable=self.cursor_text, style="Status.TLabel").pack(side="right")

    def _build_file_explorer(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, padding=(3, 3, 3, 6))
        header.pack(fill="x")
        copy = ttk.Frame(header)
        copy.pack(side="left")
        ttk.Label(copy, text="Explorer", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(copy, text="Project files", font=("Segoe UI Semibold", 11)).pack(anchor="w")
        refresh = self._action_button(header, "", "refresh", self.populate_file_tree, "Ghost.TButton",
                                      "Refresh project files", width=2)
        refresh.pack(side="right")
        add_module = self._action_button(header, "", "plus", self.new_module, "Ghost.TButton",
                                         "Create an HDL module", width=2)
        add_module.pack(side="right", padx=2)
        self.file_filter_var = tk.StringVar()
        self.file_filter_var.trace_add("write", lambda *_args: self.populate_file_tree())
        filter_frame = tk.Frame(parent, bg=COLORS["panel_alt"], highlightthickness=1,
                                highlightbackground=COLORS["border_soft"])
        filter_frame.pack(fill="x", padx=2, pady=(0, 7))
        tk.Label(filter_frame, image=self.icons["search"], bg=COLORS["panel_alt"]).pack(side="left", padx=(7, 3))
        self.file_filter = tk.Entry(
            filter_frame, textvariable=self.file_filter_var, bg=COLORS["panel_alt"], fg=COLORS["text"],
            insertbackground=COLORS["cursor"], relief="flat", font=("Segoe UI", 9),
        )
        self.file_filter.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=6)
        footer = ttk.Frame(parent, padding=(2, 7, 2, 2))
        footer.pack(fill="x", side="bottom")
        self._action_button(footer, "New module", "code", self.new_module, "Ghost.TButton").pack(side="left")
        self._action_button(footer, "Folder", "folder", self.open_project_folder, "Ghost.TButton").pack(side="right")
        self.file_tree = ttk.Treeview(parent, show="tree", selectmode="browse")
        file_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=file_scroll.set)
        self.file_tree.pack(side="left", fill="both", expand=True)
        file_scroll.pack(side="right", fill="y")
        self.file_tree.bind("<Double-1>", self._tree_open)
        self.file_tree.bind("<Return>", self._tree_open)

    def _build_center(self, parent: ttk.Frame) -> None:
        vertical = ttk.Panedwindow(parent, orient="vertical")
        vertical.pack(fill="both", expand=True)
        editor_card = ttk.Frame(vertical)
        console_card = ttk.Frame(vertical)
        vertical.add(editor_card, weight=5)
        vertical.add(console_card, weight=2)

        self.editor_tabs = ttk.Frame(editor_card, style="Card.TFrame", padding=(6, 4, 6, 0))
        self.editor_tabs.pack(fill="x")
        editor_header = ttk.Frame(editor_card, padding=(10, 6))
        editor_header.pack(fill="x")
        self.file_label = tk.StringVar(value="No file open")
        ttk.Label(editor_header, image=self.icons["code"], textvariable=self.file_label,
                  compound="left", font=("Segoe UI Semibold", 10)).pack(side="left")
        self._action_button(
            editor_header, "", "sparkle", self.show_snippets, "Ghost.TButton", "Insert an HDL snippet", width=2,
        ).pack(side="right", padx=2)
        self._action_button(
            editor_header, "", "bulb", self.explain_current_code, "Ghost.TButton",
            "Explain the selected HDL construct (Ctrl+Shift+E)", width=2,
        ).pack(side="right", padx=2)
        self._action_button(
            editor_header, "", "search", self.show_project_search, "Ghost.TButton", "Search this project", width=2,
        ).pack(side="right", padx=2)
        ttk.Label(editor_header, text="Ctrl+Space Complete   •   F12 Definition   •   Shift+F12 References",
                  style="Eyebrow.TLabel").pack(side="right", padx=8)

        code_frame = tk.Frame(editor_card, bg=COLORS["editor"], highlightthickness=1,
                              highlightbackground=COLORS["border_soft"])
        code_frame.pack(fill="both", expand=True)
        self.editor = tk.Text(
            code_frame, undo=True, wrap="none", height=12,
            background=COLORS["editor"], foreground=COLORS["text"],
            insertbackground=COLORS["cursor"], selectbackground=COLORS["selection"],
            selectforeground=COLORS["selection_text"], relief="flat",
            padx=12, pady=10, font=("Cascadia Code", 11), tabs=(32,), maxundo=500,
            spacing1=1, spacing3=1,
        )
        self.line_numbers = LineNumberCanvas(code_frame, self.editor, bg=COLORS["panel"])
        y_scroll = ttk.Scrollbar(code_frame, orient="vertical")
        x_scroll = ttk.Scrollbar(code_frame, orient="horizontal", command=self.editor.xview)

        def on_y_scroll(first: str, last: str) -> None:
            y_scroll.set(first, last)
            self.line_numbers.redraw()

        self.editor.configure(yscrollcommand=on_y_scroll, xscrollcommand=x_scroll.set)
        y_scroll.configure(command=self._editor_yview)
        self.line_numbers.pack(side="left", fill="y")
        self.editor.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(side="bottom", fill="x")
        self._configure_editor_tags()

        console_header = ttk.Frame(console_card, padding=(9, 6))
        console_header.pack(fill="x")
        ttk.Label(console_header, image=self.icons["terminal"], text="  Command console",
                  compound="left", font=("Segoe UI Semibold", 10)).pack(side="left")
        self.console_meta = tk.StringVar(value="Ready for a command")
        ttk.Label(console_header, textvariable=self.console_meta, style="Muted.TLabel").pack(side="left", padx=14)
        self._action_button(console_header, "Clear", "close", self.clear_console, "Ghost.TButton",
                            "Clear console output").pack(side="right")
        self.console = tk.Text(
            console_card, wrap="word", height=7, state="disabled", background=COLORS["console"],
            foreground=COLORS["text"], insertbackground=COLORS["cursor"], relief="flat", padx=9, pady=7,
            font=("Cascadia Mono", 9), spacing1=1, spacing3=1,
        )
        console_scroll = ttk.Scrollbar(console_card, orient="vertical", command=self.console.yview)
        self.console.configure(yscrollcommand=console_scroll.set)
        self.console.pack(side="left", fill="both", expand=True)
        console_scroll.pack(side="right", fill="y")
        self.console.tag_configure("command", foreground=COLORS["cyan"])
        self.console.tag_configure("success", foreground=COLORS["green"])
        self.console.tag_configure("warning", foreground=COLORS["yellow"])
        self.console.tag_configure("error", foreground=COLORS["red"])
        self.console.tag_configure("muted", foreground=COLORS["muted"])

    def _build_intelligence_panel(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)
        outline_frame = ttk.Frame(notebook, padding=5)
        problems_frame = ttk.Frame(notebook, padding=5)
        coach_frame = ttk.Frame(notebook, padding=5)
        insights_frame = ttk.Frame(notebook, padding=5)
        notebook.add(outline_frame, text="Outline", image=self.icons["code"], compound="left")
        notebook.add(problems_frame, text="Problems", image=self.icons["lint"], compound="left")
        notebook.add(coach_frame, text="Guide", image=self.icons["bulb"], compound="left")
        notebook.add(insights_frame, text="Insights", image=self.icons["dashboard"], compound="left")
        self.intelligence_notebook = notebook

        self.outline_tree = ttk.Treeview(outline_frame, show="tree")
        outline_scroll = ttk.Scrollbar(outline_frame, orient="vertical", command=self.outline_tree.yview)
        self.outline_tree.configure(yscrollcommand=outline_scroll.set)
        self.outline_tree.pack(side="left", fill="both", expand=True)
        outline_scroll.pack(side="right", fill="y")
        self.outline_tree.bind("<Double-1>", self._outline_open)

        self.problems_tree = ttk.Treeview(
            problems_frame, columns=("severity", "location"), show="tree headings",
        )
        self.problems_tree.heading("#0", text="Message")
        self.problems_tree.heading("severity", text="Level")
        self.problems_tree.heading("location", text="Location")
        self.problems_tree.column("#0", width=190, stretch=True)
        self.problems_tree.column("severity", width=54, stretch=False)
        self.problems_tree.column("location", width=92, stretch=False)
        problem_actions = ttk.Frame(problems_frame, padding=(2, 6, 2, 2))
        problem_actions.pack(side="bottom", fill="x")
        self.quick_fix_button = self._action_button(
            problem_actions, "Apply safe quick fix", "bulb", self.apply_quick_fix,
            "Accent.TButton", "Apply a safe automated fix when one is available",
        )
        self.quick_fix_button.pack(side="left")
        self.problem_count = tk.StringVar(value="0 problems")
        ttk.Label(problem_actions, textvariable=self.problem_count, style="Muted.TLabel").pack(side="right")
        problems_scroll = ttk.Scrollbar(problems_frame, orient="vertical", command=self.problems_tree.yview)
        self.problems_tree.configure(yscrollcommand=problems_scroll.set)
        self.problems_tree.pack(side="left", fill="both", expand=True)
        problems_scroll.pack(side="right", fill="y")
        self.problems_tree.bind("<Double-1>", self._problem_open)
        self.problems_tree.bind("<<TreeviewSelect>>", self._problem_selected)
        self.problems_tree.tag_configure("error", foreground=COLORS["red"])
        self.problems_tree.tag_configure("warning", foreground=COLORS["yellow"])
        self.problems_tree.tag_configure("info", foreground=COLORS["cyan"])

        self.coach = tk.Text(
            coach_frame, wrap="word", width=38, state="disabled", background=COLORS["panel"],
            foreground=COLORS["text"], relief="flat", padx=8, pady=8, font=("Segoe UI", 10),
        )
        coach_scroll = ttk.Scrollbar(coach_frame, orient="vertical", command=self.coach.yview)
        self.coach.configure(yscrollcommand=coach_scroll.set)
        self.coach.pack(side="left", fill="both", expand=True)
        coach_scroll.pack(side="right", fill="y")
        self.coach.tag_configure("title", foreground=COLORS["cyan"], font=("Segoe UI Semibold", 13))
        self.coach.tag_configure("heading", foreground=COLORS["accent_text"], font=("Segoe UI Semibold", 10))
        self.coach.tag_configure("good", foreground=COLORS["green"])
        self.coach.tag_configure("warning", foreground=COLORS["yellow"])
        self.coach.tag_configure("muted", foreground=COLORS["muted"])

        self.insights = tk.Text(
            insights_frame, wrap="word", width=38, state="disabled", background=COLORS["panel"],
            foreground=COLORS["text"], relief="flat", padx=10, pady=10, font=("Segoe UI", 10),
        )
        insights_scroll = ttk.Scrollbar(insights_frame, orient="vertical", command=self.insights.yview)
        self.insights.configure(yscrollcommand=insights_scroll.set)
        self.insights.pack(side="left", fill="both", expand=True)
        insights_scroll.pack(side="right", fill="y")
        self.insights.tag_configure("score", foreground=COLORS["green"], font=("Segoe UI Semibold", 28))
        self.insights.tag_configure("title", foreground=COLORS["text"], font=("Segoe UI Semibold", 13))
        self.insights.tag_configure("heading", foreground=COLORS["cyan"], font=("Segoe UI Semibold", 10))
        self.insights.tag_configure("good", foreground=COLORS["green"])
        self.insights.tag_configure("next", foreground=COLORS["yellow"])
        self.insights.tag_configure("blocked", foreground=COLORS["red"])
        self.insights.tag_configure("muted", foreground=COLORS["muted"])

    def _configure_editor_tags(self) -> None:
        self.editor.tag_configure("keyword", foreground=COLORS["purple"])
        self.editor.tag_configure("module", foreground=COLORS["cyan"])
        self.editor.tag_configure("signal", foreground=COLORS["editor_signal"])
        self.editor.tag_configure("comment", foreground=COLORS["editor_comment"])
        self.editor.tag_configure("string", foreground=COLORS["editor_string"])
        self.editor.tag_configure("number", foreground=COLORS["orange"])
        self.editor.tag_configure("directive", foreground=COLORS["yellow"])
        self.editor.tag_configure("current_line", background=COLORS["current_line"])
        self.editor.tag_configure("matching_bracket", background=COLORS["selection"],
                                  foreground=COLORS["selection_text"], font=("Cascadia Code", 11, "bold"))

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Control-s>", lambda _event: self.save_file())
        self.root.bind_all("<Control-b>", lambda _event: self.run_fpga("build"))
        self.root.bind_all("<F5>", lambda _event: self.run_fpga("sim"))
        self.root.bind_all("<F6>", lambda _event: self.run_fpga("wave"))
        self.root.bind_all("<F7>", lambda _event: self.run_fpga("lint"))
        self.root.bind_all("<F8>", lambda _event: self.run_fpga("debug"))
        self.root.bind_all("<F9>", lambda _event: self.run_fpga("upload"))
        self.root.bind_all("<Control-Shift-P>", lambda _event: self.show_command_palette())
        self.root.bind_all("<Control-Shift-F>", lambda _event: self.show_project_search())
        self.root.bind_all("<Control-Alt-s>", lambda _event: self.show_snippets())
        self.root.bind_all("<Control-Alt-t>", self.toggle_theme)
        self.root.bind_all("<Control-Shift-E>", lambda _event: self.explain_current_code())
        self.editor.bind("<Control-space>", self.show_completion)
        self.editor.bind("<F12>", self.go_to_definition)
        self.editor.bind("<Shift-F12>", self.show_symbol_references)
        self.editor.bind("<Control-Button-1>", self.go_to_definition)
        self.editor.bind("<Tab>", self.insert_spaces)
        self.editor.bind("<Shift-Tab>", self.unindent_selection)
        self.editor.bind("<Control-slash>", self.toggle_line_comment)
        self.editor.bind("<Control-d>", self.duplicate_line)
        self.editor.bind("<<Modified>>", self._editor_modified)
        self.editor.bind("<KeyRelease>", self._editor_activity)
        self.editor.bind("<ButtonRelease-1>", self._update_cursor)
        self.editor.bind("<MouseWheel>", lambda _event: self.root.after_idle(self.line_numbers.redraw))
        self.editor.bind("<Configure>", lambda _event: self.line_numbers.redraw())

    # ----------------------------------------------------------- projects/files
    def discover_projects(self) -> dict[str, Path]:
        projects: dict[str, Path] = {}
        if (WORKSPACE_ROOT / "fpga.config.psd1").exists():
            projects["00_workspace_starter"] = WORKSPACE_ROOT
        projects_root = WORKSPACE_ROOT / "projects"
        if projects_root.is_dir():
            for path in sorted(projects_root.iterdir(), key=lambda value: (value.name.startswith("_"), value.name)):
                if path.is_dir() and (path / "fpga.config.psd1").exists():
                    projects[f"projects/{path.name}"] = path.resolve()
        return projects

    def _refresh_projects(self, preferred: str | None = None) -> None:
        self.project_map = self.discover_projects()
        values = list(self.project_map)
        self.project_combo["values"] = values
        selected = preferred if preferred in self.project_map else None
        if selected is None and "projects/01_button_led_pwm" in self.project_map:
            selected = "projects/01_button_led_pwm"
        if selected is None and values:
            selected = values[0]
        if selected:
            self.project_var.set(selected)
            self.switch_project(self.project_map[selected], force=True)

    def _project_selected(self, _event=None) -> None:
        label = self.project_var.get()
        path = self.project_map.get(label)
        if path:
            self.switch_project(path)

    def switch_project(self, path: Path, force: bool = False) -> None:
        if not force and path == self.current_project:
            return
        if not force and not self._confirm_discard_or_save():
            current_label = next((label for label, value in self.project_map.items() if value == self.current_project), "")
            self.project_var.set(current_label)
            return
        self.current_project = path.resolve()
        self.settings["last_project"] = self._project_relative()
        self.settings["theme"] = self.theme_name
        save_user_settings(self.settings)
        LOGGER.info("Project selected: %s", self.current_project)
        self.current_file = None
        self.open_files.clear()
        self.dirty = False
        self.editor.delete("1.0", "end")
        self.editor.edit_modified(False)
        self.file_label.set("No file open")
        self._refresh_editor_tabs()
        self.populate_file_tree()
        self.analyze_project(False)
        first_file = self.current_project / "rtl" / "top.sv"
        if not first_file.exists():
            first_file = self.current_project / "README.md"
        if first_file.exists():
            self.open_file(first_file)
        self._append_console(f"\nSelected project: {self._project_relative()}\n", "command")

    def _project_relative(self) -> str:
        try:
            return self.current_project.relative_to(WORKSPACE_ROOT).as_posix() or "."
        except ValueError:
            return str(self.current_project)

    def populate_file_tree(self) -> None:
        self.file_tree.delete(*self.file_tree.get_children())
        self.tree_paths.clear()
        root_item = self.file_tree.insert(
            "", "end", text=self.current_project.name or "workspace", open=True, image=self.icons["folder"],
        )
        self.tree_paths[root_item] = self.current_project
        query = self.file_filter_var.get().strip().lower() if hasattr(self, "file_filter_var") else ""

        def has_match(path: Path, depth: int = 0) -> bool:
            if not query:
                return True
            if query in path.name.lower():
                return True
            if not path.is_dir() or depth > 8:
                return False
            try:
                return any(
                    has_match(child, depth + 1)
                    for child in path.iterdir()
                    if child.name not in IGNORED_TREE_NAMES and not child.name.startswith(".")
                )
            except (OSError, PermissionError):
                return False

        def add_children(parent_item: str, directory: Path, depth: int = 0) -> None:
            if depth > 8:
                return
            try:
                entries = sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            except (OSError, PermissionError):
                return
            for entry in entries:
                if entry.name in IGNORED_TREE_NAMES or entry.name.startswith("."):
                    continue
                if not has_match(entry, depth):
                    continue
                icon = "folder" if entry.is_dir() else "code" if entry.suffix.lower() in HDL_SUFFIXES else "file"
                item = self.file_tree.insert(
                    parent_item, "end", text=entry.name,
                    open=bool(query) or (depth < 1 and entry.name in {"rtl", "sim", "constraints"}),
                    image=self.icons[icon],
                )
                self.tree_paths[item] = entry
                if entry.is_dir():
                    add_children(item, entry, depth + 1)

        add_children(root_item, self.current_project)

    def _tree_open(self, _event=None) -> None:
        selected = self.file_tree.selection()
        if not selected:
            return
        path = self.tree_paths.get(selected[0])
        if path and path.is_file():
            self.open_file(path)

    def open_file(self, path: Path, line: int | None = None) -> None:
        path = path.resolve()
        try:
            path.relative_to(self.current_project)
        except ValueError:
            messagebox.showerror("Outside project", "The IDE only opens files inside the selected project.")
            return
        if path.suffix.lower() not in EDITABLE_SUFFIXES:
            messagebox.showinfo("Generated/binary file", f"{path.name} is not opened as editable text.")
            return
        if self.current_file != path and not self._confirm_discard_or_save():
            return
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            messagebox.showerror("Open failed", str(error))
            return
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)
        self.current_file = path
        if path in self.open_files:
            self.open_files.remove(path)
        self.open_files.append(path)
        self.open_files = self.open_files[-7:]
        self.dirty = False
        self.editor.edit_modified(False)
        self._update_file_label()
        self.highlight_syntax()
        if line:
            target = f"{max(1, line)}.0"
            self.editor.mark_set("insert", target)
            self.editor.see(target)
            self.editor.tag_remove("sel", "1.0", "end")
            self.editor.tag_add("sel", target, f"{target} lineend")
        self.line_numbers.redraw()
        self._update_cursor()

    def save_file(self) -> bool:
        if self.current_file is None:
            return True
        try:
            self.current_file.write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8", newline="\n")
        except OSError as error:
            messagebox.showerror("Save failed", str(error))
            return False
        self.dirty = False
        self.editor.edit_modified(False)
        self._update_file_label()
        self.status_text.set(f"Saved {self.current_file.name}")
        self.analyze_project(False)
        return True

    def _confirm_discard_or_save(self) -> bool:
        if not self.dirty:
            return True
        response = messagebox.askyesnocancel("Unsaved changes", "Save the current file before continuing?")
        if response is None:
            return False
        if response:
            return self.save_file()
        return True

    def _update_file_label(self) -> None:
        if self.current_file is None:
            self.file_label.set("No file open")
            return
        relative = self.current_file.relative_to(self.current_project).as_posix()
        self.file_label.set(("● " if self.dirty else "") + relative.replace("/", "  ›  "))
        self._refresh_editor_tabs()

    def _refresh_editor_tabs(self) -> None:
        if not hasattr(self, "editor_tabs"):
            return
        for child in self.editor_tabs.winfo_children():
            child.destroy()
        if not self.open_files:
            ttk.Label(self.editor_tabs, text="NO FILES OPEN", style="Eyebrow.TLabel").pack(side="left", padx=5)
            return
        for path in self.open_files:
            active = path == self.current_file
            text = ("● " if active and self.dirty else "") + path.name
            button = ttk.Button(
                self.editor_tabs, text=text, image=self.icons["code" if path.suffix.lower() in HDL_SUFFIXES else "file"],
                compound="left", style="Accent.TButton" if active else "Tab.TButton",
                command=lambda value=path: self.open_file(value),
            )
            button.pack(side="left", padx=(0, 3))
            try:
                relative = path.relative_to(self.current_project).as_posix()
            except ValueError:
                relative = str(path)
            Tooltip(button, relative)

    def _editor_modified(self, _event=None) -> None:
        if self.editor.edit_modified():
            self.dirty = True
            self._update_file_label()
            self.editor.edit_modified(False)

    def _editor_activity(self, _event=None) -> None:
        self._update_cursor()
        if self.highlight_job:
            self.root.after_cancel(self.highlight_job)
        self.highlight_job = self.root.after(180, self.highlight_syntax)

    def _update_cursor(self, _event=None) -> None:
        line, column = self.editor.index("insert").split(".")
        self.cursor_text.set(f"Ln {line}, Col {int(column) + 1}")
        self.editor.tag_remove("current_line", "1.0", "end")
        self.editor.tag_add("current_line", f"{line}.0", f"{line}.0 lineend+1c")
        self.editor.tag_lower("current_line")
        self._highlight_matching_bracket()

    def _highlight_matching_bracket(self) -> None:
        self.editor.tag_remove("matching_bracket", "1.0", "end")
        content = self.editor.get("1.0", "end-1c")
        if not content:
            return
        insert_offset = int(self.editor.count("1.0", "insert", "chars")[0])
        candidate = insert_offset - 1 if insert_offset and content[insert_offset - 1] in "()[]{}" else insert_offset
        if candidate < 0 or candidate >= len(content) or content[candidate] not in "()[]{}":
            return
        pairs = {"(": ")", "[": "]", "{": "}", ")": "(", "]": "[", "}": "{"}
        char = content[candidate]
        direction = 1 if char in "([{ " else -1
        target = pairs[char]
        depth = 0
        position = candidate
        while 0 <= position < len(content):
            current = content[position]
            if current == char:
                depth += 1
            elif current == target:
                depth -= 1
                if depth == 0:
                    for offset in (candidate, position):
                        start = f"1.0+{offset}c"
                        self.editor.tag_add("matching_bracket", start, f"{start}+1c")
                    return
            position += direction

    def insert_spaces(self, _event=None):
        self.editor.insert("insert", "    ")
        return "break"

    def unindent_selection(self, _event=None):
        try:
            first = int(self.editor.index("sel.first").split(".")[0])
            last = int(self.editor.index("sel.last").split(".")[0])
        except tk.TclError:
            first = last = int(self.editor.index("insert").split(".")[0])
        for line in range(first, last + 1):
            value = self.editor.get(f"{line}.0", f"{line}.4")
            remove = len(value) - len(value.lstrip(" "))
            if remove:
                self.editor.delete(f"{line}.0", f"{line}.{remove}")
        return "break"

    def toggle_line_comment(self, _event=None):
        if self.current_file is None:
            return "break"
        try:
            first = int(self.editor.index("sel.first").split(".")[0])
            last = int(self.editor.index("sel.last").split(".")[0])
        except tk.TclError:
            first = last = int(self.editor.index("insert").split(".")[0])
        values = [self.editor.get(f"{line}.0", f"{line}.0 lineend") for line in range(first, last + 1)]
        uncomment = all(not value.strip() or value.lstrip().startswith("//") for value in values)
        for line, value in zip(range(first, last + 1), values):
            if not value.strip():
                continue
            indent = len(value) - len(value.lstrip())
            if uncomment:
                marker = value.find("//", indent)
                if marker >= 0:
                    self.editor.delete(f"{line}.{marker}", f"{line}.{marker + 2}")
                    if self.editor.get(f"{line}.{marker}", f"{line}.{marker + 1}") == " ":
                        self.editor.delete(f"{line}.{marker}", f"{line}.{marker + 1}")
            else:
                self.editor.insert(f"{line}.{indent}", "// ")
        return "break"

    def duplicate_line(self, _event=None):
        if self.current_file is None:
            return "break"
        line = self.editor.index("insert").split(".")[0]
        value = self.editor.get(f"{line}.0", f"{line}.0 lineend")
        self.editor.insert(f"{line}.0 lineend", "\n" + value)
        self.editor.mark_set("insert", f"{int(line) + 1}.0 lineend")
        return "break"

    def _editor_yview(self, *args) -> None:
        self.editor.yview(*args)
        self.line_numbers.redraw()

    # --------------------------------------------------------------- editor IQ
    def highlight_syntax(self) -> None:
        self.highlight_job = None
        content = self.editor.get("1.0", "end-1c")
        if len(content) > 1_500_000:
            return
        for tag in ("keyword", "module", "signal", "comment", "string", "number", "directive"):
            self.editor.tag_remove(tag, "1.0", "end")

        def apply(tag: str, pattern: str, flags: int = 0) -> None:
            for match in re.finditer(pattern, content, flags):
                self.editor.tag_add(tag, f"1.0+{match.start()}c", f"1.0+{match.end()}c")

        keyword_pattern = r"\b(?:" + "|".join(map(re.escape, SYSTEMVERILOG_KEYWORDS)) + r")\b"
        apply("keyword", keyword_pattern)
        if self.current_index.modules:
            module_pattern = r"\b(?:" + "|".join(map(re.escape, self.current_index.modules)) + r")\b"
            apply("module", module_pattern)
        signal_names = {
            symbol.name
            for module in self.current_index.modules.values()
            for symbol in (*module.ports, *module.signals)
        }
        if signal_names:
            signal_pattern = r"\b(?:" + "|".join(map(re.escape, sorted(signal_names))) + r")\b"
            apply("signal", signal_pattern)
        apply("number", r"\b(?:\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+|\d[\d_]*)\b")
        apply("directive", r"(?m)^\s*`[A-Za-z_]\w*")
        apply("string", r'"(?:\\.|[^"\\])*"')
        apply("comment", r"//[^\n]*|/\*.*?\*/", re.DOTALL)
        self.editor.tag_raise("comment")
        self.editor.tag_raise("string")
        self.editor.tag_raise("module")
        self.line_numbers.redraw()

    def show_completion(self, _event=None):
        before = self.editor.get("insert linestart", "insert")
        match = re.search(r"([A-Za-z_]\w*)$", before)
        prefix = match.group(1) if match else ""
        if re.search(r"\.\s*[A-Za-z_]*$", before):
            port_words = {
                port.name for module in self.current_index.modules.values() for port in module.ports
            }
            candidates = sorted(
                (word for word in port_words if word.lower().startswith(prefix.lower()) and word != prefix),
                key=str.lower,
            )
        else:
            candidates = matching_completions(self.current_index, prefix)
        snippet_aliases = [name for name in HDL_SNIPPET_ALIASES if name.startswith(prefix.lower()) and name != prefix]
        if not candidates and not snippet_aliases:
            self.root.bell()
            return "break"
        menu = tk.Menu(self.root, tearoff=False, bg=COLORS["panel_alt"], fg=COLORS["text"],
                       activebackground=COLORS["selection"], activeforeground=COLORS["text"])
        for alias in snippet_aliases:
            snippet_name = HDL_SNIPPET_ALIASES[alias]
            menu.add_command(
                label=f"✦ {alias}  —  {snippet_name}",
                command=lambda key=alias: self._insert_snippet_completion(prefix, key),
            )
        if snippet_aliases and candidates:
            menu.add_separator()
        for candidate in candidates[:24 - len(snippet_aliases)]:
            menu.add_command(label=candidate, command=lambda value=candidate: self._insert_completion(prefix, value))
        bbox = self.editor.bbox("insert") or (0, 0, 0, 0)
        menu.tk_popup(self.editor.winfo_rootx() + bbox[0], self.editor.winfo_rooty() + bbox[1] + bbox[3])
        return "break"

    def _insert_completion(self, prefix: str, value: str) -> None:
        if prefix:
            self.editor.delete(f"insert-{len(prefix)}c", "insert")
        self.editor.insert("insert", value)

    def _insert_snippet_completion(self, prefix: str, alias: str) -> None:
        if prefix:
            self.editor.delete(f"insert-{len(prefix)}c", "insert")
        self._insert_snippet(HDL_SNIPPETS[HDL_SNIPPET_ALIASES[alias]])

    def go_to_definition(self, _event=None):
        word = self.editor.get("insert wordstart", "insert wordend").strip()
        definition = self.current_index.definition(word, self.current_file)
        if definition:
            self.open_file(*definition)
        else:
            self.status_text.set(f"No project symbol definition found for '{word}'.")
            self.root.bell()
        return "break"

    def show_symbol_references(self, _event=None):
        word = self.editor.get("insert wordstart", "insert wordend").strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", word):
            word = simpledialog.askstring("Find references", "HDL symbol:", parent=self.root) or ""
            word = word.strip()
        if not word:
            return "break" if _event is not None else None
        references = self.current_index.references(word)
        dialog = tk.Toplevel(self.root)
        dialog.title(f"References — {word}")
        dialog.geometry("900x520")
        dialog.minsize(680, 360)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)

        header = ttk.Frame(dialog, style="Top.TFrame", padding=(18, 16, 18, 10))
        header.pack(fill="x")
        ttk.Label(header, text=f"{len(references)} reference{'s' if len(references) != 1 else ''} to {word}",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Definitions and exact identifier uses in synthesizable project HDL. Double-click to open.",
            style="Status.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Frame(dialog, padding=(14, 6, 14, 14))
        body.pack(fill="both", expand=True)
        tree = ttk.Treeview(body, columns=("kind", "file", "line", "preview"), show="headings")
        for column, title, width in (
            ("kind", "Kind", 85), ("file", "File", 180),
            ("line", "Line", 55), ("preview", "Source", 480),
        ):
            tree.heading(column, text=title)
            tree.column(column, width=width, stretch=column in {"file", "preview"})
        locations: dict[str, object] = {}
        for location in references:
            try:
                relative = location.path.relative_to(self.current_project).as_posix()
            except ValueError:
                relative = str(location.path)
            item = tree.insert("", "end", values=(location.kind.title(), relative, location.line, location.preview))
            locations[item] = location
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def open_selected(_event=None) -> None:
            selected = tree.selection()
            location = locations.get(selected[0]) if selected else None
            if location:
                self.open_file(location.path, location.line)
                dialog.destroy()

        tree.bind("<Double-1>", open_selected)
        tree.bind("<Return>", open_selected)
        if references:
            first = tree.get_children()[0]
            tree.selection_set(first)
            tree.focus(first)
        else:
            self.status_text.set(f"No references found for '{word}'.")
        return "break" if _event is not None else None

    def generate_module_instance(self) -> None:
        modules = sorted(self.current_index.modules, key=str.lower)
        if not modules:
            messagebox.showinfo("No modules indexed", "Add or save an HDL module, then run Analyze.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Generate module instance")
        dialog.geometry("700x520")
        dialog.minsize(580, 420)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)
        dialog.grab_set()

        header = ttk.Frame(dialog, style="Top.TFrame", padding=(18, 16, 18, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Generate a named-port instance", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Ports come from the live HDL index; edit signal names after insertion.",
                  style="Status.TLabel").pack(anchor="w", pady=(3, 0))
        form = ttk.Frame(dialog, padding=(18, 10))
        form.pack(fill="x")
        ttk.Label(form, text="Module").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        module_var = tk.StringVar(value=modules[0])
        module_combo = ttk.Combobox(form, textvariable=module_var, values=modules, state="readonly", width=28)
        module_combo.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="Instance name").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        instance_var = tk.StringVar(value=f"u_{modules[0]}")
        instance_entry = ttk.Entry(form, textvariable=instance_var)
        instance_entry.grid(row=1, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)
        preview = tk.Text(
            dialog, height=14, wrap="none", bg=COLORS["editor"], fg=COLORS["text"],
            insertbackground=COLORS["cursor"], selectbackground=COLORS["selection"],
            relief="flat", padx=12, pady=10, font=("Cascadia Code", 10), state="disabled",
        )
        preview.pack(fill="both", expand=True, padx=18, pady=(4, 10))

        def refresh(*_args) -> None:
            if module_var.get() and not instance_var.get().strip():
                instance_var.set(f"u_{module_var.get()}")
                return
            try:
                value = self.current_index.module_instantiation(module_var.get(), instance_var.get().strip())
            except (KeyError, ValueError) as error:
                value = f"// {error}"
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", value)
            preview.configure(state="disabled")

        module_var.trace_add("write", refresh)
        instance_var.trace_add("write", refresh)
        refresh()
        actions = ttk.Frame(dialog, padding=(18, 0, 18, 16))
        actions.pack(fill="x")

        def insert() -> None:
            try:
                value = self.current_index.module_instantiation(module_var.get(), instance_var.get().strip())
            except (KeyError, ValueError) as error:
                messagebox.showerror("Cannot generate instance", str(error), parent=dialog)
                return
            self.editor.insert("insert", value + "\n")
            dialog.destroy()
            self.editor.focus_set()

        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")
        self._action_button(actions, "Insert into editor", "plus", insert, "Accent.TButton").pack(side="right", padx=8)

    def analyze_project(self, report_to_console: bool = False) -> None:
        self.current_index = scan_project(self.current_project)
        self._populate_outline()
        self._populate_problems()
        self._refresh_coach()
        self._refresh_insights()
        self._refresh_device_status()
        self.highlight_syntax()
        errors = sum(item.severity == "error" for item in self.current_index.diagnostics)
        warnings = sum(item.severity == "warning" for item in self.current_index.diagnostics)
        if errors:
            self.status_text.set(f"Smart check: {errors} error(s), {warnings} warning(s)")
        elif warnings:
            self.status_text.set(f"Smart check: {warnings} warning(s)")
        else:
            self.status_text.set(f"Smart check passed — {len(self.current_index.modules)} module(s) recognized")
        if report_to_console:
            self._append_console("\n> Smart project check\n", "command")
            if not self.current_index.diagnostics:
                self._append_console(
                    f"PASS: {len(self.current_index.modules)} modules recognized; no beginner checks failed.\n",
                    "success",
                )
            for diagnostic in self.current_index.diagnostics:
                location = self._diagnostic_location(diagnostic)
                self._append_console(
                    f"{diagnostic.severity.upper()} {diagnostic.code} {location}: {diagnostic.message}\n",
                    "error" if diagnostic.severity == "error" else "warning" if diagnostic.severity == "warning" else "muted",
                )

    def _populate_outline(self) -> None:
        self.outline_tree.delete(*self.outline_tree.get_children())
        self.outline_locations.clear()
        for module in sorted(
            self.current_index.modules.values(),
            key=lambda item: (item.name != self.current_index.top_name, item.name.lower()),
        ):
            module_item = self.outline_tree.insert(
                "", "end", text=f"module {module.name}", open=module.name == self.current_index.top_name,
            )
            self.outline_locations[module_item] = (module.path, module.line)
            port_group = self.outline_tree.insert(module_item, "end", text=f"Ports  {len(module.ports)}", open=True)
            for port in module.ports:
                width = f" {port.width}" if port.width else ""
                item = self.outline_tree.insert(port_group, "end", text=f"{port.direction}{width}  {port.name}")
                self.outline_locations[item] = (module.path, port.line)
            if module.instances:
                instance_group = self.outline_tree.insert(
                    module_item, "end", text=f"Instances  {len(module.instances)}", open=True,
                )
            else:
                instance_group = module_item
            for instance in module.instances:
                item = self.outline_tree.insert(
                    instance_group, "end", text=f"{instance.name}  :  {instance.module_type}"
                )
                self.outline_locations[item] = (module.path, instance.line)
            if module.signals:
                signal_group = self.outline_tree.insert(
                    module_item, "end", text=f"Signals  {len(module.signals)}", open=False,
                )
                for signal in module.signals[:80]:
                    width = f" {signal.width}" if signal.width else ""
                    item = self.outline_tree.insert(signal_group, "end", text=f"{signal.kind}{width}  {signal.name}")
                    self.outline_locations[item] = (module.path, signal.line)

    def _populate_problems(self) -> None:
        self.problems_tree.delete(*self.problems_tree.get_children())
        self.problem_items.clear()
        for diagnostic in self.current_index.diagnostics:
            location = self._diagnostic_location(diagnostic)
            item = self.problems_tree.insert(
                "", "end", text=f"[{diagnostic.code}] {diagnostic.message}",
                values=(diagnostic.severity.upper(), location), tags=(diagnostic.severity,),
            )
            self.problem_items[item] = diagnostic
        count = len(self.current_index.diagnostics)
        self.problem_count.set(f"{count} problem{'s' if count != 1 else ''}")
        has_fix = any(item.code in {"STYLE001", "SIM001"} for item in self.current_index.diagnostics)
        self.quick_fix_button.configure(state="normal" if has_fix else "disabled")

    def _refresh_device_status(self) -> None:
        config = self.current_project / "fpga.config.psd1"
        if not config.exists():
            self.device_text.set("Device not configured")
            return
        text = config.read_text(encoding="utf-8", errors="replace")
        device = re.search(r"(?m)^\s*Family\s*=\s*['\"]([^'\"]+)", text)
        clock = re.search(r"(?m)^\s*ClockMHz\s*=\s*([0-9.]+)", text)
        self.device_text.set(
            f"{device.group(1) if device else 'Tang Primer 20K'}  •  {clock.group(1) if clock else '?'} MHz"
        )

    def _refresh_insights(self) -> None:
        insight = load_project_insights(self.current_project, self.current_index)
        self.health_text.set(f"Health {insight.score}/100  •  {insight.grade}")
        self.insights.configure(state="normal")
        self.insights.delete("1.0", "end")
        score_tag = "score" if insight.score >= 80 else "next" if insight.score >= 60 else "blocked"
        self.insights.insert("end", f"{insight.score}", score_tag)
        self.insights.insert("end", "/100\n", "muted")
        self.insights.insert("end", insight.grade + "\n", "title")
        self.insights.insert("end", insight.summary + "\n\n", "muted")

        self.insights.insert("end", "WORKFLOW READINESS\n", "heading")
        for label, state, detail in workflow_steps(self.current_project, self.current_index, self.session_passes):
            marker = "●" if state == "ready" else "◆" if state == "next" else "○"
            tag = "good" if state == "ready" else "next" if state in {"next", "optional"} else "blocked"
            self.insights.insert("end", f"{marker} {label}\n", tag)
            self.insights.insert("end", f"    {detail}\n", "muted")

        self.insights.insert("end", "\nDESIGN SNAPSHOT\n", "heading")
        module_count = len(self.current_index.modules)
        port_count = sum(len(module.ports) for module in self.current_index.modules.values())
        signal_count = sum(len(module.signals) for module in self.current_index.modules.values())
        self.insights.insert("end", f"{module_count} modules  •  {port_count} ports  •  {signal_count} indexed signals\n")
        top = self.current_index.modules.get(self.current_index.top_name)
        if top:
            pin_assignments = 0
            config = self.current_project / "fpga.config.psd1"
            config_text = config.read_text(encoding="utf-8", errors="replace") if config.exists() else ""
            constraint_match = re.search(r"(?m)^\s*Constraint\s*=\s*['\"]([^'\"]+)", config_text)
            constraint = self.current_project / (
                constraint_match.group(1) if constraint_match else "constraints/primer20k_dock.cst"
            )
            if constraint.exists():
                pin_assignments = len(re.findall(r'(?m)^\s*IO_LOC\s+"', constraint.read_text(encoding="utf-8", errors="replace")))
            pin_errors = sum(item.code in {"PIN001", "PIN002", "PIN003", "PIN004"} for item in self.current_index.diagnostics)
            self.insights.insert(
                "end", f"Pins  {pin_assignments} physical assignments  •  {len(top.ports)} logical port groups\n",
                "good" if not pin_errors else "blocked",
            )
        if insight.achieved_mhz is not None:
            timing_tag = "good" if insight.target_mhz is None or insight.achieved_mhz >= insight.target_mhz else "blocked"
            self.insights.insert("end", f"Timing  {insight.achieved_mhz:.1f} MHz achieved", timing_tag)
            if insight.target_mhz is not None:
                self.insights.insert("end", f"  /  {insight.target_mhz:g} MHz target")
            self.insights.insert("end", "\n")
        else:
            self.insights.insert("end", "No timing report yet — run Build.\n", "muted")

        if top:
            self.insights.insert("end", "\nMODULE HIERARCHY\n", "heading")
            self.insights.insert("end", f"{top.name}  (top)\n", "good")

            def append_children(module_name: str, prefix: str, seen: set[str]) -> None:
                module = self.current_index.modules.get(module_name)
                if module is None or module_name in seen:
                    return
                next_seen = seen | {module_name}
                for position, instance in enumerate(module.instances):
                    last = position == len(module.instances) - 1
                    connector = "└─" if last else "├─"
                    self.insights.insert("end", f"{prefix}{connector} {instance.name} : {instance.module_type}\n")
                    append_children(instance.module_type, prefix + ("   " if last else "│  "), next_seen)

            append_children(top.name, "", set())

        if insight.resources:
            self.insights.insert("end", "\nDEVICE UTILIZATION\n", "heading")
            for resource in insight.resources:
                blocks = min(10, int(round(resource.percent / 10)))
                bar = "█" * blocks + "░" * (10 - blocks)
                self.insights.insert(
                    "end", f"{resource.name:<10} {bar}  {resource.used:,}/{resource.available:,}  ({resource.percent:.1f}%)\n",
                    "good" if resource.percent < 70 else "next" if resource.percent < 90 else "blocked",
                )
        self.insights.insert("end", "\nARTIFACTS\n", "heading")
        self.insights.insert(
            "end", f"Bitstream  {self._format_bytes(insight.bitstream_bytes)}\n"
                   f"Waveform   {self._format_bytes(insight.waveform_bytes)}\n",
        )
        if insight.build_time:
            self.insights.insert("end", f"Last build  {insight.build_time:%Y-%m-%d %H:%M}\n", "muted")
        self.insights.configure(state="disabled")

    @staticmethod
    def _format_bytes(value: int | None) -> str:
        if value is None:
            return "Not generated"
        if value >= 1_048_576:
            return f"{value / 1_048_576:.1f} MiB"
        if value >= 1024:
            return f"{value / 1024:.1f} KiB"
        return f"{value} B"

    def show_project_insights(self) -> None:
        self._refresh_insights()
        self.intelligence_notebook.select(3)

    def _diagnostic_location(self, diagnostic: Diagnostic) -> str:
        if diagnostic.path is None:
            return "project"
        try:
            relative = diagnostic.path.relative_to(self.current_project).as_posix()
        except ValueError:
            relative = diagnostic.path.name
        return f"{relative}:{diagnostic.line}"

    def _outline_open(self, _event=None) -> None:
        selected = self.outline_tree.selection()
        if selected and selected[0] in self.outline_locations:
            self.open_file(*self.outline_locations[selected[0]])

    def _problem_open(self, _event=None) -> None:
        selected = self.problems_tree.selection()
        if not selected:
            return
        diagnostic = self.problem_items.get(selected[0])
        if diagnostic and diagnostic.path and diagnostic.path.exists() and diagnostic.path.is_file():
            self.open_file(diagnostic.path, diagnostic.line)

    def _problem_selected(self, _event=None) -> None:
        selected = self.problems_tree.selection()
        if not selected:
            return
        diagnostic = self.problem_items.get(selected[0])
        if diagnostic:
            self._refresh_coach(diagnostic)
            self.quick_fix_button.configure(
                state="normal" if diagnostic.code in {"STYLE001", "SIM001"} else "disabled",
            )

    def _refresh_coach(self, selected: Diagnostic | None = None) -> None:
        self.coach.configure(state="normal")
        self.coach.delete("1.0", "end")
        self.coach.insert("end", "Beginner Coach\n", "title")
        self.coach.insert("end", f"Project: {self._project_relative()}\n\n", "muted")
        if selected:
            self.coach.insert("end", f"{selected.severity.upper()} {selected.code}\n", "heading")
            self.coach.insert("end", selected.message + "\n\n")
            if selected.suggestion:
                self.coach.insert("end", "Suggested fix\n", "heading")
                self.coach.insert("end", selected.suggestion + "\n\n")
        errors = sum(item.severity == "error" for item in self.current_index.diagnostics)
        warnings = sum(item.severity == "warning" for item in self.current_index.diagnostics)
        if not errors and not warnings:
            self.coach.insert("end", "✓ Project structure checks pass.\n\n", "good")
        else:
            self.coach.insert("end", f"Resolve {errors} error(s) and review {warnings} warning(s).\n\n", "warning")
        self.coach.insert("end", "Safe workflow\n", "heading")
        self.coach.insert("end", "1. Edit RTL under rtl/.\n2. Add expectations to sim/tb_top.sv.\n"
                          "3. Simulate and inspect GTKWave.\n4. Lint and build.\n"
                          "5. Upload to SRAM.\n6. Flash only after hardware behavior is correct.\n\n")
        self.coach.insert("end", "Editor intelligence\n", "heading")
        self.coach.insert("end", "• Ctrl+Space: project, port, and signal completion\n• F12 / Ctrl+Click: go to symbol definition\n"
                          "• Shift+F12: find exact project references\n"
                          "• Generate module instance: create named port wiring\n"
                          "• Double-click Outline/Problems entries to navigate\n"
                          "• Smart check validates hierarchy, pins, testbench, and RTL hazards\n"
                          "• Ctrl+Shift+P: searchable command palette\n"
                          "• Ctrl+Shift+F: search every project source\n"
                          "• Ctrl+Alt+S: insert verified HDL patterns\n"
                          "• Ctrl+Alt+T: switch accessible dark/light mode\n"
                          "• Insights: timing, utilization, artifacts, and hardware readiness\n")
        self.coach.configure(state="disabled")

    # ---------------------------------------------------------- power features
    def _center_toplevel(self, window: tk.Toplevel, width: int, height: int) -> None:
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + max(20, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(20, (self.root.winfo_height() - height) // 3)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.configure(bg=COLORS["bg"])
        window.transient(self.root)

    def _command_catalog(self):
        return [
            ("Run: Simulate", "Run the self-checking RTL testbench", "F5", lambda: self.run_fpga("sim")),
            ("Run: Open waveform", "Simulate and inspect saved signals in GTKWave", "F6", lambda: self.run_fpga("wave")),
            ("Run: Lint", "Analyze RTL with Verilator", "F7", lambda: self.run_fpga("lint")),
            ("Run: Debug flow", "Lint, simulate and open the waveform", "F8", lambda: self.run_fpga("debug")),
            ("Hardware: Build bitstream", "Synthesize, place/route and pack", "Ctrl+B", lambda: self.run_fpga("build")),
            ("Hardware: Upload SRAM", "Fast volatile hardware test", "F9", lambda: self.run_fpga("upload")),
            ("Hardware: Flash persistent", "Write configuration flash after verification", "", lambda: self.run_fpga("flash")),
            ("Hardware: Detect JTAG", "Scan the attached FPGA chain", "", lambda: self.run_fpga("detect")),
            ("Hardware: Doctor", "Inspect tools, USB interfaces and UART", "", lambda: self.run_fpga("doctor")),
            ("Hardware: Guided setup", "JTAG, UART, driver, cable, and switch guidance", "", self.show_hardware_setup),
            ("Create: New project", "Choose a complete verified starting point", "", self.new_project),
            ("Create: New HDL module", "Generate a safe SystemVerilog skeleton", "", self.new_module),
            ("Code: Insert HDL snippet", "Use a reviewed sequential/combinational pattern", "Ctrl+Alt+S", self.show_snippets),
            ("Code: Explain selection", "Explain the current HDL construct and safer usage", "Ctrl+Shift+E", self.explain_current_code),
            ("Code: Search project", "Find text across sources, constraints and docs", "Ctrl+Shift+F", self.show_project_search),
            ("Code: Find references", "Find exact identifier uses across project HDL", "Shift+F12", self.show_symbol_references),
            ("Code: Generate instance", "Create named port connections from an indexed module", "", self.generate_module_instance),
            ("View: Toggle dark/light mode", "Switch the complete live workspace theme", "Ctrl+Alt+T", self.toggle_theme),
            ("Intelligence: Smart check", "Refresh actionable design diagnostics", "", lambda: self.analyze_project(True)),
            ("Intelligence: Project insights", "Review health, timing, utilization and readiness", "", self.show_project_insights),
            ("Intelligence: View synthesized netlist", "Search cells and inspect local connectivity", "", self.show_netlist_viewer),
            ("Intelligence: Inspect pin map", "Review signal, package pin, voltage standard and source line", "", self.show_pin_inspector),
            ("Intelligence: Apply quick fix", "Apply a safe fix to the selected problem", "", self.apply_quick_fix),
            ("Tools: Verification center", "Select a testbench, assertions, and waveform layout", "", self.show_verification_center),
            ("Tools: UART terminal", "Auto-detect COM ports, send/receive, inspect hex, and save logs", "", self.open_serial_monitor),
            ("Tools: Open project folder", "Reveal the selected project in Explorer", "", self.open_project_folder),
            ("Help: What's new in 1.2.0", "Reopen this version's release highlights", "", self.show_release_notes),
            ("Help: First-project tutorial", "Follow the complete verified workflow step by step", "", self.show_first_project_tutorial),
            ("Help: Project guide", "Open the project guide and coach", "", self.show_beginner_guide),
        ]

    def show_command_palette(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Command Palette")
        self._center_toplevel(window, 700, 500)
        shell = tk.Frame(window, bg=COLORS["panel"], highlightthickness=1,
                         highlightbackground=COLORS["border"])
        shell.pack(fill="both", expand=True, padx=12, pady=12)
        header = tk.Frame(shell, bg=COLORS["panel"])
        header.pack(fill="x", padx=16, pady=(15, 8))
        tk.Label(header, image=self.icons["command"], bg=COLORS["panel"]).pack(side="left", padx=(0, 9))
        copy = tk.Frame(header, bg=COLORS["panel"])
        copy.pack(side="left")
        tk.Label(copy, text="Command Palette", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(copy, text="Type an action, workflow, or tool name", bg=COLORS["panel"], fg=COLORS["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w")
        query = tk.StringVar()
        entry = tk.Entry(shell, textvariable=query, bg=COLORS["panel_alt"], fg=COLORS["text"],
                         insertbackground=COLORS["cursor"], relief="flat", font=("Segoe UI", 12))
        entry.pack(fill="x", padx=16, ipady=9)
        listbox = tk.Listbox(
            shell, bg=COLORS["panel"], fg=COLORS["text"], selectbackground=COLORS["selection"],
            selectforeground=COLORS["selection_text"], relief="flat", activestyle="none", font=("Segoe UI", 10),
            highlightthickness=0,
        )
        listbox.pack(fill="both", expand=True, padx=12, pady=(8, 3))
        detail = tk.StringVar(value="Select a command")
        tk.Label(shell, textvariable=detail, bg=COLORS["panel_alt"], fg=COLORS["muted"],
                 anchor="w", padx=12, pady=8, font=("Segoe UI", 9)).pack(fill="x")
        visible = []

        def refresh(*_args) -> None:
            needle = query.get().strip().lower()
            visible.clear()
            visible.extend(
                item for item in self._command_catalog()
                if not needle or needle in (item[0] + " " + item[1]).lower()
            )
            listbox.delete(0, "end")
            for title, _description, shortcut, _callback in visible:
                suffix = f"     {shortcut}" if shortcut else ""
                listbox.insert("end", "  " + title + suffix)
            if visible:
                listbox.selection_set(0)
                detail.set(visible[0][1])

        def selection_changed(_event=None) -> None:
            selected = listbox.curselection()
            if selected and selected[0] < len(visible):
                detail.set(visible[selected[0]][1])

        def execute(_event=None):
            selected = listbox.curselection()
            if not selected or selected[0] >= len(visible):
                return "break"
            callback = visible[selected[0]][3]
            window.destroy()
            self.root.after_idle(callback)
            return "break"

        query.trace_add("write", refresh)
        listbox.bind("<<ListboxSelect>>", selection_changed)
        listbox.bind("<Double-1>", execute)
        listbox.bind("<Return>", execute)
        entry.bind("<Return>", execute)
        entry.bind("<Down>", lambda _event: (listbox.focus_set(), listbox.selection_set(0)))
        window.bind("<Escape>", lambda _event: window.destroy())
        refresh()
        entry.focus_set()

    def show_project_search(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Search Project")
        self._center_toplevel(window, 900, 590)
        shell = ttk.Frame(window, padding=14)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, image=self.icons["search"], text="  Search this project", compound="left",
                  font=("Segoe UI Semibold", 16)).pack(anchor="w")
        ttk.Label(shell, text="Sources, constraints, simulations, scripts and documentation",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        query = tk.StringVar()
        search_entry = tk.Entry(
            shell, textvariable=query, bg=COLORS["panel_alt"], fg=COLORS["text"],
            insertbackground=COLORS["cursor"], relief="flat", font=("Segoe UI", 11),
        )
        search_entry.pack(fill="x", ipady=8)
        result_tree = ttk.Treeview(shell, columns=("file", "line", "preview"), show="headings")
        result_tree.heading("file", text="File")
        result_tree.heading("line", text="Line")
        result_tree.heading("preview", text="Match")
        result_tree.column("file", width=240, stretch=False)
        result_tree.column("line", width=60, stretch=False, anchor="center")
        result_tree.column("preview", width=540, stretch=True)
        result_tree.pack(fill="both", expand=True, pady=(10, 5))
        result_count = tk.StringVar(value="Enter at least two characters")
        ttk.Label(shell, textvariable=result_count, style="Muted.TLabel").pack(anchor="w")
        locations: dict[str, tuple[Path, int]] = {}
        search_job: str | None = None

        def perform() -> None:
            nonlocal search_job
            search_job = None
            needle = query.get().strip()
            result_tree.delete(*result_tree.get_children())
            locations.clear()
            if len(needle) < 2:
                result_count.set("Enter at least two characters")
                return
            lowered = needle.lower()
            total = 0
            for path in sorted(self.current_project.rglob("*"), key=lambda item: str(item).lower()):
                if total >= 300:
                    break
                if not path.is_file() or path.suffix.lower() not in EDITABLE_SUFFIXES:
                    continue
                if any(part in IGNORED_TREE_NAMES or part == "build" for part in path.relative_to(self.current_project).parts):
                    continue
                try:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for line_number, value in enumerate(lines, 1):
                    if lowered in value.lower():
                        relative = path.relative_to(self.current_project).as_posix()
                        item = result_tree.insert("", "end", values=(relative, line_number, value.strip()[:180]))
                        locations[item] = (path, line_number)
                        total += 1
                        if total >= 300:
                            break
            suffix = " (first 300)" if total >= 300 else ""
            result_count.set(f"{total} match{'es' if total != 1 else ''}{suffix}")

        def schedule(*_args) -> None:
            nonlocal search_job
            if search_job:
                window.after_cancel(search_job)
            search_job = window.after(220, perform)

        def open_result(_event=None) -> None:
            selected = result_tree.selection()
            if selected and selected[0] in locations:
                self.open_file(*locations[selected[0]])
                window.destroy()

        query.trace_add("write", schedule)
        result_tree.bind("<Double-1>", open_result)
        result_tree.bind("<Return>", open_result)
        window.bind("<Escape>", lambda _event: window.destroy())
        try:
            selected_text = self.editor.get("sel.first", "sel.last").strip()
        except tk.TclError:
            selected_text = self.editor.get("insert wordstart", "insert wordend").strip()
        if selected_text and "\n" not in selected_text:
            query.set(selected_text)
        search_entry.focus_set()

    def show_snippets(self) -> None:
        can_insert = self.current_file is not None and self.current_file.suffix.lower() in HDL_SUFFIXES
        window = tk.Toplevel(self.root)
        window.title("HDL Pattern Library")
        self._center_toplevel(window, 1160, 800)
        shell = ttk.Frame(window, padding=14)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, image=self.icons["sparkle"], text="  HDL Pattern Library", compound="left",
                  font=("Segoe UI Semibold", 16)).pack(anchor="w")
        ttk.Label(
            shell,
            text=f"{len(PATTERNS)} reviewed references with scope, difficulty, explanation, and insertion-ready code",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        controls = ttk.Frame(shell)
        controls.pack(fill="x", pady=(0, 10))
        query = tk.StringVar()
        category = tk.StringVar(value="All categories")
        difficulty = tk.StringVar(value="All levels")
        result_count = tk.StringVar()
        ttk.Label(controls, image=self.icons["search"], text="  Search", compound="left",
                  style="Muted.TLabel").pack(side="left", padx=(0, 7))
        search_entry = ttk.Entry(controls, textvariable=query)
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        category_box = ttk.Combobox(
            controls, textvariable=category, state="readonly",
            values=("All categories", *CATEGORIES), width=25,
        )
        category_box.pack(side="left", padx=(0, 8))
        difficulty_box = ttk.Combobox(
            controls, textvariable=difficulty, state="readonly",
            values=("All levels", *DIFFICULTIES), width=14,
        )
        difficulty_box.pack(side="left", padx=(0, 8))
        ttk.Label(controls, textvariable=result_count, style="Muted.TLabel", width=12).pack(side="right")

        body = ttk.Panedwindow(shell, orient="horizontal")
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=2)
        body.add(right, weight=5)
        matches: list[HDLPattern] = []
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True, padx=(0, 8))
        listbox = tk.Listbox(
            list_frame, bg=COLORS["panel_alt"], fg=COLORS["text"], selectbackground=COLORS["selection"],
            selectforeground=COLORS["selection_text"], relief="flat", activestyle="none", font=("Segoe UI", 10),
            width=39, exportselection=False,
        )
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=list_scroll.set)
        listbox.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")

        pattern_title = tk.StringVar()
        pattern_meta = tk.StringVar()
        pattern_summary = tk.StringVar()
        ttk.Label(right, textvariable=pattern_title, font=("Segoe UI Semibold", 13),
                  foreground=COLORS["cyan"]).pack(anchor="w")
        ttk.Label(right, textvariable=pattern_meta, style="Muted.TLabel").pack(anchor="w", pady=(2, 5))
        ttk.Label(right, textvariable=pattern_summary, wraplength=720, justify="left").pack(
            anchor="w", fill="x", pady=(0, 9),
        )
        preview_frame = ttk.Frame(right)
        preview_frame.pack(fill="both", expand=True)
        preview = tk.Text(
            preview_frame, bg=COLORS["editor"], fg=COLORS["text"], insertbackground=COLORS["cursor"],
            relief="flat", font=("Cascadia Code", 10), padx=12, pady=12, wrap="none", state="disabled",
            width=58,
        )
        preview_y = ttk.Scrollbar(preview_frame, orient="vertical", command=preview.yview)
        preview_x = ttk.Scrollbar(preview_frame, orient="horizontal", command=preview.xview)
        preview.configure(yscrollcommand=preview_y.set, xscrollcommand=preview_x.set)
        preview.grid(row=0, column=0, sticky="nsew")
        preview_y.grid(row=0, column=1, sticky="ns")
        preview_x.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        footer = ttk.Frame(shell, padding=(0, 10, 0, 0))
        footer.pack(side="bottom", fill="x")
        footer_hint = (
            "Insert uses the current line indentation. Review parameters and simulate after adapting."
            if can_insert else
            "Reference mode: open a Verilog/SystemVerilog file to enable insertion."
        )
        ttk.Label(footer, text=footer_hint, style="Muted.TLabel").pack(side="left")
        insert_button = self._action_button(footer, "Insert pattern", "plus", lambda: insert_selected(),
                                            "Accent.TButton")
        insert_button.pack(side="right")
        copy_button = ttk.Button(footer, text="Copy code", command=lambda: copy_selected())
        copy_button.pack(side="right", padx=(0, 8))
        body.pack(fill="both", expand=True)

        def selected_pattern() -> HDLPattern | None:
            selection = listbox.curselection()
            if not selection or selection[0] >= len(matches):
                return None
            return matches[selection[0]]

        def refresh_preview(_event=None) -> None:
            pattern = selected_pattern()
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            if pattern is None:
                pattern_title.set("No matching patterns")
                pattern_meta.set("Try another search term or filter.")
                pattern_summary.set("")
                insert_button.configure(state="disabled")
                copy_button.configure(state="disabled")
            else:
                scope = "SYNTHESIZABLE RTL" if pattern.synthesizable else "SIMULATION ONLY"
                aliases = ", ".join(pattern.aliases)
                pattern_title.set(pattern.title)
                pattern_meta.set(
                    f"{pattern.category}  |  {pattern.difficulty}  |  {scope}  |  aliases: {aliases}"
                )
                pattern_summary.set(pattern.summary)
                preview.insert("1.0", pattern.code)
                insert_button.configure(state="normal" if can_insert else "disabled")
                copy_button.configure(state="normal")
            preview.configure(state="disabled")

        def insert_selected(_event=None) -> None:
            pattern = selected_pattern()
            if pattern is None or not can_insert:
                return
            self._insert_snippet(pattern.code)
            self.status_text.set(f"Inserted pattern: {pattern.title}")
            window.destroy()

        def copy_selected() -> None:
            pattern = selected_pattern()
            if pattern is None:
                return
            self.root.clipboard_clear()
            self.root.clipboard_append(pattern.code)
            self.status_text.set(f"Copied pattern: {pattern.title}")

        def refresh_results(*_args) -> None:
            matches[:] = search_patterns(query.get(), category.get(), difficulty.get())
            listbox.delete(0, "end")
            for pattern in matches:
                listbox.insert("end", "  " + pattern.title)
            result_count.set(f"{len(matches)} / {len(PATTERNS)}")
            if matches:
                listbox.selection_set(0)
                listbox.activate(0)
            refresh_preview()

        listbox.bind("<<ListboxSelect>>", refresh_preview)
        listbox.bind("<Double-1>", insert_selected)
        query.trace_add("write", refresh_results)
        category_box.bind("<<ComboboxSelected>>", refresh_results)
        difficulty_box.bind("<<ComboboxSelected>>", refresh_results)
        window.bind("<Control-f>", lambda _event: search_entry.focus_set())
        window.bind("<Escape>", lambda _event: window.destroy())
        refresh_results()
        search_entry.focus_set()

    def _insert_snippet(self, snippet: str) -> None:
        line_start = self.editor.get("insert linestart", "insert")
        indent = re.match(r"\s*", line_start).group(0)
        value = snippet.replace("\n", "\n" + indent)
        if line_start.strip():
            value = "\n" + indent + value
        self.editor.insert("insert", value)
        self.editor.focus_set()

    def explain_current_code(self) -> None:
        if self.current_file is None or self.current_file.suffix.lower() not in HDL_SUFFIXES:
            messagebox.showinfo("Explain HDL", "Open a Verilog/SystemVerilog source file first.")
            return
        try:
            selection = self.editor.get("sel.first", "sel.last").strip()
        except tk.TclError:
            selection = self.editor.get("insert linestart", "insert lineend").strip()
        word = self.editor.get("insert wordstart", "insert wordend").strip()
        facts: list[tuple[str, str]] = []
        if "always_ff" in selection:
            facts.append(("Sequential process", "always_ff models registers updated on a clock edge. Use nonblocking <= assignments inside it."))
        if "always_comb" in selection:
            facts.append(("Combinational process", "always_comb recalculates from every signal it reads. Assign every output on every path to prevent latches."))
        if re.search(r"\balways\s*@\s*\(\s*posedge", selection):
            facts.append(("Clocked process", "This is edge-triggered sequential logic. always_ff is clearer when the file is SystemVerilog."))
        if re.search(r"\bassign\b", selection):
            facts.append(("Continuous assignment", "The left side continuously follows the expression and does not store state."))
        if re.search(r"\b(?:input|output|inout)\b", selection):
            facts.append(("Module interface", "This signal crosses the module boundary. Top-level interfaces also require board pin and IO standard constraints."))
        if re.search(r"\b(?:parameter|localparam)\b", selection):
            facts.append(("Compile-time constant", "Parameters make modules reusable; localparam protects internal constants from external override."))
        if re.search(r"\bcase(?:x|z)?\b", selection):
            facts.append(("Decision structure", "Provide an explicit default branch and a safe recovery state for finite-state machines."))
        if "<=" in selection:
            facts.append(("Nonblocking assignment", "The update is scheduled for the end of the time step, which matches parallel register behavior."))
        if re.search(r"(?<![<>=!])=(?!=)", selection):
            facts.append(("Blocking assignment", "This executes immediately. It is normally preferred for intermediate values in combinational logic."))
        if "#" in selection and self.current_file.parent.name == "rtl":
            facts.append(("Synthesis caution", "A numeric # delay belongs in sim/ testbench code, not synthesizable RTL."))

        module = self.current_index.modules.get(word)
        if module:
            relative = module.path.relative_to(self.current_project).as_posix()
            facts.append((
                f"Project module: {word}",
                f"Defined at {relative}:{module.line} with {len(module.ports)} ports, "
                f"{len(module.instances)} child instances and {len(module.signals)} indexed internal signals.",
            ))
        for owner in self.current_index.modules.values():
            port = next((item for item in owner.ports if item.name == word), None)
            if port:
                width = f" {port.width}" if port.width else " scalar"
                facts.append((f"{port.direction.title()} port: {word}", f"{owner.name} interface signal;{width}."))
                break
            signal = next((item for item in owner.signals if item.name == word), None)
            if signal:
                width = f" {signal.width}" if signal.width else " scalar"
                facts.append((f"{signal.kind.title()} signal: {word}", f"Declared in {owner.name};{width}, line {signal.line}."))
                break
        if any(token in word.lower() for token in ("button", "btn", "uart", "rx", "async")):
            facts.append(("Clock-domain reminder", "External or asynchronous inputs should pass through an appropriate synchronizer before synchronous logic uses them."))
        if not facts:
            facts.append(("Project-aware explanation", "No known construct is selected. Select an HDL statement, declaration, module, or signal and run Explain again."))

        window = tk.Toplevel(self.root)
        window.title("Explain HDL")
        self._center_toplevel(window, 700, 480)
        shell = ttk.Frame(window, padding=16)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, image=self.icons["bulb"], text="  Contextual HDL explanation", compound="left",
                  font=("Segoe UI Semibold", 16)).pack(anchor="w")
        ttk.Label(shell, text=f"{self.current_file.name}  •  {word or 'current selection'}",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        output = tk.Text(shell, wrap="word", state="normal", background=COLORS["panel_alt"],
                         foreground=COLORS["text"], relief="flat", padx=14, pady=14, font=("Segoe UI", 10))
        output.pack(fill="both", expand=True)
        output.tag_configure("heading", foreground=COLORS["cyan"], font=("Segoe UI Semibold", 11))
        output.tag_configure("source", foreground=COLORS["muted"], font=("Cascadia Code", 9))
        output.insert("end", "SELECTED CODE\n", "heading")
        output.insert("end", (selection[:900] or "(empty line)") + "\n\n", "source")
        for title, explanation in facts:
            output.insert("end", title + "\n", "heading")
            output.insert("end", explanation + "\n\n")
        output.insert("end", "Authoritative checks\n", "heading")
        output.insert("end", "Use Smart Check for structure, Verilator Lint for language/design rules, and Simulation for behavior.")
        output.configure(state="disabled")
        window.bind("<Escape>", lambda _event: window.destroy())

    def show_netlist_viewer(self) -> None:
        artifact = self.current_project / "build" / "top.json"
        if not artifact.is_file():
            if messagebox.askyesno(
                "Build required",
                "The netlist viewer uses the synthesized Yosys artifact build/top.json.\n\n"
                "Run Build now? Open the viewer again after the build completes.",
                parent=self.root,
            ):
                self.run_fpga("build")
            return
        try:
            graph = load_yosys_netlist(
                artifact, self.current_project, self.current_index.top_name,
            )
        except NetlistError as error:
            messagebox.showerror("Netlist viewer", str(error), parent=self.root)
            return
        open_netlist_viewer(
            self.root, graph, COLORS, self.icons,
            lambda path, line: self.open_file(path, line),
        )
        self.status_text.set(
            f"Netlist: {len(graph.cells):,} cells and {len(graph.connections):,} connections"
        )

    def show_pin_inspector(self) -> None:
        config = self.current_project / "fpga.config.psd1"
        config_text = config.read_text(encoding="utf-8", errors="replace") if config.exists() else ""
        constraint_match = re.search(r"(?m)^\s*Constraint\s*=\s*['\"]([^'\"]+)", config_text)
        relative = constraint_match.group(1) if constraint_match else "constraints/primer20k_dock.cst"
        constraint = self.current_project / relative.replace("/", os.sep)
        if not constraint.exists():
            messagebox.showerror("Pin inspector", f"Constraint file not found: {relative}")
            return
        text = constraint.read_text(encoding="utf-8", errors="replace")
        electrical: dict[str, str] = {}
        for match in re.finditer(r'(?m)^\s*IO_PORT\s+"([^"]+)"\s+(.+)$', text):
            electrical[match.group(1)] = match.group(2).strip()
        assignments: list[tuple[str, str, str, int]] = []
        for match in re.finditer(r'(?m)^\s*IO_LOC\s+"([^"]+)"\s+([A-Za-z0-9_]+)', text):
            signal, pin = match.group(1), match.group(2)
            base = re.sub(r"\[.*$", "", signal)
            standard = electrical.get(signal, electrical.get(base, "Not specified"))
            assignments.append((signal, pin, standard, text.count("\n", 0, match.start()) + 1))

        window = tk.Toplevel(self.root)
        window.title("Pin Assignment Inspector")
        self._center_toplevel(window, 930, 570)
        shell = ttk.Frame(window, padding=14)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, image=self.icons["target"], text="  Pin Assignment Inspector", compound="left",
                  font=("Segoe UI Semibold", 16)).pack(anchor="w")
        ttk.Label(shell, text=f"{relative}  •  {len(assignments)} physical assignments",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        tree = ttk.Treeview(shell, columns=("signal", "pin", "electrical", "line"), show="headings")
        for column, label in (("signal", "Top-level signal"), ("pin", "Package pin"),
                              ("electrical", "Electrical properties"), ("line", "Line")):
            tree.heading(column, text=label)
        tree.column("signal", width=220, stretch=False)
        tree.column("pin", width=100, stretch=False, anchor="center")
        tree.column("electrical", width=480, stretch=True)
        tree.column("line", width=65, stretch=False, anchor="center")
        locations: dict[str, int] = {}
        for signal, pin, standard, line in assignments:
            item = tree.insert("", "end", values=(signal, pin, standard, line),
                               tags=("warning",) if standard == "Not specified" else ())
            locations[item] = line
        tree.tag_configure("warning", foreground=COLORS["yellow"])
        tree.pack(fill="both", expand=True)
        missing = sum(standard == "Not specified" for _signal, _pin, standard, _line in assignments)
        summary = (
            f"{len(assignments)} pins mapped  •  {missing} without electrical properties  •  "
            "Double-click a row to open its constraint"
        )
        ttk.Label(shell, text=summary, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

        def open_assignment(_event=None) -> None:
            selected = tree.selection()
            if selected and selected[0] in locations:
                self.open_file(constraint, locations[selected[0]])
                window.destroy()

        tree.bind("<Double-1>", open_assignment)
        tree.bind("<Return>", open_assignment)
        window.bind("<Escape>", lambda _event: window.destroy())

    def apply_quick_fix(self) -> None:
        selected = self.problems_tree.selection()
        diagnostic = self.problem_items.get(selected[0]) if selected else None
        if diagnostic is None or diagnostic.code not in {"STYLE001", "SIM001"}:
            diagnostic = next(
                (item for item in self.current_index.diagnostics if item.code in {"STYLE001", "SIM001"}), None,
            )
        if diagnostic is None:
            messagebox.showinfo(
                "No safe quick fix",
                "This issue needs a design decision. The Coach explains what to inspect without guessing hardware behavior.",
            )
            return
        if diagnostic.code == "STYLE001" and diagnostic.path:
            path = diagnostic.path
            if self.current_file == path and self.dirty and not self.save_file():
                return
            text = path.read_text(encoding="utf-8", errors="replace")
            updated = "`default_nettype none\n\n" + text.rstrip() + "\n\n`default_nettype wire\n"
            path.write_text(updated, encoding="utf-8", newline="\n")
            self._append_console(f"Quick fix: added strict net declarations to {path.name}.\n", "success")
            self.open_file(path)
            self.analyze_project(False)
            return
        if diagnostic.code == "SIM001":
            self._create_testbench_skeleton()

    def _create_testbench_skeleton(self) -> None:
        top = self.current_index.modules.get(self.current_index.top_name)
        if top is None:
            messagebox.showerror("Cannot create testbench", "The configured top module must exist first.")
            return
        target = self.current_project / "sim" / "tb_top.sv"
        if target.exists():
            messagebox.showinfo("Testbench exists", "sim/tb_top.sv already exists.")
            return
        if not messagebox.askyesno(
            "Create testbench",
            "Generate a compilable smoke-test skeleton from the recognized top-level ports?\n\n"
            "You will still need to add project-specific expected behavior.",
        ):
            return
        inputs = [port for port in top.ports if port.direction in {"input", "inout"}]
        outputs = [port for port in top.ports if port.direction == "output"]
        clock = next((port for port in inputs if "clk" in port.name.lower() or "clock" in port.name.lower()), None)
        declarations = []
        for port in top.ports:
            width = (port.width + " ") if port.width else ""
            initial = " = '0" if port.direction in {"input", "inout"} else ""
            declarations.append(f"    logic {width}{port.name}{initial};")
        connections = ",\n".join(f"        .{port.name}({port.name})" for port in top.ports)
        clock_process = f"    always #18.5 {clock.name} = ~{clock.name};\n\n" if clock else ""
        wait_statement = f"        repeat (5) @(posedge {clock.name});" if clock else "        #200;"
        output_names = ", ".join(port.name for port in outputs)
        output_check = (
            f"        if ($isunknown({{{output_names}}})) $fatal(1, \"Top-level output contains X/Z\");\n"
            if output_names else ""
        )
        content = f"""`timescale 1ns/1ps
`default_nettype none

module tb_top;
{chr(10).join(declarations)}

    {top.name} dut (
{connections}
    );

{clock_process}    initial begin
        $dumpfile("build/waves.vcd");
        $dumpvars(0, tb_top);
{wait_statement}
{output_check}        // TODO: drive inputs and assert the intended behavior.
        $display("PASS: smoke test completed without unknown outputs");
        $finish;
    end
endmodule

`default_nettype wire
"""
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        self._append_console("Quick fix: generated sim/tb_top.sv from recognized top-level ports.\n", "success")
        self.populate_file_tree()
        self.analyze_project(False)
        self.open_file(target)

    # ------------------------------------------------------------- project help
    def new_project(self) -> None:
        templates = discover_templates(WORKSPACE_ROOT)
        if not templates:
            messagebox.showerror("No project templates", "No complete project template is available in projects/.")
            return
        projects_root = WORKSPACE_ROOT / "projects"
        existing_numbers = [
            int(match.group(1))
            for path in projects_root.iterdir() if path.is_dir()
            if (match := re.match(r"(\d{2})_", path.name))
        ]
        next_number = min(99, max(existing_numbers, default=0) + 1)

        dialog = tk.Toplevel(self.root)
        dialog.title("New FPGA project")
        dialog.geometry("860x620")
        dialog.minsize(720, 520)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)
        dialog.grab_set()
        header = ttk.Frame(dialog, style="Top.TFrame", padding=(22, 18, 22, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Create a project you can verify immediately", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Choose a tested starting point. The wizard creates RTL, constraints, a self-checking testbench, and waves.",
            style="Status.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(dialog, padding=(22, 8, 22, 12))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="1  Choose a starting point", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 7))
        tree = ttk.Treeview(body, columns=("level", "description"), show="tree headings", height=5)
        tree.heading("#0", text="Template")
        tree.heading("level", text="Level")
        tree.heading("description", text="What you get")
        tree.column("#0", width=170, stretch=False)
        tree.column("level", width=95, stretch=False)
        tree.column("description", width=470, stretch=True)
        template_items: dict[str, object] = {}
        for template in templates:
            item = tree.insert("", "end", text=template.title, values=(template.level, template.description))
            template_items[item] = template
        tree.pack(fill="x")
        first = tree.get_children()[0]
        tree.selection_set(first)
        tree.focus(first)

        ttk.Separator(body).pack(fill="x", pady=15)
        ttk.Label(body, text="2  Name the project", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 7))
        form = ttk.Frame(body)
        form.pack(fill="x")
        ttk.Label(form, text="Folder").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        name_var = tk.StringVar(value=f"{next_number:02d}_my_fpga_project")
        name_entry = ttk.Entry(form, textvariable=name_var)
        name_entry.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(form, text="Example: 04_uart_echo", style="Muted.TLabel").grid(
            row=0, column=2, sticky="w", padx=(10, 0), pady=5,
        )
        ttk.Label(form, text="Project title").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        title_var = tk.StringVar(value="My FPGA project")
        ttk.Entry(form, textvariable=title_var).grid(row=1, column=1, sticky="ew", pady=5)
        form.columnconfigure(1, weight=1)
        tutorial_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            body, text="Open the interactive first-project tutorial after creation",
            variable=tutorial_var,
        ).pack(anchor="w", pady=(16, 0))
        ttk.Label(
            body,
            text="Nothing is uploaded automatically. Simulation comes first; hardware actions remain explicit.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        actions = ttk.Frame(dialog, padding=(22, 8, 22, 18))
        actions.pack(fill="x")

        def finish() -> None:
            selected = tree.selection()
            template = template_items.get(selected[0]) if selected else None
            if template is None:
                messagebox.showerror("Choose a template", "Select a project starting point.", parent=dialog)
                return
            try:
                target = create_project(
                    projects_root, name_var.get(), template, display_name=title_var.get(),
                )
            except ProjectCreationError as error:
                messagebox.showerror("Project not created", str(error), parent=dialog)
                name_entry.focus_set()
                return
            relative = target.relative_to(WORKSPACE_ROOT).as_posix()
            dialog.destroy()
            self._refresh_projects(relative)
            self._append_console(f"Created a complete project: {relative}\n", "success")
            self.open_file(target / "rtl" / "top.sv")
            self.status_text.set(f"Project ready — {target.name}")
            if tutorial_var.get():
                self.root.after(120, self.show_first_project_tutorial)

        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")
        self._action_button(actions, "Create project", "plus", finish, "Accent.TButton").pack(side="right", padx=8)
        name_entry.selection_range(3, "end")
        name_entry.focus_set()

    def new_module(self) -> None:
        name = simpledialog.askstring("New HDL module", "SystemVerilog module name:", parent=self.root)
        if not name:
            return
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            messagebox.showerror("Invalid module", "Use a valid HDL identifier such as uart_rx.")
            return
        target = self.current_project / "rtl" / f"{name}.sv"
        if target.exists():
            messagebox.showerror("Already exists", f"{target.name} already exists.")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        content = f"""`timescale 1ns/1ps
`default_nettype none

module {name} (
    input logic clk
);
    // TODO: define ports and behavior.
endmodule

`default_nettype wire
"""
        target.write_text(content, encoding="utf-8", newline="\n")
        file_list = self.current_project / "rtl" / "files.f"
        existing = file_list.read_text(encoding="utf-8", errors="replace") if file_list.exists() else ""
        entry = f"rtl/{name}.sv"
        if entry not in existing.splitlines():
            with file_list.open("a", encoding="utf-8", newline="\n") as stream:
                if existing and not existing.endswith("\n"):
                    stream.write("\n")
                stream.write(entry + "\n")
        self.populate_file_tree()
        self.analyze_project(False)
        self.open_file(target)

    def open_project_folder(self) -> None:
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", str(self.current_project)])
        else:
            messagebox.showinfo("Project folder", str(self.current_project))

    def show_beginner_guide(self) -> None:
        readme = self.current_project / "README.md"
        if readme.exists():
            self.open_file(readme)
        self.intelligence_notebook.select(2)
        self._refresh_coach()

    def show_release_notes_if_needed(self) -> None:
        """Present this version's notes once, without interrupting later launches."""
        if release_notes_pending(self.settings, APP_VERSION):
            self.show_release_notes()

    def show_release_notes(self, *, mark_seen: bool = True) -> None:
        """Show the current version's highlights in a persistent, themed window."""
        if self.release_notes_window is not None:
            try:
                if self.release_notes_window.winfo_exists():
                    self.release_notes_window.deiconify()
                    self.release_notes_window.lift()
                    self.release_notes_window.focus_force()
                    return
            except tk.TclError:
                pass
            self.release_notes_window = None

        notes = notes_for_version(APP_VERSION)
        dialog = tk.Toplevel(self.root)
        self.release_notes_window = dialog
        dialog.title(f"What's new in {APP_VERSION}")
        dialog.geometry("980x700")
        dialog.minsize(780, 620)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)

        def close() -> None:
            self.release_notes_window = None
            try:
                dialog.destroy()
            except tk.TclError:
                pass

        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _event: close())

        header = ttk.Frame(dialog, style="Top.TFrame", padding=(26, 20, 26, 18))
        header.pack(fill="x")
        heading_row = ttk.Frame(header, style="Top.TFrame")
        heading_row.pack(fill="x")
        ttk.Label(heading_row, image=self.icons["sparkle"], style="Title.TLabel").pack(
            side="left", padx=(0, 10), anchor="n",
        )
        heading_copy = ttk.Frame(heading_row, style="Top.TFrame")
        heading_copy.pack(side="left", fill="x", expand=True)
        ttk.Label(heading_copy, text=notes.eyebrow, style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(
            heading_copy, text=notes.title, style="Title.TLabel", wraplength=790, justify="left",
        ).pack(anchor="w", pady=(5, 0))

        body = ttk.Frame(dialog, padding=(26, 18, 26, 12))
        body.pack(fill="both", expand=True)
        intro = ttk.Frame(body, style="Card.TFrame", padding=(18, 14))
        intro.pack(fill="x", pady=(0, 14))
        ttk.Label(
            intro, text=notes.summary, style="Muted.TLabel", wraplength=850, justify="left",
        ).pack(anchor="w")

        cards = ttk.Frame(body)
        cards.pack(fill="both", expand=True)
        cards.columnconfigure(0, weight=1, uniform="release-card")
        cards.columnconfigure(1, weight=1, uniform="release-card")
        for row in range(3):
            cards.rowconfigure(row, weight=1, uniform="release-row")
        for index, highlight in enumerate(notes.highlights):
            row, column = divmod(index, 2)
            card = ttk.Frame(cards, style="Card.TFrame", padding=(16, 13))
            card.grid(
                row=row, column=column, sticky="nsew",
                padx=(0, 7) if column == 0 else (7, 0), pady=6,
            )
            title_row = ttk.Frame(card, style="Card.TFrame")
            title_row.pack(fill="x")
            ttk.Label(title_row, image=self.icons[highlight.icon], style="Card.TLabel").pack(
                side="left", padx=(0, 9),
            )
            ttk.Label(
                title_row, text=highlight.title, style="CardTitle.TLabel", wraplength=330,
            ).pack(side="left", anchor="w")
            ttk.Label(
                card, text=highlight.description, style="Muted.TLabel",
                wraplength=390, justify="left",
            ).pack(anchor="w", pady=(8, 0))

        footer = ttk.Frame(dialog, padding=(26, 8, 26, 20))
        footer.pack(fill="x")

        def open_changelog() -> None:
            close()
            self.open_file(WORKSPACE_ROOT / "CHANGELOG.md")

        def start_tutorial() -> None:
            close()
            self.root.after_idle(self.show_first_project_tutorial)

        self._action_button(
            footer, "Start exploring", "play", close, "Accent.TButton",
        ).pack(side="right")
        ttk.Button(footer, text="First-project tutorial", command=start_tutorial).pack(side="right", padx=8)
        ttk.Button(footer, text="Full changelog", command=open_changelog).pack(side="right")
        ttk.Label(
            footer, text="Reopen later from Help → What's new",
            style="Muted.TLabel",
        ).pack(side="left")

        # Reserve the action row before allowing the highlight grid to expand.
        # Tk's packer otherwise lets large fonts squeeze footer buttons on
        # high-DPI laptop displays.
        body.pack_forget()
        footer.pack_forget()
        footer.pack(side="bottom", fill="x")
        body.pack(fill="both", expand=True)

        if mark_seen:
            mark_release_notes_seen(self.settings, APP_VERSION)
            save_user_settings(self.settings)
        dialog.lift()
        dialog.focus_force()

    def show_first_project_tutorial(self) -> None:
        project_key = self._project_relative()
        stored = self.settings.get("tutorial_progress")
        progress_map = dict(stored) if isinstance(stored, dict) else {}
        try:
            current_step = max(0, min(6, int(progress_map.get(project_key, 0))))
        except (TypeError, ValueError):
            current_step = 0

        steps = [
            ("Read the top-level RTL", "See how board pins enter the design and where child modules connect.",
             lambda: self.open_file(self.current_project / "rtl" / "top.sv")),
            ("Run the project check", "Catch hierarchy, pin, testbench, and beginner RTL issues before tools run.",
             lambda: self.analyze_project(True)),
            ("Simulate the design", "Run the self-checking testbench. A PASS line is your first proof.",
             lambda: self.run_fpga("sim")),
            ("Inspect the waveform", "Open the prepared GTKWave layout and connect behavior to clock cycles.",
             lambda: self.run_fpga("wave")),
            ("Build the bitstream", "Synthesize, place, route, and check the 27 MHz timing target.",
             lambda: self.run_fpga("build")),
            ("Try SRAM safely", "Use volatile SRAM first. Flash is deliberately left outside this first lesson.",
             lambda: self.run_fpga("upload")),
        ]

        dialog = tk.Toplevel(self.root)
        dialog.title("First-project tutorial")
        dialog.geometry("900x600")
        dialog.minsize(740, 500)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)
        header = ttk.Frame(dialog, style="Top.TFrame", padding=(22, 18, 22, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Your first FPGA workflow", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header, text="One small, repeatable loop: understand → check → simulate → inspect → build → test SRAM.",
            style="Status.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(dialog, padding=(22, 8, 22, 18))
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 20))
        right = ttk.Frame(body, style="Card.TFrame", padding=20)
        right.pack(side="left", fill="both", expand=True)
        step_labels: list[ttk.Label] = []
        for position, (title, _description, _action) in enumerate(steps):
            label = ttk.Label(left, text="", width=27, padding=(8, 9), anchor="w")
            label.pack(fill="x", pady=2)
            step_labels.append(label)

        progress_text = tk.StringVar()
        title_text = tk.StringVar()
        detail_text = tk.StringVar()
        ttk.Label(right, textvariable=progress_text, style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(right, textvariable=title_text, font=("Segoe UI Semibold", 18), wraplength=500).pack(
            anchor="w", pady=(8, 8),
        )
        ttk.Label(right, textvariable=detail_text, style="Muted.TLabel", wraplength=500, justify="left").pack(
            anchor="w", pady=(0, 18),
        )
        explanation = tk.Text(
            right, height=10, wrap="word", state="disabled", bg=COLORS["panel_alt"], fg=COLORS["text"],
            relief="flat", padx=14, pady=12, font=("Segoe UI", 10),
        )
        explanation.pack(fill="both", expand=True)
        controls = ttk.Frame(right, padding=(0, 14, 0, 0))
        controls.pack(fill="x")

        def save_progress(value: int) -> None:
            progress_map[project_key] = value
            self.settings["tutorial_progress"] = progress_map
            save_user_settings(self.settings)

        selected_step = tk.IntVar(value=current_step)

        def select_step(position: int) -> None:
            selected_step.set(position)
            title, description, _action = steps[position]
            progress_text.set(f"STEP {position + 1} OF {len(steps)}")
            title_text.set(title)
            detail_text.set(description)
            notes = (
                "Run the action, read the console, and inspect the relevant file. "
                "Do not chase every warning blindly: the Problems panel explains the project-level checks.\n\n"
                "Hardware safety: simulation and build do not program the board. SRAM is volatile. "
                "Persistent Flash remains a separate, confirmed action."
            )
            explanation.configure(state="normal")
            explanation.delete("1.0", "end")
            explanation.insert("1.0", notes)
            explanation.configure(state="disabled")
            for index, label in enumerate(step_labels):
                marker = "✓" if index < current_step else "→" if index == position else "○"
                label.configure(
                    text=f"{marker}  {index + 1}. {steps[index][0]}",
                    style="Accent.TLabel" if index == position else "TLabel",
                )

        for position, label in enumerate(step_labels):
            label.bind("<Button-1>", lambda _event, value=position: select_step(value))

        def run_action() -> None:
            steps[selected_step.get()][2]()

        def complete_step() -> None:
            nonlocal current_step
            position = selected_step.get()
            current_step = max(current_step, min(len(steps), position + 1))
            save_progress(current_step)
            if position < len(steps) - 1:
                select_step(position + 1)
            else:
                select_step(position)
                messagebox.showinfo(
                    "Workflow complete",
                    "You completed the guided loop. Repeat it whenever you add a module or change behavior.",
                    parent=dialog,
                )

        self._action_button(controls, "Run this step", "play", run_action, "Accent.TButton").pack(side="left")
        ttk.Button(controls, text="Mark done and continue", command=complete_step).pack(side="left", padx=8)
        ttk.Button(controls, text="Close", command=dialog.destroy).pack(side="right")
        # Reserve the action row before giving the explanation the remaining
        # height; this keeps controls visible on small/laptop displays.
        explanation.pack_forget()
        controls.pack_forget()
        controls.pack(side="bottom", fill="x")
        explanation.pack(fill="both", expand=True)
        select_step(current_step if current_step < len(steps) else len(steps) - 1)

    def show_verification_center(self) -> None:
        benches, layouts = discover_verification_assets(self.current_project)
        dialog = tk.Toplevel(self.root)
        dialog.title("Verification center")
        dialog.geometry("820x560")
        dialog.minsize(690, 470)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)
        header = ttk.Frame(dialog, style="Top.TFrame", padding=(22, 18, 22, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Verification center", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header, text="Choose exactly what to test, inspect assertion results, and open a repeatable waveform layout.",
            style="Status.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        body = ttk.Frame(dialog, padding=(22, 12, 22, 18))
        body.pack(fill="both", expand=True)

        bench_values = [item.path.relative_to(self.current_project).as_posix() for item in benches]
        layout_values = [item.path.relative_to(self.current_project).as_posix() for item in layouts]
        bench_var = tk.StringVar(value=bench_values[0] if bench_values else "")
        layout_var = tk.StringVar(value=layout_values[0] if layout_values else "")
        ttk.Label(body, text="Testbench").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Combobox(body, textvariable=bench_var, values=bench_values, state="readonly", width=48).grid(
            row=0, column=1, sticky="ew", pady=6,
        )
        ttk.Label(body, text="GTKWave layout").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Combobox(body, textvariable=layout_var, values=layout_values, state="readonly", width=48).grid(
            row=1, column=1, sticky="ew", pady=6,
        )
        body.columnconfigure(1, weight=1)

        result_card = ttk.Frame(body, style="Card.TFrame", padding=16)
        result_card.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(16, 12))
        ttk.Label(result_card, text="Session result", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(result_card, textvariable=self.verification_summary, font=("Segoe UI Semibold", 13),
                  wraplength=680).pack(anchor="w", pady=(7, 4))
        ttk.Label(
            result_card,
            text="PASS/FAIL lines are counted from the simulator output. Tool errors in the console are clickable.",
            style="Muted.TLabel", wraplength=680,
        ).pack(anchor="w")
        body.rowconfigure(2, weight=1)

        actions = ttk.Frame(body)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew")

        def arguments(include_layout: bool = False) -> list[str]:
            selected = next((item for item in benches if item.path.relative_to(self.current_project).as_posix() == bench_var.get()), None)
            if selected is None:
                return []
            result = ["-Testbench", bench_var.get(), "-TestbenchTop", selected.top_module]
            if include_layout and layout_var.get():
                result.extend(["-WaveLayout", layout_var.get()])
            return result

        def run(command: str) -> None:
            if not benches:
                messagebox.showerror("No testbench", "Add a .v or .sv testbench under sim/ first.", parent=dialog)
                return
            self.run_fpga(command, arguments(command in {"wave", "debug"}))

        self._action_button(actions, "Run selected", "play", lambda: run("sim"), "Accent.TButton").pack(side="left")
        self._action_button(actions, "Debug with waves", "bug", lambda: run("debug")).pack(side="left", padx=6)
        if benches:
            ttk.Button(
                actions, text="Open testbench",
                command=lambda: self.open_file(self.current_project / bench_var.get()),
            ).pack(side="left", padx=6)
        ttk.Button(actions, text="Close", command=dialog.destroy).pack(side="right")

    def show_hardware_setup(self) -> None:
        ports = list_serial_ports()
        port_text = ", ".join(item.port for item in ports) if ports else "No COM ports detected"
        likely_uart = preferred_serial_port(ports)
        dialog = tk.Toplevel(self.root)
        dialog.title("Tang Primer 20K hardware setup")
        dialog.geometry("860x640")
        dialog.minsize(720, 520)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)
        header = ttk.Frame(dialog, style="Top.TFrame", padding=(22, 18, 22, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Connect the board without guesswork", style="Title.TLabel").pack(anchor="w")
        uart_summary = f"Likely Dock UART: {likely_uart.port}" if likely_uart else "Dock UART not identified"
        ttk.Label(header, text=f"{uart_summary}  •  Detected: {port_text}", style="Status.TLabel").pack(
            anchor="w", pady=(4, 0),
        )
        body_shell = ttk.Frame(dialog)
        body_shell.pack(fill="both", expand=True, padx=16, pady=(4, 10))
        body = tk.Text(
            body_shell, wrap="word", state="normal", bg=COLORS["panel"], fg=COLORS["text"], relief="flat",
            padx=22, pady=16, font=("Segoe UI", 10), spacing1=2, spacing3=5,
        )
        body_scroll = ttk.Scrollbar(body_shell, orient="vertical", command=body.yview)
        body.configure(yscrollcommand=body_scroll.set)
        body.pack(side="left", fill="both", expand=True)
        body_scroll.pack(side="right", fill="y")
        body.tag_configure("heading", foreground=COLORS["cyan"], font=("Segoe UI Semibold", 12))
        body.tag_configure("good", foreground=COLORS["green"])
        body.tag_configure("warning", foreground=COLORS["yellow"])
        sections = [
            ("1. USB connection\n", "heading"),
            ("Connect the Tang Primer 20K Dock directly to a reliable USB data port. Avoid charge-only cables.\n\n", ""),
            ("2. Choose the correct USB interfaces\n", "heading"),
            ("JTAG Debugger (Interface 0) is JTAG. Install WinUSB on Interface 0 only.\n", "good"),
            ("JTAG Debugger (Interface 1) is the UART bridge. Keep its normal serial driver. Do not replace it with WinUSB.\n\n", "warning"),
            ("3. Confirm the boot/DIP switches\n", "heading"),
            ("Use the board's normal JTAG programming position. If detection fails, power-cycle after checking the cable and switches.\n\n", ""),
            ("4. Verify in order\n", "heading"),
            ("Run Doctor, then Detect. Build and SRAM upload only after project diagnostics are clear. Test SRAM before persistent Flash.\n\n", ""),
            ("5. UART\n", "heading"),
            ("Open UART terminal, choose the COM port for Interface 1, and use the baud rate defined by your RTL (the UART lesson uses 115200, 8-N-1).", ""),
        ]
        for value, tag in sections:
            body.insert("end", value, tag or None)
        body.configure(state="disabled")
        actions = ttk.Frame(dialog, padding=(18, 0, 18, 16))
        actions.pack(fill="x")
        self._action_button(actions, "Run Doctor", "doctor", lambda: self.run_fpga("doctor"), "Accent.TButton").pack(side="left")
        self._action_button(actions, "Detect JTAG", "target", lambda: self.run_fpga("detect")).pack(side="left", padx=6)
        self._action_button(actions, "Configure Interface 0", "flash", lambda: self.run_fpga("driver")).pack(side="left", padx=6)
        self._action_button(actions, "Open UART", "terminal", self.open_serial_monitor).pack(side="left", padx=6)
        ttk.Button(actions, text="Close", command=dialog.destroy).pack(side="right")
        body_shell.pack_forget()
        actions.pack_forget()
        actions.pack(side="bottom", fill="x")
        body_shell.pack(fill="both", expand=True, padx=16, pady=(4, 10))

    def show_about(self) -> None:
        messagebox.showinfo(
            "About Tang Primer FPGA Studio",
            f"{APP_NAME} {APP_VERSION}\n\nOffline beginner UI for the Tang Primer 20K open-source toolchain.\n"
            "Guided project creation, project-aware HDL navigation, integrated UART, verification selection, "
            "clickable tool diagnostics, pin inspection, workflow coaching, and verified hardware commands.\n\n"
            "HDL intelligence is lightweight assistance, not a full standards-complete language server. "
            "Verilator lint and simulation remain authoritative.",
        )

    # --------------------------------------------------------------- execution
    def run_fpga(self, command: str, extra_args: list[str] | None = None) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showwarning("Command running", "Stop the current command before starting another one.")
            return
        if self.dirty and not self.save_file():
            return
        if command in {"upload", "flash"}:
            self.analyze_project(False)
            blocking = [item for item in self.current_index.diagnostics if item.severity == "error"]
            if blocking:
                self.intelligence_notebook.select(1)
                messagebox.showerror(
                    "Hardware action blocked",
                    f"Resolve {len(blocking)} red project problem(s) before programming hardware. "
                    "This prevents an incomplete pin map or invalid hierarchy from reaching the board.",
                )
                return
        if command == "flash" and not messagebox.askyesno(
            "Persistent flash",
            "This writes persistent FPGA configuration. Have simulation, build, and SRAM testing passed?\n\n"
            + ("SRAM upload passed in this IDE session." if "upload" in self.session_passes else
               "No successful SRAM upload is recorded in this IDE session."),
            icon="warning",
        ):
            return
        command_script = WORKSPACE_ROOT / "fpga.ps1"
        powershell = shutil.which("powershell") or "powershell"
        arguments = [
            powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(command_script),
            command, "-Project", str(self.current_project),
        ]
        if extra_args:
            arguments.extend(extra_args)
        self.active_command = command
        self.active_output = []
        self.command_started = datetime.now()
        self._append_console(
            f"\n[{self.command_started:%H:%M:%S}]  › {command.upper()}  •  {self._project_relative()}\n", "command",
        )
        self.console_meta.set(f"{command.upper()} running  •  live output")
        LOGGER.info("Command started: %s project=%s args=%s", command, self._project_relative(), extra_args or [])
        self.run_state.configure(text=f"● Running {command}", foreground=COLORS["yellow"])
        self.status_text.set(f"Running {command}…")
        self._set_runner_state(False)
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                arguments, cwd=WORKSPACE_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=flags,
            )
        except OSError as error:
            LOGGER.exception("Unable to start command %s", command)
            self._append_console(f"Failed to start command: {error}\n", "error")
            self.run_state.configure(text="● Failed", foreground=COLORS["red"])
            self.status_text.set("Unable to start command")
            self.console_meta.set("Command could not be started")
            self.active_command = ""
            self.process = None
            self._set_runner_state(True)
            return

        process = self.process

        def reader() -> None:
            assert process.stdout is not None
            for line in iter(process.stdout.readline, ""):
                self.process_queue.put(("line", line))
            process.stdout.close()
            self.process_queue.put(("done", process.wait()))

        threading.Thread(target=reader, daemon=True).start()

    def _poll_process_queue(self) -> None:
        try:
            while True:
                kind, payload = self.process_queue.get_nowait()
                if kind == "line":
                    line = str(payload)
                    self.active_output.append(line)
                    lowered = line.lower()
                    tag = "error" if any(word in lowered for word in ("error", "fatal", "failed")) else \
                          "warning" if "warning" in lowered else \
                          "success" if any(word in lowered for word in ("pass:", "complete:", "complete", "done")) else ""
                    tool_diagnostic = parse_tool_diagnostic(line, self.current_project)
                    self._append_console(line, tag, tool_diagnostic)
                elif kind == "done":
                    return_code = int(payload)
                    finished = datetime.now()
                    duration = (finished - self.command_started).total_seconds() if hasattr(self, "command_started") else 0
                    completed_command = self.active_command
                    self.command_history.append((completed_command, return_code, finished))
                    LOGGER.info(
                        "Command finished: %s exit=%s duration=%.1fs",
                        completed_command, return_code, duration,
                    )
                    if return_code == 0:
                        self._append_console(f"Completed successfully in {duration:.1f}s.\n", "success")
                        if completed_command:
                            self.session_passes.add(completed_command)
                        self.run_state.configure(text="● Ready", foreground=COLORS["green"])
                        self.status_text.set("Command completed successfully")
                        self.console_meta.set(f"Last: {completed_command.upper()} passed  •  {duration:.1f}s")
                    else:
                        self._append_console(f"Command exited with code {return_code}.\n", "error")
                        self.run_state.configure(text="● Failed", foreground=COLORS["red"])
                        self.status_text.set(f"Command failed with exit code {return_code}")
                        self.console_meta.set(f"Last: {completed_command.upper()} failed  •  exit {return_code}")
                    if completed_command in {"sim", "wave", "debug"}:
                        state, passed, failed = summarize_verification_output("".join(self.active_output), return_code)
                        detail = f"{state} • {passed} PASS assertion line{'s' if passed != 1 else ''}"
                        if failed:
                            detail += f" • {failed} failure line{'s' if failed != 1 else ''}"
                        detail += f" • {duration:.1f}s"
                        self.verification_summary.set(detail)
                    self.active_command = ""
                    self.process = None
                    self._set_runner_state(True)
                    self.populate_file_tree()
                    self.analyze_project(False)
        except queue.Empty:
            pass
        self.root.after(60, self._poll_process_queue)

    def _set_runner_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.runner_buttons:
            button.configure(state=state)
        self.stop_button.configure(state="disabled" if enabled else "normal")

    def stop_process(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        if self.active_command in {"upload", "flash"} and not messagebox.askyesno(
            "Interrupt hardware programming?",
            "Stopping during programming can leave the FPGA configuration incomplete. "
            "Stop only if the command is genuinely stuck.",
            icon="warning",
        ):
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                    capture_output=True, text=True, check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                self.process.terminate()
            self._append_console("Stop requested by user.\n", "warning")
            LOGGER.warning("Stop requested for command: %s", self.active_command)
        except OSError as error:
            self._append_console(f"Unable to stop process: {error}\n", "error")

    def open_serial_monitor(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("UART terminal")
        dialog.geometry("980x650")
        dialog.minsize(760, 500)
        dialog.configure(bg=COLORS["bg"])
        dialog.transient(self.root)
        self.serial_windows.append(dialog)
        incoming: queue.Queue[bytes] = queue.Queue()
        connection: SerialConnection | None = None
        history_position = len(self.uart_history)

        header = ttk.Frame(dialog, style="Top.TFrame", padding=(16, 13, 16, 9))
        header.pack(fill="x")
        title = ttk.Frame(header, style="Top.TFrame")
        title.pack(side="left")
        ttk.Label(title, text="UART terminal", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="Send and inspect serial data without leaving the FPGA workflow",
                  style="Status.TLabel").pack(anchor="w")
        connection_state = tk.StringVar(value="Disconnected")
        ttk.Label(header, textvariable=connection_state, style="Status.TLabel").pack(side="right")

        controls = ttk.Frame(dialog, padding=(16, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="Port").pack(side="left")
        port_var = tk.StringVar()
        port_combo = ttk.Combobox(controls, textvariable=port_var, state="readonly", width=23)
        port_combo.pack(side="left", padx=(6, 12))
        ttk.Label(controls, text="Baud").pack(side="left")
        baud_var = tk.StringVar(value="115200")
        ttk.Combobox(
            controls, textvariable=baud_var,
            values=("9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"),
            width=10,
        ).pack(side="left", padx=(6, 12))
        ttk.Label(controls, text="View").pack(side="left")
        mode_var = tk.StringVar(value="ascii")
        ttk.Combobox(controls, textvariable=mode_var, values=("ascii", "hex"), state="readonly", width=7).pack(
            side="left", padx=(6, 12),
        )
        timestamp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Timestamps", variable=timestamp_var).pack(side="left")

        terminal_frame = tk.Frame(dialog, bg=COLORS["console"], highlightthickness=1,
                                  highlightbackground=COLORS["border_soft"])
        terminal_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))
        terminal = tk.Text(
            terminal_frame, wrap="word", state="disabled", bg=COLORS["console"], fg=COLORS["text"],
            insertbackground=COLORS["cursor"], selectbackground=COLORS["selection"], relief="flat",
            padx=12, pady=10, font=("Cascadia Mono", 10),
        )
        terminal.tag_configure("rx", foreground=COLORS["text"])
        terminal.tag_configure("tx", foreground=COLORS["cyan"])
        terminal.tag_configure("status", foreground=COLORS["muted"])
        terminal.tag_configure("error", foreground=COLORS["red"])
        terminal_scroll = ttk.Scrollbar(terminal_frame, orient="vertical", command=terminal.yview)
        terminal.configure(yscrollcommand=terminal_scroll.set)
        terminal.pack(side="left", fill="both", expand=True)
        terminal_scroll.pack(side="right", fill="y")

        send_row = ttk.Frame(dialog, padding=(16, 4, 16, 8))
        send_row.pack(fill="x")
        send_var = tk.StringVar()
        send_entry = ttk.Entry(send_row, textvariable=send_var)
        send_entry.pack(side="left", fill="x", expand=True)
        ending_var = tk.StringVar(value="CRLF")
        ttk.Combobox(send_row, textvariable=ending_var, values=("None", "CR", "LF", "CRLF"),
                     state="readonly", width=7).pack(side="left", padx=7)

        def append_terminal(value: str, tag: str = "status") -> None:
            terminal.configure(state="normal")
            terminal.insert("end", value, tag)
            terminal.see("end")
            terminal.configure(state="disabled")

        def timestamp_prefix() -> str:
            if not timestamp_var.get():
                return ""
            now = datetime.now()
            return f"[{now:%H:%M:%S}.{now.microsecond // 1000:03d}] "

        port_map: dict[str, str] = {}

        def refresh_ports() -> None:
            nonlocal port_map
            ports = list_serial_ports()
            port_map = {
                f"{item.port} — {item.description}" if item.description else item.port: item.port
                for item in ports
            }
            values = list(port_map)
            current_port = port_map.get(port_var.get(), port_var.get().split(" — ", 1)[0])
            port_combo.configure(values=values)
            selected = next((label for label, port in port_map.items() if port == current_port), "")
            preferred = preferred_serial_port(ports)
            if not selected and preferred:
                selected = next((label for label, port in port_map.items() if port == preferred.port), "")
            port_var.set(selected)
            message = f"Detected {len(values)} COM port{'s' if len(values) != 1 else ''}. "
            if preferred:
                message += f"Likely Dock UART: {preferred.port}."
            else:
                message += "No USB UART was auto-selected; Bluetooth modem ports are ignored."
            append_terminal(message + " Interface 1 is UART.\n", "status")

        connect_button: ttk.Button

        def connected_port() -> str:
            return port_map.get(port_var.get(), port_var.get().split(" — ", 1)[0].strip().upper())

        def disconnect(announce: bool = True) -> None:
            nonlocal connection
            if connection:
                connection.close()
            connection = None
            connection_state.set("Disconnected")
            connect_button.configure(text="Connect")
            port_combo.configure(state="readonly")
            if announce:
                append_terminal("Disconnected.\n", "status")

        def toggle_connection() -> None:
            nonlocal connection
            if connection and connection.is_open:
                disconnect()
                return
            port = connected_port()
            if not port:
                messagebox.showerror("No COM port", "Connect the Dock UART interface, then refresh ports.", parent=dialog)
                return
            try:
                baud = int(baud_var.get())
                if not 300 <= baud <= 4_000_000:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid baud rate", "Enter a baud rate from 300 to 4,000,000.", parent=dialog)
                return
            try:
                connection = SerialConnection(port, baud, incoming.put)
                connection.open()
            except (OSError, ValueError) as error:
                connection = None
                append_terminal(f"Could not open {port}: {error}\n", "error")
                messagebox.showerror(
                    "UART connection failed",
                    f"{error}\n\nClose other serial monitors and confirm Interface 1 still uses its serial driver.",
                    parent=dialog,
                )
                return
            connection_state.set(f"Connected • {port} • {baud} baud • 8-N-1")
            connect_button.configure(text="Disconnect")
            port_combo.configure(state="disabled")
            append_terminal(f"Connected to {port} at {baud} baud, 8-N-1.\n", "status")

        def send(_event=None):
            value = send_var.get()
            if not value and ending_var.get() == "None":
                return "break"
            if connection is None or not connection.is_open:
                messagebox.showinfo("UART is disconnected", "Choose a COM port and press Connect first.", parent=dialog)
                return "break"
            try:
                payload = encode_terminal_input(value, mode_var.get())
                ending = {"None": b"", "CR": b"\r", "LF": b"\n", "CRLF": b"\r\n"}[ending_var.get()]
                payload += ending
                connection.write(payload)
            except (OSError, ValueError) as error:
                append_terminal(f"Send failed: {error}\n", "error")
                return "break"
            prefix = timestamp_prefix()
            append_terminal(f"{prefix}TX  {format_terminal_bytes(payload, mode_var.get())}\n", "tx")
            if value:
                self.uart_history.append(value)
                if len(self.uart_history) > 100:
                    del self.uart_history[:-100]
            send_var.set("")
            return "break"

        def history_move(delta: int):
            def move(_event=None):
                nonlocal history_position
                if not self.uart_history:
                    return "break"
                history_position = max(0, min(len(self.uart_history), history_position + delta))
                send_var.set(self.uart_history[history_position] if history_position < len(self.uart_history) else "")
                send_entry.icursor("end")
                return "break"
            return move

        send_entry.bind("<Return>", send)
        send_entry.bind("<Up>", history_move(-1))
        send_entry.bind("<Down>", history_move(1))
        self._action_button(send_row, "Send", "upload", send, "Accent.TButton").pack(side="left")

        footer = ttk.Frame(dialog, padding=(16, 0, 16, 14))
        footer.pack(fill="x")
        connect_button = self._action_button(footer, "Connect", "terminal", toggle_connection, "Accent.TButton")
        connect_button.pack(side="left")
        ttk.Button(footer, text="Refresh ports", command=refresh_ports).pack(side="left", padx=6)

        def clear() -> None:
            terminal.configure(state="normal")
            terminal.delete("1.0", "end")
            terminal.configure(state="disabled")

        def save_log() -> None:
            target = filedialog.asksaveasfilename(
                parent=dialog, title="Save UART log", defaultextension=".log",
                filetypes=(("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")),
                initialfile=f"uart-{datetime.now():%Y%m%d-%H%M%S}.log",
            )
            if not target:
                return
            try:
                Path(target).write_text(terminal.get("1.0", "end-1c"), encoding="utf-8", newline="\n")
                append_terminal(f"Saved log to {target}\n", "status")
            except OSError as error:
                messagebox.showerror("Log not saved", str(error), parent=dialog)

        ttk.Button(footer, text="Clear", command=clear).pack(side="right")
        ttk.Button(footer, text="Save log…", command=save_log).pack(side="right", padx=6)
        terminal_frame.pack_forget()
        send_row.pack_forget()
        footer.pack_forget()
        footer.pack(side="bottom", fill="x")
        send_row.pack(side="bottom", fill="x")
        terminal_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))

        def poll_incoming() -> None:
            if not dialog.winfo_exists():
                return
            try:
                while True:
                    payload = incoming.get_nowait()
                    if not payload:
                        append_terminal("The serial connection stopped unexpectedly.\n", "error")
                        disconnect(False)
                        continue
                    prefix = timestamp_prefix()
                    formatted = format_terminal_bytes(payload, mode_var.get())
                    suffix = "\n" if mode_var.get() == "hex" else ""
                    append_terminal(f"{prefix}RX  {formatted}{suffix}", "rx")
            except queue.Empty:
                pass
            dialog.after(40, poll_incoming)

        def close() -> None:
            disconnect(False)
            if dialog in self.serial_windows:
                self.serial_windows.remove(dialog)
            dialog.destroy()

        dialog._serial_close = close  # type: ignore[attr-defined]
        dialog.protocol("WM_DELETE_WINDOW", close)
        refresh_ports()
        poll_incoming()
        send_entry.focus_set()

    def clean_project(self) -> None:
        if messagebox.askyesno("Clean project", "Remove only generated files under this project's build/ folder?"):
            self.run_fpga("clean")

    def _append_console(
        self, text: str, tag: str = "", diagnostic: ToolDiagnostic | None = None,
    ) -> None:
        self.console.configure(state="normal")
        tags: list[str] = [tag] if tag else []
        if diagnostic and diagnostic.path:
            self.console_diagnostic_sequence += 1
            link_tag = f"tool_location_{self.console_diagnostic_sequence}"
            self.console_diagnostics[link_tag] = diagnostic
            self.console.tag_configure(link_tag, foreground=COLORS["cyan"], underline=True)
            self.console.tag_bind(
                link_tag, "<Button-1>",
                lambda _event, value=diagnostic: self._open_tool_diagnostic(value),
            )
            self.console.tag_bind(link_tag, "<Enter>", lambda _event: self.console.configure(cursor="hand2"))
            self.console.tag_bind(link_tag, "<Leave>", lambda _event: self.console.configure(cursor=""))
            tags.append(link_tag)
        self.console.insert("end", text, tuple(tags) if tags else None)
        self.console.see("end")
        self.console.configure(state="disabled")

    def _open_tool_diagnostic(self, diagnostic: ToolDiagnostic) -> None:
        if diagnostic.path is None:
            return
        self.open_file(diagnostic.path, diagnostic.line)
        target = f"{max(1, diagnostic.line)}.{max(0, diagnostic.column - 1)}"
        self.editor.mark_set("insert", target)
        self.editor.see(target)
        self.editor.focus_set()
        self.status_text.set(f"Opened {diagnostic.path.name}:{diagnostic.line}:{diagnostic.column}")

    def clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        self.console_diagnostics.clear()

    def _on_close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Command running", "Stop the running command and close the IDE?"):
                return
            self.stop_process()
        if not self._confirm_discard_or_save():
            return
        for window in list(self.serial_windows):
            try:
                close_serial = getattr(window, "_serial_close", None)
                if close_serial:
                    close_serial()
            except (OSError, tk.TclError):
                continue
        self.settings["last_project"] = self._project_relative()
        save_user_settings(self.settings)
        LOGGER.info("Studio closed normally")
        self.root.destroy()


def check_project(project: Path) -> int:
    index = scan_project(project)
    payload = {
        "project": str(index.project_root),
        "top": index.top_name,
        "modules": sorted(index.modules),
        "diagnostics": [
            {
                "severity": item.severity,
                "code": item.code,
                "message": item.message,
                "path": str(item.path) if item.path else None,
                "line": item.line,
            }
            for item in index.diagnostics
        ],
    }
    print(json.dumps(payload, indent=2))
    return 1 if any(item.severity == "error" for item in index.diagnostics) else 0


def smoke_test_ui(project_name: str | None, theme_name: str | None = None) -> int:
    """Construct the complete interface without entering the interactive loop."""
    root = tk.Tk()
    root.withdraw()
    studio = FPGAStudio(root, initial_project=project_name, initial_theme=theme_name)
    root.update_idletasks()
    payload = {
        "window": root.title(),
        "theme": studio.theme_name,
        "project": studio._project_relative(),
        "modules": sorted(studio.current_index.modules),
        "diagnostics": len(studio.current_index.diagnostics),
    }
    print(json.dumps(payload, indent=2))
    root.destroy()
    return 0


def stress_test_themes(project_name: str | None) -> int:
    """Exercise live theming, open dialogs, icons, state retention, and rollback."""
    palette_problems = validate_themes()
    if palette_problems:
        print(json.dumps({"passed": False, "palette_errors": palette_problems}, indent=2))
        return 1

    root = tk.Tk()
    root.withdraw()
    studio = FPGAStudio(root, initial_project=project_name, initial_theme="dark")
    try:
        studio.show_snippets()
        studio.show_command_palette()
        studio.show_pin_inspector()
        studio.show_verification_center()
        studio.show_hardware_setup()
        studio.show_first_project_tutorial()
        studio.show_release_notes(mark_seen=False)
        studio.open_serial_monitor()
        netlist_fixture = NetlistGraph(
            WORKSPACE_ROOT / "build" / "theme-test.json", "Yosys theme fixture", "top", {}, {}, [],
        )
        open_netlist_viewer(root, netlist_fixture, COLORS, studio.icons, lambda _path, _line: None)
        root.update_idletasks()
        editor_before = studio.editor.get("1.0", "end-1c")
        open_windows = len([widget for widget in studio._walk_widgets() if isinstance(widget, tk.Toplevel)])

        for cycle in range(30):
            target = "light" if cycle % 2 == 0 else "dark"
            if not studio.set_theme(target, persist=False, announce=False):
                raise RuntimeError(f"Theme switch failed during cycle {cycle}: {target}")
            root.update_idletasks()
            if studio.editor.get("1.0", "end-1c") != editor_before:
                raise RuntimeError("Editor content changed during a theme switch")
            if studio.editor.cget("background").lower() != COLORS["editor"]:
                raise RuntimeError("Editor background did not follow the active theme")
            if studio.editor.cget("foreground").lower() != COLORS["text"]:
                raise RuntimeError("Editor text did not follow the active theme")
            if any(image.width() < 1 or image.height() < 1 for image in studio.icons.values()):
                raise RuntimeError("An icon became invalid during a theme switch")

        if studio.set_theme("not-a-theme", persist=False, announce=False):
            raise RuntimeError("An unknown theme was unexpectedly accepted")
        if studio.theme_name != "dark":
            raise RuntimeError("Rejecting an unknown theme changed the active theme")

        original_configure_styles = studio._configure_styles
        failure_injected = False

        def fail_once() -> None:
            nonlocal failure_injected
            if not failure_injected:
                failure_injected = True
                raise tk.TclError("injected theme failure")
            original_configure_styles()

        studio._configure_styles = fail_once  # type: ignore[method-assign]
        if studio.set_theme("light", persist=False, announce=False):
            raise RuntimeError("Injected theme failure did not trigger recovery")
        studio._configure_styles = original_configure_styles  # type: ignore[method-assign]
        root.update_idletasks()
        if studio.theme_name != "dark" or COLORS != THEMES["dark"]:
            raise RuntimeError("Theme failure did not restore the previous palette")

        current_image_names = {str(image) for image in studio.icons.values()}
        stale_images: list[str] = []
        for widget in studio._walk_widgets():
            try:
                if "image" in widget.configure():
                    reference = studio._image_reference(widget.cget("image"))
                    if reference and reference not in current_image_names:
                        stale_images.append(f"{widget.winfo_class()}:{reference}")
            except (AttributeError, tk.TclError):
                continue
            if isinstance(widget, ttk.Treeview):
                pending = list(widget.get_children(""))
                while pending:
                    item = pending.pop()
                    pending.extend(widget.get_children(item))
                    reference = studio._image_reference(widget.item(item, "image"))
                    if reference and reference not in current_image_names:
                        stale_images.append(f"Treeview item:{reference}")
        for menu in studio.menus:
            end = menu.index("end")
            for index in range((end if end is not None else -1) + 1):
                try:
                    reference = studio._image_reference(menu.entrycget(index, "image"))
                    if reference and reference not in current_image_names:
                        stale_images.append(f"Menu item:{reference}")
                except tk.TclError:
                    continue
        if stale_images:
            raise RuntimeError("Stale icons after theme recovery: " + "; ".join(stale_images[:8]))

        contrast_failures: list[str] = []
        for widget in studio._walk_widgets():
            try:
                configuration = widget.configure()
                if "background" not in configuration or "foreground" not in configuration:
                    continue
                background = str(widget.cget("background"))
                foreground = str(widget.cget("foreground"))
                if HEX_COLOR.fullmatch(background) and HEX_COLOR.fullmatch(foreground):
                    ratio = contrast_ratio(foreground, background)
                    if ratio < 4.5:
                        contrast_failures.append(
                            f"{widget.winfo_class()} {foreground}/{background}={ratio:.2f}:1"
                        )
            except (AttributeError, tk.TclError):
                continue
        if contrast_failures:
            raise RuntimeError("Runtime contrast failures: " + "; ".join(contrast_failures[:8]))

        payload = {
            "passed": True,
            "switches": 30,
            "rollback_verified": True,
            "open_dialogs_rethemed": open_windows,
            "widgets_checked": len(studio._walk_widgets()),
            "icons_checked": len(studio.icons),
            "final_theme": studio.theme_name,
        }
        print(json.dumps(payload, indent=2))
        return 0
    except Exception as error:
        LOGGER.exception("Theme stress test failed")
        print(json.dumps({"passed": False, "error": str(error)}, indent=2))
        return 1
    finally:
        root.destroy()


def enable_windows_dpi_awareness() -> None:
    """Keep Tk crisp and correctly sized on 125–200% Windows displays."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TangPrimer.FPGAStudio")
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except (ImportError, AttributeError, OSError):
        pass


def open_demo_view(studio: FPGAStudio, view: str) -> None:
    """Open a deterministic view used by the documentation screenshot job."""
    if view == "insights":
        studio.show_project_insights()
    elif view == "commands":
        studio.show_command_palette()
    elif view == "snippets":
        studio.show_snippets()
    elif view == "pins":
        studio.show_pin_inspector()
    elif view == "verification":
        studio.show_verification_center()
    elif view == "hardware":
        studio.show_hardware_setup()
    elif view == "uart":
        studio.open_serial_monitor()
    elif view == "tutorial":
        studio.show_first_project_tutorial()
    elif view == "netlist":
        studio.show_netlist_viewer()
    elif view == "release-notes":
        studio.show_release_notes(mark_seen=False)


def main() -> int:
    enable_windows_dpi_awareness()
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--check", metavar="PROJECT", help="run headless HDL intelligence and print JSON")
    parser.add_argument("--project", help="initial project label, for example projects/01_button_led_pwm")
    parser.add_argument("--theme", choices=tuple(THEMES), help="start with an explicit color theme")
    parser.add_argument("--ui-smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--theme-stress-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-startup-release-notes", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--demo-view", choices=(
            "main", "insights", "commands", "snippets", "pins",
            "verification", "hardware", "uart", "tutorial",
            "netlist", "release-notes",
        ),
        default="main", help=argparse.SUPPRESS,
    )
    arguments = parser.parse_args()
    if arguments.check:
        project = Path(arguments.check)
        if not project.is_absolute():
            project = WORKSPACE_ROOT / project
        return check_project(project)
    if arguments.theme_stress_test:
        return stress_test_themes(arguments.project)
    if arguments.ui_smoke_test:
        return smoke_test_ui(arguments.project, arguments.theme)
    root = tk.Tk()
    studio = FPGAStudio(root, initial_project=arguments.project, initial_theme=arguments.theme)
    if arguments.demo_view != "main":
        root.after(650, lambda: open_demo_view(studio, arguments.demo_view))
    elif not arguments.skip_startup_release_notes:
        root.after(520, studio.show_release_notes_if_needed)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
