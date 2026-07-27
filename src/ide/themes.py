"""Validated semantic color themes for Tang Primer FPGA Studio.

Keeping colors behind semantic names lets the complete Tk interface switch
themes without rebuilding the workspace or losing editor state.
"""

from __future__ import annotations

import re


DEFAULT_THEME = "dark"

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#15181d",
        "header": "#1a1e24",
        "panel": "#20252c",
        "panel_alt": "#292f38",
        "panel_hover": "#323a45",
        "editor": "#181c22",
        "console": "#161a1f",
        "border": "#46515f",
        "border_soft": "#343d48",
        "text": "#f2f4f7",
        "muted": "#bac2cc",
        "muted_2": "#aab4c0",
        "accent": "#2f6fed",
        "accent_hover": "#255ac4",
        "accent_text": "#8fb5ff",
        "on_accent": "#ffffff",
        "blue": "#72a7ff",
        "green": "#65d19e",
        "yellow": "#f2ce72",
        "red": "#ff8796",
        "purple": "#c5a3ff",
        "cyan": "#6cccd5",
        "orange": "#f2ad72",
        "selection": "#375a8f",
        "selection_text": "#ffffff",
        "tooltip": "#303741",
        "cursor": "#ffffff",
        "editor_signal": "#a6d4ff",
        "editor_comment": "#a6b0bd",
        "editor_string": "#9bd49f",
        "current_line": "#222832",
        "success_button": "#19734a",
        "success_hover": "#1d7a4e",
        "danger_button": "#8c3040",
        "danger_hover": "#a63a4d",
    },
    "light": {
        "bg": "#f2f1ee",
        "header": "#ffffff",
        "panel": "#ffffff",
        "panel_alt": "#f7f6f3",
        "panel_hover": "#eeece7",
        "editor": "#fcfbf8",
        "console": "#f7f6f3",
        "border": "#aeb7c2",
        "border_soft": "#d6dbe1",
        "text": "#20242b",
        "muted": "#4e5b6a",
        "muted_2": "#586575",
        "accent": "#365fd9",
        "accent_hover": "#2b4eb5",
        "accent_text": "#294daf",
        "on_accent": "#ffffff",
        "blue": "#175cd3",
        "green": "#087443",
        "yellow": "#795300",
        "red": "#c1153c",
        "purple": "#6941c6",
        "cyan": "#0e6f85",
        "orange": "#a84400",
        "selection": "#d7e2fa",
        "selection_text": "#20242b",
        "tooltip": "#20242b",
        "cursor": "#101828",
        "editor_signal": "#005a9c",
        "editor_comment": "#596a82",
        "editor_string": "#207227",
        "current_line": "#f0eee9",
        "success_button": "#087443",
        "success_hover": "#05603a",
        "danger_button": "#b42318",
        "danger_hover": "#912018",
    },
}

THEME_KEYS = frozenset(THEMES[DEFAULT_THEME])
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

# Text pairs use WCAG AA's 4.5:1 target. Semantic status colors are also held
# to 4.5:1 so they remain readable when a platform renders them as small text.
TEXT_CONTRAST_PAIRS = (
    ("text", "bg"),
    ("text", "header"),
    ("text", "panel"),
    ("text", "panel_alt"),
    ("text", "editor"),
    ("muted", "header"),
    ("muted", "panel"),
    ("muted_2", "panel"),
    ("on_accent", "accent"),
    ("on_accent", "accent_hover"),
    ("on_accent", "success_button"),
    ("on_accent", "success_hover"),
    ("on_accent", "danger_button"),
    ("on_accent", "danger_hover"),
    ("selection_text", "selection"),
    ("on_accent", "tooltip"),
    ("cursor", "editor"),
    ("accent_text", "panel"),
    ("editor_signal", "editor"),
    ("editor_comment", "editor"),
    ("editor_string", "editor"),
)
SEMANTIC_CONTRAST_PAIRS = tuple(
    (foreground, background)
    for foreground in ("blue", "green", "yellow", "red", "purple", "cyan", "orange")
    for background in ("panel", "editor")
)


def normalize_theme(value: object, fallback: str = DEFAULT_THEME) -> str:
    """Return a known theme name, safely falling back for corrupt settings."""
    if isinstance(value, str) and value.strip().lower() in THEMES:
        return value.strip().lower()
    return fallback if fallback in THEMES else DEFAULT_THEME


def theme_colors(name: object) -> dict[str, str]:
    """Return a defensive copy so callers cannot mutate the registry."""
    return dict(THEMES[normalize_theme(name)])


def _linear_channel(value: int) -> float:
    channel = value / 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    """Calculate WCAG relative luminance for a six-digit hexadecimal color."""
    if not HEX_COLOR.fullmatch(color):
        raise ValueError(f"Invalid hexadecimal color: {color!r}")
    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    return 0.2126 * _linear_channel(red) + 0.7152 * _linear_channel(green) + 0.0722 * _linear_channel(blue)


def contrast_ratio(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two opaque colors."""
    bright, dark = sorted((relative_luminance(foreground), relative_luminance(background)), reverse=True)
    return (bright + 0.05) / (dark + 0.05)


def validate_themes() -> list[str]:
    """Return actionable palette errors; an empty list is release-ready."""
    problems: list[str] = []
    for name, palette in THEMES.items():
        missing = sorted(THEME_KEYS - palette.keys())
        extra = sorted(palette.keys() - THEME_KEYS)
        if missing:
            problems.append(f"{name}: missing tokens {', '.join(missing)}")
        if extra:
            problems.append(f"{name}: unexpected tokens {', '.join(extra)}")
        for token, color in palette.items():
            if not HEX_COLOR.fullmatch(color):
                problems.append(f"{name}.{token}: invalid color {color!r}")
        for foreground, background in TEXT_CONTRAST_PAIRS:
            if foreground in palette and background in palette:
                ratio = contrast_ratio(palette[foreground], palette[background])
                if ratio < 4.5:
                    problems.append(
                        f"{name}: {foreground}/{background} contrast {ratio:.2f}:1 is below 4.5:1"
                    )
        for foreground, background in SEMANTIC_CONTRAST_PAIRS:
            if foreground in palette and background in palette:
                ratio = contrast_ratio(palette[foreground], palette[background])
                if ratio < 4.5:
                    problems.append(
                        f"{name}: {foreground}/{background} contrast {ratio:.2f}:1 is below 4.5:1"
                    )
    return problems
