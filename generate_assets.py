"""Generate the multi-resolution Windows application icon."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


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


sizes = (16, 24, 32, 48, 64, 128, 256)
images = [icon_image(size) for size in sizes]
images[-1].save(ASSETS / "TangPrimerFPGAStudio.ico", format="ICO", append_images=images[:-1], sizes=[(s, s) for s in sizes])
images[-1].save(ASSETS / "TangPrimerFPGAStudio.png", format="PNG")
print(ASSETS / "TangPrimerFPGAStudio.ico")
