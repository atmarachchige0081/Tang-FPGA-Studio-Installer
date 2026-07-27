"""Generate the application icon and version-specific Windows metadata."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def parse_version() -> tuple[str, tuple[int, int, int, int]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.2.0")
    value = parser.parse_args().version
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"Expected a semantic version such as 1.2.0, received {value!r}")
    return value, (int(parts[0]), int(parts[1]), int(parts[2]), 0)


def write_version_metadata(version: str, numeric: tuple[int, int, int, int]) -> None:
    metadata = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric!r},
    prodvers={numeric!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Tang Primer FPGA Studio contributors'),
        StringStruct('FileDescription', 'Beginner-friendly Tang Primer 20K FPGA IDE'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'TangPrimerFPGAStudio'),
        StringStruct('LegalCopyright', 'MIT licensed'),
        StringStruct('OriginalFilename', 'TangPrimerFPGAStudio.exe'),
        StringStruct('ProductName', 'Tang Primer FPGA Studio'),
        StringStruct('ProductVersion', '{version}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    (ASSETS / "version_info.txt").write_text(metadata, encoding="utf-8", newline="\n")
    (ROOT / "src" / "build_version.py").write_text(
        f'"""Version injected by the installer build and upstream synchronization jobs."""\n\nAPP_VERSION = "{version}"\n',
        encoding="utf-8",
        newline="\n",
    )


def icon_image(size: int) -> Image.Image:
    scale = size / 256
    image = Image.new("RGBA", (size, size), (8, 16, 31, 255))
    draw = ImageDraw.Draw(image)

    def box(values: tuple[int, int, int, int], fill, outline=None, width=1):
        draw.rounded_rectangle(
            tuple(round(value * scale) for value in values),
            radius=max(1, round(24 * scale)),
            fill=fill,
            outline=outline,
            width=max(1, round(width * scale)),
        )

    box((18, 18, 238, 238), (13, 27, 49, 255), (35, 211, 238, 255), 8)
    box((64, 64, 192, 192), (18, 43, 72, 255), (123, 97, 255, 255), 6)

    pin_color = (35, 211, 238, 255)
    pin_width = max(2, round(9 * scale))
    for offset in (79, 112, 145, 178):
        coordinate = round(offset * scale)
        draw.line((round(35 * scale), coordinate, round(64 * scale), coordinate), fill=pin_color, width=pin_width)
        draw.line((round(192 * scale), coordinate, round(221 * scale), coordinate), fill=pin_color, width=pin_width)
        draw.line((coordinate, round(35 * scale), coordinate, round(64 * scale)), fill=pin_color, width=pin_width)
        draw.line((coordinate, round(192 * scale), coordinate, round(221 * scale)), fill=pin_color, width=pin_width)

    wave = [(79, 144), (100, 144), (100, 105), (126, 105), (126, 158), (153, 158), (153, 118), (177, 118)]
    draw.line(
        [(round(x * scale), round(y * scale)) for x, y in wave],
        fill=(255, 196, 74, 255),
        width=max(2, round(10 * scale)),
        joint="curve",
    )
    return image


version, numeric_version = parse_version()
sizes = (16, 24, 32, 48, 64, 128, 256)
images = [icon_image(size) for size in sizes]
images[-1].save(ASSETS / "TangPrimerFPGAStudio.ico", format="ICO", append_images=images[:-1], sizes=[(s, s) for s in sizes])
images[-1].save(ASSETS / "TangPrimerFPGAStudio.png", format="PNG")
write_version_metadata(version, numeric_version)
print(ASSETS / "TangPrimerFPGAStudio.ico")
