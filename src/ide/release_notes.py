"""Versioned release-note content and first-launch preference helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import MutableMapping


@dataclass(frozen=True)
class ReleaseHighlight:
    title: str
    description: str
    icon: str


@dataclass(frozen=True)
class ReleaseNotes:
    version: str
    eyebrow: str
    title: str
    summary: str
    highlights: tuple[ReleaseHighlight, ...]


V1_2_0_NOTES = ReleaseNotes(
    version="1.2.0",
    eyebrow="STUDIO RELEASE  •  VERSION 1.2.0",
    title="A clearer path from first module to real hardware",
    summary=(
        "This release turns the studio into a more complete learning workspace: "
        "create a project, understand the RTL, verify it, inspect the synthesized "
        "design, and communicate with the board without leaving the IDE."
    ),
    highlights=(
        ReleaseHighlight(
            "Create with confidence",
            "A guided wizard creates a complete, verified project instead of an empty file.",
            "plus",
        ),
        ReleaseHighlight(
            "Understand synthesized hardware",
            "Search components, group implementation cells, and inspect local fan-in and fan-out.",
            "dashboard",
        ),
        ReleaseHighlight(
            "Learn HDL in context",
            "Definitions, references, completions, instances, and 72 patterns support the editor.",
            "sparkle",
        ),
        ReleaseHighlight(
            "Verify deliberately",
            "Choose tests and wave layouts, read PASS/FAIL results, and jump from diagnostics to source.",
            "lint",
        ),
        ReleaseHighlight(
            "Talk to your FPGA",
            "Auto-detect COM ports and send or receive ASCII and hexadecimal data inside the IDE.",
            "terminal",
        ),
        ReleaseHighlight(
            "Comfortable in either theme",
            "Natural dark and accessible light modes re-theme the live workspace and remember your choice.",
            "theme",
        ),
    ),
)


RELEASES: dict[str, ReleaseNotes] = {V1_2_0_NOTES.version: V1_2_0_NOTES}


def notes_for_version(version: str) -> ReleaseNotes:
    """Return the exact notes for a known application version."""
    try:
        return RELEASES[version]
    except KeyError as error:
        raise ValueError(f"No release notes are registered for version {version}") from error


def release_notes_pending(settings: MutableMapping[str, object], version: str) -> bool:
    """Whether this exact version has not yet been presented to the user."""
    return settings.get("release_notes_seen") != version


def mark_release_notes_seen(settings: MutableMapping[str, object], version: str) -> None:
    """Record that the current version's notes have been presented."""
    settings["release_notes_seen"] = version
