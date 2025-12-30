from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def load_ascii_map(path: Path) -> list[str]:
    #keep spaces strip trailing new lines
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return [""]
    return lines

def pad_to_rect(lines: list[str]) -> tuple[list[str], int, int]:
    h = len(lines)
    w = max((len(line) for line in lines), default=0)
    padded = [line.ljust(w, " ") for line in lines]
    return padded, w, h

def pick_monospace_font(font_path: str | None, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
     # If you pass --font as an arg use it otherwise use a common monospace.
    if font_path:
        return ImageFont.truetype(font_path, font_size)

    # Best-effort defaults; if none exist, fall back to PIL's default (not always monospace).
    candidates = [
        "DejaVuSansMono.ttf",
        "DejaVuSansMono-Regular.ttf",
        "LiberationMono-Regular.ttf",
        "Consolas.ttf",
        "Menlo.ttc",
        "Courier New.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, font_size)
        except Exception:
            pass
    return ImageFont.load_default()

def measure_cell(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, cell_w: int | None, cell_h: int | None):
    #if no cell size derive from font metrics
    if cell_w is None or cell_h is None:
        bbox = draw.textbbox((0, 0), "M", font=font)

        glyph_w = bbox[2] - bbox[0]
        glyph_h = bbox[3] - bbox[1]

        default_w = glyph_w + 6
        default_h = glyph_h + 6

        return cell_w or default_w, cell_h or default_h
    return cell_w, cell_h

def render_ascii_to_image(
    lines: list[str],
    out_path: Path,
    *,
    font_path: str | None,
    font_size: int,
    cell_w: int | None,
    cell_h: int | None,
    margin: int,
    bg: str,
    fg: str,
    grid: bool,
    grid_color: str,
    grid_width: int,
) -> None:
    padded, w_chars, h_chars = pad_to_rect(lines)

    if w_chars == 0 or h_chars == 0:
        Image.new("RGBA", (1, 1), bg).save(out_path)
        return
    
    tmp = Image.new("RGBA", (10, 10), bg)
    tmp_draw = ImageDraw.Draw(tmp)
    font = pick_monospace_font(font_path, font_size)

    cell_w, cell_h = measure_cell(tmp_draw, font, cell_w, cell_h)

    img_w = margin * 2 + w_chars * cell_w
    img_h = margin * 2 + h_chars * cell_h

    img = Image.new("RGBA", (img_w, img_h), bg)
    draw = ImageDraw.Draw(img)
    for y, line in enumerate(padded):
        for x, ch, in enumerate(line):
            cx0 = margin + x * cell_w
            cy0 = margin + y * cell_h

            bbox = draw.textbbox((0, 0), ch, font=font)
            gw = bbox[2] - bbox[0]
            gh = bbox[3] - bbox[1]

            tx = cx0 + (cell_w - gw) // 2 - bbox[0]
            ty = cy0 + (cell_h - gh) // 2 - bbox[1]

            draw.text((tx, ty), ch, fill=fg, font=font)

    if grid:
        left = margin
        top = margin
        right = margin + w_chars * cell_w
        bottom = margin + h_chars * cell_h

        for x in range(w_chars + 1):
            xx = left + x * cell_w
            draw.line([(xx, top), (xx, bottom)], fill=grid_color, width=grid_width)

        for y in range(h_chars + 1):
            yy = top + y * cell_h
            draw.line([(left, yy), (right, yy)], fill=grid_color, width=grid_width)

    img.save(out_path)

def main() -> int:
    ap = argparse.ArgumentParser(description="Convert an ASCII map text file to a PNG with optional grid lines.")
    ap.add_argument("input", type=Path, help="Path to ASCII map file (txt).")
    ap.add_argument("-o", "--output", type=Path, default=Path("out.png"), help="Output PNG path.")
    ap.add_argument("--font", type=str, default=None, help="Path to a .ttf/.otf monospace font (optional).")
    ap.add_argument("--font-size", type=int, default=18, help="Font size in points.")
    ap.add_argument("--cell-w", type=int, default=None, help="Cell width in pixels (optional).")
    ap.add_argument("--cell-h", type=int, default=None, help="Cell height in pixels (optional).")
    ap.add_argument("--margin", type=int, default=16, help="Outer margin in pixels.")
    ap.add_argument("--bg", type=str, default="#0b0f14", help="Background color.")
    ap.add_argument("--fg", type=str, default="#e6edf3", help="Text color.")
    ap.add_argument("--grid", action="store_true", help="Enable grid lines.")
    ap.add_argument("--grid-color", type=str, default="#2b3440", help="Grid line color.")
    ap.add_argument("--grid-width", type=int, default=1, help="Grid line width in pixels.")
    args = ap.parse_args()

    lines = load_ascii_map(args.input)
    render_ascii_to_image(
        lines,
        args.output,
        font_path=args.font,
        font_size=args.font_size,
        cell_w=args.cell_w,
        cell_h=args.cell_h,
        margin=args.margin,
        bg=args.bg,
        fg=args.fg,
        grid=args.grid,
        grid_color=args.grid_color,
        grid_width=args.grid_width,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
