"""Validated semantic color themes for Tang Primer FPGA Studio.

Keeping colors behind semantic names lets the complete Tk interface switch
themes without rebuilding the workspace or losing editor state.
"""

from __future__ import annotations

import re


DEFAULT_THEME = "dark"

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#070b14",
        "header": "#0b1120",
        "panel": "#0f1728",
        "panel_alt": "#151f34",
        "panel_hover": "#1c2a45",
        "editor": "#0a1020",
        "console": "#080d17",
        "border": "#253451",
        "border_soft": "#1a2740",
        "text": "#e8f0ff",
        "muted": "#9aa8c3",
        "muted_2": "#8795b1",
        "accent": "#665cf2",
        "accent_hover": "#554bda",
        "accent_text": "#b1acff",
        "on_accent": "#ffffff",
        "blue": "#63a9ff",
        "green": "#42d392",
        "yellow": "#f4c95d",
        "red": "#ff7187",
        "purple": "#d2a8ff",
        "cyan": "#65dce5",
        "orange": "#ffb678",
        "selection": "#284677",
        "selection_text": "#ffffff",
        "tooltip": "#202b43",
        "cursor": "#ffffff",
        "editor_signal": "#9cdcfe",
        "editor_comment": "#8b9ab8",
        "editor_string": "#a6e3a1",
        "current_line": "#121e33",
        "success_button": "#19734a",
        "success_hover": "#1d7a4e",
        "danger_button": "#8c3040",
        "danger_hover": "#a63a4d",
    },
    "light": {
        "bg": "#e9eef5",
        "header": "#fbfcfe",
        "panel": "#ffffff",
        "panel_alt": "#f2f5f9",
        "panel_hover": "#e4eaf2",
        "editor": "#f8fafc",
        "console": "#f3f6fa",
        "border": "#b8c4d3",
        "border_soft": "#d3dce7",
        "text": "#172033",
        "muted": "#4c5d75",
        "muted_2": "#5b6b82",
        "accent": "#5146d8",
        "accent_hover": "#4036bb",
        "accent_text": "#4036bb",
        "on_accent": "#ffffff",
        "blue": "#175cd3",
        "green": "#087443",
        "yellow": "#795300",
        "red": "#c1153c",
        "purple": "#6941c6",
        "cyan": "#0e6f85",
        "orange": "#a84400",
        "selection": "#cad8f2",
        "selection_text": "#172033",
        "tooltip": "#172033",
        "cursor": "#101828",
        "editor_signal": "#005a9c",
        "editor_comment": "#596a82",
        "editor_string": "#207227",
        "current_line": "#e8eef8",
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
