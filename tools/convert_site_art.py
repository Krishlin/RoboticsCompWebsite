"""Re-encode the landing page's flat artwork as WebP at web sizes.

The art arrives from SRC as full-resolution PNG — the Hill spec sheet is
1950 px wide and 198 KB, the kit photograph 1381 px and 434 KB — and the page
never shows either above about 600 CSS px. Serving the originals means a
phone on a gym's cell signal downloads roughly six hundred kilobytes it
cannot use a pixel of, which on this page is more than everything else put
together.

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
    "kit_parts.png": [520, 900],
}

QUALITY = 84


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
