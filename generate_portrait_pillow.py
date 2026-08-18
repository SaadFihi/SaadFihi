#!/usr/bin/env python3
"""
Generate a self-typing ASCII-art portrait as an animated SVG for a GitHub profile.
PILLOW-ONLY version — no OpenCV, no NumPy. Installs in seconds:

    python3 -m pip install pillow

Pipeline:
  1. Grayscale + (optional) trim near-white borders.
  2. Smoothing pass (Pillow) -> stand-in for OpenCV's bilateral filter.
  3. Autocontrast -> stand-in for CLAHE (global, not per-tile, but fine for
     a well-lit photo with a plain background).
  4. Darkening curve (v/255)^GAMMA -> the key fix; keeps glasses/brows/lips alive.
  5. Downscale to COLS wide, map brightness to a 13-level ramp.
  6. Emit an SVG where each row is revealed left-to-right (SMIL typing animation).

Usage:
  python3 generate_portrait_pillow.py me.jpg -o portrait.svg --preview
  python3 generate_portrait_pillow.py me.jpg --cols 90 --gamma 2.1
"""

import argparse
import sys
import html

from PIL import Image, ImageOps, ImageFilter

# ---- The ramp: dark -> light. Trailing space clears background to nothing. ----
RAMP = "@%#sc*+=-:.` "  # index 0 = darkest, last = space (lightest)

# Grid geometry the guide bakes in: advance width exactly 0.600 em.
FONT_SIZE = 12.9
CHAR_W = 7.74          # 0.600 * 12.9
LINE_H = FONT_SIZE
CHAR_ASPECT = 0.48     # rows = cols * (h/w) * 0.48 (mono chars ~2x tall as wide)


def load_and_prep(path):
    """Return a grayscale PIL image."""
    try:
        img = Image.open(path)
    except Exception as e:
        sys.exit(f"[error] could not read image: {path} ({e})")
    # Flatten any alpha onto white, then grayscale.
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img).convert("RGB")
    return img.convert("L")


def enhance(gray, gamma):
    from PIL import ImageOps as _IO
    gray = _IO.invert(gray)          # flip: dark<->light
    # Smoothing: soften skin noise while keeping overall shape.
    g = gray.filter(ImageFilter.SMOOTH)
    # Autocontrast: stretch the tonal range (global stand-in for CLAHE).
    g = ImageOps.autocontrast(g, cutoff=1)
    # Darkening curve — THE fix. Applied via a per-pixel lookup table.
    lut = [int(round(((v / 255.0) ** gamma) * 255)) for v in range(256)]
    g = g.point(lut)
    return g


def to_ascii(gray, cols):
    w, h = gray.size
    rows = max(1, int(round(cols * (h / w) * CHAR_ASPECT)))
    small = gray.resize((cols, rows), Image.LANCZOS)
    px = small.load()
    n = len(RAMP)
    lines = []
    for y in range(rows):
        chars = []
        for x in range(cols):
            v = px[x, y]
            idx = round((v / 255.0) * (n - 1))
            idx = max(0, min(n - 1, idx))
            chars.append(RAMP[idx])
        lines.append("".join(chars))
    return lines


def build_svg(lines, display_width, stagger, fg="#e6edf3", bg="none"):
    cols = max(len(l) for l in lines)
    rows = len(lines)
    grid_w = cols * CHAR_W
    grid_h = rows * LINE_H
    scale = display_width / grid_w
    disp_h = grid_h * scale

    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{display_width:.0f}" height="{disp_h:.0f}" '
        f'viewBox="0 0 {grid_w:.2f} {grid_h:.2f}" '
        f'font-family="\'JetBrains Mono\', \'Liberation Mono\', \'DejaVu Sans Mono\', monospace" '
        f'font-size="{FONT_SIZE}">'
    )
    if bg != "none":
        parts.append(f'<rect width="100%" height="100%" fill="{bg}"/>')

    parts.append("<defs>")
    for i in range(rows):
        y = i * LINE_H
        begin = i * stagger
        parts.append(
            f'<clipPath id="c{i}">'
            f'<rect x="0" y="{y:.2f}" width="0" height="{LINE_H:.2f}">'
            f'<animate attributeName="width" from="0" to="{grid_w:.2f}" '
            f'dur="0.9s" begin="{begin:.2f}s" fill="freeze" calcMode="linear"/>'
            f'</rect></clipPath>'
        )
    parts.append("</defs>")

    for i, line in enumerate(lines):
        baseline = i * LINE_H + FONT_SIZE * 0.82
        safe = html.escape(line).replace(" ", "&#160;")
        parts.append(
            f'<text x="0" y="{baseline:.2f}" xml:space="preserve" '
            f'fill="{fg}" clip-path="url(#c{i})">{safe}</text>'
        )
        begin = i * stagger
        parts.append(
            f'<rect y="{i*LINE_H:.2f}" width="{CHAR_W:.2f}" height="{LINE_H:.2f}" '
            f'fill="{fg}" opacity="0.85">'
            f'<animate attributeName="x" from="0" to="{grid_w:.2f}" '
            f'dur="0.9s" begin="{begin:.2f}s" fill="freeze" calcMode="linear"/>'
            f'<set attributeName="opacity" to="0" begin="{begin+0.9:.2f}s"/>'
            f'</rect>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="input photo (jpg/png)")
    ap.add_argument("-o", "--output", default="portrait.svg")
    ap.add_argument("--cols", type=int, default=90,
                    help="character columns (guide recommends ~90)")
    ap.add_argument("--gamma", type=float, default=1.7,
                    help="darkening curve exponent; higher = darker midtones")
    ap.add_argument("--width", type=float, default=460,
                    help="displayed width in px (guide uses 460)")
    ap.add_argument("--stagger", type=float, default=0.09,
                    help="seconds between row starts")
    ap.add_argument("--fg", default="#e6edf3", help="text color")
    ap.add_argument("--preview", action="store_true",
                    help="also print the ASCII to the terminal")
    args = ap.parse_args()

    gray = load_and_prep(args.input)
    gray = enhance(gray, gamma=args.gamma)
    lines = to_ascii(gray, cols=args.cols)

    if args.preview:
        print("\n".join(lines))

    svg = build_svg(lines, display_width=args.width, stagger=args.stagger, fg=args.fg)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(svg)

    total = len(lines) * args.stagger + 0.9
    print(f"[ok] wrote {args.output}  ({args.cols} cols x {len(lines)} rows, "
          f"~{total:.1f}s to finish typing)")


if __name__ == "__main__":
    main()
