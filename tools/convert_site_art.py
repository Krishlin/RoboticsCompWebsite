"""Re-encode the landing page's flat artwork as WebP at web sizes.

The art arrives from SRC as full-resolution PNG — the Hill spec sheet is
1950 px wide and 198 KB, the kit render 3282 px and 1.5 MB — and the page
never shows either above about 670 CSS px. Serving the originals means a
phone on a gym's cell signal downloads well over a megabyte it cannot use a
pixel of, which on this page is more than everything else put together.

Run this when the art in app/static/img is replaced:

    pip install -r tools/requirements.txt
    python tools/convert_site_art.py

It writes <name>-<width>.webp beside each source and a manifest the landing
route reads. The PNGs stay where they are: they are the originals, and the
template falls back to them when a conversion has not been run.

The robot renders are not handled here — they need cutting out of their
studio background first, which is tools/render_bot_views.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "app" / "static" / "img"
MANIFEST = IMG_DIR / "art-manifest.json"

# Source filename -> the widths the page asks for. The larger entry covers a
# 2x phone and a desktop; the smaller is what a 1x phone actually downloads.
ART = {
    "summit_hill_named.png": [640, 1100],
    # The kit layout is the one piece of art with fine detail in it — pin
    # legends, board silkscreen — and it is shown at 668 CSS px on a desktop,
    # so it carries a third size a 2x screen can actually use. 104 KB, and
    # only a retina desktop ever asks for it.
    "kit_parts.png": [520, 900, 1340],
    # The footer shows this at 180 CSS px, so 320 is the 1x file and 640
    # covers a 2x screen with room to spare. It is 10 KB and 23 KB.
    "stemsters_logo.png": [320, 640],
}

QUALITY = 84

# Art that arrives on a canvas larger than the artwork on it. The kit render
# is drawn with about 400 px of empty space to either side, which on the page
# is not framing: it is a quarter of the column spent on nothing, and it makes
# the same layout read a quarter smaller than the render it replaced. Cropped
# back to the artwork here rather than in the source file, so the original
# stays the original.
TRIM = {"kit_parts.png"}

# Margin left around trimmed art, as a fraction of its width. 1.5% is what the
# kit render carried before its canvas grew, so trimming to it lands the new
# art on the old one's proportions and the section's layout does not move.
TRIM_MARGIN = 0.015


def _trim(image):
    """Crop transparent canvas back to the artwork, leaving an even margin.

    The crop is taken flush and the margin added back afterwards, rather than
    widening the crop box and clamping it at the edges: artwork that already
    sits against one side would otherwise come out with a margin on three.

    Returns the image unchanged when there is nothing to trim — fully opaque,
    or fully transparent, which getbbox reports as None.
    """
    from PIL import ImageOps

    box = image.getchannel("A").getbbox()
    if box is None or box == (0, 0, image.width, image.height):
        return image

    content = image.crop(box)
    return ImageOps.expand(
        content, round(content.width * TRIM_MARGIN), (0, 0, 0, 0)
    )


def convert(img_dir: Path) -> dict:
    """Write every size of every entry in ART. Returns the manifest.

    Raises FileNotFoundError naming the first missing source, and ImportError
    if Pillow is absent; main() reports both with a fix.
    """
    from PIL import Image

    missing = [name for name in ART if not (img_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(img_dir / missing[0])

    art = {}
    for name, widths in ART.items():
        with Image.open(img_dir / name) as source:
            # Some of this art carries an alpha channel it does not use;
            # RGBA WebP is meaningfully larger, so only keep it if a pixel
            # is actually transparent.
            image = source.convert("RGBA")
            if name in TRIM:
                image = _trim(image)
            if image.getchannel("A").getextrema()[0] == 255:
                image = image.convert("RGB")

            sizes = []
            seen = set()
            for width in sorted(widths):
                scaled = image
                if width < image.width:
                    height = round(image.height * width / image.width)
                    scaled = image.resize((width, height), Image.LANCZOS)
                if scaled.width in seen:
                    continue
                seen.add(scaled.width)
                out_name = f"{Path(name).stem}-{scaled.width}.webp"
                scaled.save(
                    img_dir / out_name, "WEBP", quality=QUALITY, method=6
                )
                sizes.append(
                    {
                        "file": out_name,
                        "width": scaled.width,
                        "height": scaled.height,
                    }
                )

        art[name] = {"source": name, "sizes": sizes}

    MANIFEST.write_text(json.dumps(art, indent=2) + "\n", encoding="utf-8")
    return art


def main() -> int:
    try:
        art = convert(IMG_DIR)
    except FileNotFoundError as exc:
        print(f"No artwork at {exc}.", file=sys.stderr)
        return 1
    except ImportError as exc:
        missing = exc.name or "a required module"
        print(
            f"{missing} is not installed. Run: pip install -r tools/requirements.txt",
            file=sys.stderr,
        )
        return 1

    for name, entry in art.items():
        was = (IMG_DIR / name).stat().st_size
        now = sum((IMG_DIR / size["file"]).stat().st_size for size in entry["sizes"])
        smallest = (IMG_DIR / entry["sizes"][0]["file"]).stat().st_size
        print(
            f"{name}: {was / 1024:.0f} KB -> "
            f"{now / 1024:.0f} KB in {len(entry['sizes'])} sizes "
            f"({smallest / 1024:.0f} KB for a phone)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
