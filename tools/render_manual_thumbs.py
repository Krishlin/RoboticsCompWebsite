"""Rasterise the game manual into page thumbnails for the landing page.

The landing page shows every page of the manual as a contact sheet, which is
the point it is making: the whole rulebook is nine pages. Rendering those in
the browser meant shipping a PDF rasteriser to every visitor and stalling the
page on slow machines — the machines this competition exists to include. So
the pages are rendered here instead and served as ordinary images.

Run this whenever the manual is replaced:

    python tools/render_manual_thumbs.py

It writes app/static/img/manual/page-N.webp and rewrites the manifest that
the landing route reads. pypdfium2 is a tooling dependency, needed to run
this script and not to run the site.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = ROOT / "app" / "static" / "docs" / "summit-manual-v1.0.pdf"
OUT_DIR = ROOT / "app" / "static" / "img" / "manual"
MANIFEST = OUT_DIR / "manifest.json"

# Widest slot on the page is about 135 CSS px, so this is comfortably past 2x
# on a retina display while keeping each file small.
TARGET_WIDTH = 440


def render(pdf_path: Path, out_dir: Path, target_width: int) -> dict:
    """Render every page of *pdf_path* into *out_dir*. Returns the manifest.

    Raises FileNotFoundError if the PDF is missing and ImportError if the
    tooling dependency is absent; both are reported with a fix by main().
    """
    import pypdfium2  # imported here so --help style use doesn't need it

    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    # Clear stale pages first: a manual that loses a page would otherwise
    # leave the old last page behind and the sheet would claim one too many.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    pdf = pypdfium2.PdfDocument(pdf_path)
    try:
        pages = []
        for index, page in enumerate(pdf, start=1):
            width, _height = page.get_size()
            image = page.render(scale=target_width / width).to_pil()
            name = f"page-{index}.webp"
            image.save(out_dir / name, "WEBP", quality=88, method=6)
            pages.append(
                {
                    "page": index,
                    "file": name,
                    "width": image.width,
                    "height": image.height,
                }
            )
    finally:
        pdf.close()

    manifest = {
        "source": pdf_path.name,
        "count": len(pages),
        "pages": pages,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    try:
        manifest = render(PDF_PATH, OUT_DIR, TARGET_WIDTH)
    except FileNotFoundError as exc:
        print(f"No manual at {exc}. Copy the PDF there and run again.", file=sys.stderr)
        return 1
    except ImportError as exc:
        # Name the module that is actually missing: this needs both pypdfium2
        # and Pillow, and "install pypdfium2" is unhelpful when Pillow is the
        # one that is absent.
        missing = exc.name or "a required module"
        print(
            f"{missing} is not installed. Run: pip install pypdfium2 pillow",
            file=sys.stderr,
        )
        return 1

    total = sum((OUT_DIR / p["file"]).stat().st_size for p in manifest["pages"])
    print(f"Rendered {manifest['count']} pages to {OUT_DIR}")
    print(f"Total {total / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
