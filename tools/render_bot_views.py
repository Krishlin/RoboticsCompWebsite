"""Cut the kit-robot CAD renders out of their studio background for the web.

The renders arrive as 1920x1080 PNGs of the robot floating on a smooth grey
studio gradient, about 3 MB each. Shipped as-is they would be the heaviest
thing on the landing page by an order of magnitude, and the grey ground fights
both the paper and the ink sections of the site. So they are cut out here and
written as transparent WebP at the handful of widths the page actually asks
for, which is the difference between a phone on cell data downloading 21 MB
and downloading about a hundred kilobytes.

Run this whenever the renders are replaced:

    pip install -r tools/requirements.txt
    python tools/render_bot_views.py

It writes app/static/img/bot/<slug>-<width>.webp and a manifest the landing
route reads. The source folder is not needed to run the site.

How the cutout works
--------------------
The background is a smooth gradient, so it can be modelled: a degree-5
polynomial surface is least-squares fitted per channel to the outer frame of
the image, which is background by construction. Every pixel is then judged by
how far it sits from that model.

One threshold is not enough. A pixel far from the model is certainly the robot
(black tyres, red plastic, the yellow board). A pixel a little way from it is
either a pale grey LEGO beam or the soft contact shadow the robot casts, and
those two have to be told apart or the cutout either loses the chassis or
keeps a dirty halo. They are separated by shape rather than by colour: the
shadow is a thin ring hugging the silhouette, so eroding the weak mask deletes
it, while the beam is thick enough to survive. Eroding alone would also delete
genuinely thin parts, so the strong mask -- which the shadow never reaches --
is unioned back in, and that is what saves the micro:bit's aerial.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "Stemsters bod renders"
OUT_DIR = ROOT / "app" / "static" / "img" / "bot"
MANIFEST = OUT_DIR / "manifest.json"

# Source filename -> slug. Only these are published, and in this order, so
# dropping an extra experiment in the folder doesn't quietly ship it. The
# labels and captions live in app/routes.py with the rest of the page's copy.
VIEWS = [
    ("Top View Left Tilted.png", "three-quarter-left"),
    ("Front View.png", "front"),
    ("Top View Right Tilted.png", "three-quarter-right"),
    ("Left View.png", "left"),
    ("Right View 1.png", "right"),
    ("Top View Tilted.png", "above-tilted"),
    ("Top View.png", "above"),
]

# The stage tops out near 600 CSS px on a desktop and near 360 on a phone, so
# 1120 covers a 2x phone and a large desktop alike. 200 is the thumbnail rail.
WIDTHS = [200, 440, 760, 1120]

# Distance from the fitted background at which a pixel stops being background.
# Measured: across all seven renders the fit's own error never exceeds 0.019
# on the frame that was fitted, so 0.045 clears the noise floor with room to
# spare. STRONG is the level only the robot reaches, never its shadow.
WEAK = 0.045
STRONG = 0.15

# Pixels of the weak mask to shave off. The cast shadow is a soft ring a few
# pixels wide; this is comfortably wider than it and far narrower than any
# real part of the robot.
ERODE = 10

# Fitted on the outer frame of the image, which no render's robot comes near.
FRAME = 120
POLY_DEGREE = 5

# Skirt of bled colour kept around the silhouette, in source pixels. Has to
# exceed the reach of the resampling kernel at the largest downscale on offer
# (744 -> 200 is 3.7x, and Lanczos reaches three output pixels, so eleven
# source pixels); 24 is that with room to spare.
MARGIN = 24

LUMA = (0.2126, 0.7152, 0.0722)


def _poly_terms(x, y, degree: int):
    """Design matrix for a 2-D polynomial of *degree*, as an (h, w, terms) array."""
    import numpy as np

    return np.stack(
        [x**i * y**j for i in range(degree + 1) for j in range(degree + 1 - i)],
        axis=-1,
    )


def _background_residual(rgb):
    """Per-pixel distance from the fitted studio background, 0..1.

    Returns the residual of a blurred copy of the image: the renders carry
    per-pixel dither that no smooth surface can follow, and fitting against it
    raises the noise floor by a factor of three for nothing.
    """
    import numpy as np
    from scipy import ndimage

    smooth = np.dstack(
        [ndimage.gaussian_filter(rgb[..., c], 3.0) for c in range(3)]
    )

    height, width, _ = rgb.shape
    rows, cols = np.mgrid[0:height, 0:width]
    x = (cols / (width - 1)) * 2 - 1
    y = (rows / (height - 1)) * 2 - 1

    frame = np.zeros((height, width), bool)
    frame[:FRAME, :] = frame[-FRAME:, :] = True
    frame[:, :FRAME] = frame[:, -FRAME:] = True

    terms = _poly_terms(x, y, POLY_DEGREE)
    basis = terms[frame]
    fitted = np.empty_like(smooth)
    for channel in range(3):
        coefficients, *_ = np.linalg.lstsq(
            basis, smooth[..., channel][frame], rcond=None
        )
        fitted[..., channel] = terms @ coefficients

    return np.abs(smooth - fitted).max(axis=2)


def _largest_parts(mask, floor: float = 0.005):
    """Drop speckle: keep components at least *floor* of the largest one."""
    import numpy as np
    from scipy import ndimage

    labels, count = ndimage.label(mask)
    if count == 0:
        return mask
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    biggest = sizes.max()
    keep = [i + 1 for i in range(count) if sizes[i] >= floor * biggest]
    return np.isin(labels, keep)


def _silhouette(rgb):
    """Boolean mask of the robot. See the module docstring for the method."""
    import numpy as np
    from scipy import ndimage

    residual = _background_residual(rgb)

    weak = ndimage.binary_closing(residual > WEAK, np.ones((7, 7)))
    weak = ndimage.binary_fill_holes(weak)

    strong = ndimage.binary_closing(residual > STRONG, np.ones((5, 5)))
    strong = ndimage.binary_fill_holes(strong)

    mask = ndimage.binary_erosion(weak, iterations=ERODE) | strong
    mask = ndimage.binary_fill_holes(ndimage.binary_closing(mask, np.ones((5, 5))))
    return _largest_parts(mask)


def _bleed_colour(rgb, mask):
    """Flood each transparent pixel with its nearest opaque pixel's colour.

    Resampling an RGBA image mixes the colour of fully transparent pixels into
    the edge, and here that colour is the grey studio floor, which would leave
    every silhouette rimmed in grey at every size below full. Replacing it with
    the neighbouring robot colour first means there is nothing wrong to mix in.
    """
    from scipy import ndimage

    if mask.all():
        return rgb
    _, indices = ndimage.distance_transform_edt(~mask, return_indices=True)
    return rgb[tuple(indices)]


def _cut_out(path: Path):
    """Return (RGBA array, mask) for one render, still at source size."""
    import numpy as np
    from PIL import Image

    with Image.open(path) as handle:
        rgb = np.asarray(handle.convert("RGB"), dtype=np.float64) / 255.0

    mask = _silhouette(rgb)
    bled = _bleed_colour((rgb * 255).round().astype(np.uint8), mask)
    return np.dstack([bled, (mask * 255).astype(np.uint8)]), mask


def _bounds(mask):
    """(left, top, right, bottom) of the robot, with MARGIN of slack.

    The slack is not decoration. _bleed_colour has already painted the robot's
    own colours into the transparent pixels just outside the silhouette, and
    cropping with a margin is what carries that skirt into the file. Crop
    flush instead and every downscale mixes the silhouette with whatever lies
    beyond the crop -- which, once the view is centred on a shared canvas, is
    transparent black.
    """
    rows = mask.any(axis=1).nonzero()[0]
    cols = mask.any(axis=0).nonzero()[0]
    height, width = mask.shape
    return (
        int(max(0, cols[0] - MARGIN)),
        int(max(0, rows[0] - MARGIN)),
        int(min(width, cols[-1] + 1 + MARGIN)),
        int(min(height, rows[-1] + 1 + MARGIN)),
    )


def _canvas_size(bounds):
    """One canvas every view is centred on, large enough for the widest.

    All seven renders share a camera, so leaving them at source scale and
    giving them a common canvas keeps the robot the same size throughout the
    gallery -- crop each to its own bounds instead and it changes size every
    time the visitor swipes, which reads as a bug. The canvas has to be shared
    rather than the crop box: a side view's robot sits well off to one side of
    the frame, so a shared box would centre nothing and leave the profile
    views pinned to an edge.
    """
    width = max(right - left for left, _, right, _ in bounds)
    height = max(bottom - top for _, top, _, bottom in bounds)
    return width, height


def render(src_dir: Path, out_dir: Path) -> dict:
    """Cut out and write every view. Returns the manifest.

    Raises FileNotFoundError naming the first missing source render, and
    ImportError if a tooling dependency is absent; main() reports both.
    """
    import numpy as np  # noqa: F401  (imported here so --help needs no deps)
    from PIL import Image

    missing = [name for name, _ in VIEWS if not (src_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(src_dir / missing[0])

    cut = [(_cut_out(src_dir / name), slug) for name, slug in VIEWS]
    bounds = [_bounds(mask) for (_, mask), _ in cut]
    canvas = _canvas_size(bounds)

    # Clear first: a slug that goes away should not leave its files behind for
    # a manifest that no longer lists them to keep serving.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    views = []
    for ((rgba, _), slug), box in zip(cut, bounds):
        content = Image.fromarray(rgba, "RGBA").crop(box)
        full = Image.new("RGBA", canvas, (0, 0, 0, 0))
        full.paste(
            content,
            ((canvas[0] - content.width) // 2, (canvas[1] - content.height) // 2),
        )
        sizes = {}
        for width in WIDTHS:
            # Never upscale. A width past the crop's own resolution collapses
            # onto the full size, and asking for two of those would otherwise
            # write the same file twice under the same key.
            scaled = full
            if width < full.width:
                height = round(full.height * width / full.width)
                scaled = full.resize((width, height), Image.LANCZOS)
            if str(scaled.width) in sizes:
                continue
            name = f"{slug}-{scaled.width}.webp"
            scaled.save(out_dir / name, "WEBP", quality=82, method=6)
            sizes[str(scaled.width)] = {
                "file": name,
                "width": scaled.width,
                "height": scaled.height,
            }
        views.append({"slug": slug, "sizes": sizes})

    manifest = {
        "source": src_dir.name,
        "widths": sorted({int(w) for v in views for w in v["sizes"]}),
        "aspect": {"width": canvas[0], "height": canvas[1]},
        "views": views,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    try:
        manifest = render(SRC_DIR, OUT_DIR)
    except FileNotFoundError as exc:
        print(
            f"No render at {exc}. Put the CAD renders in {SRC_DIR.name}/ "
            "and run again.",
            file=sys.stderr,
        )
        return 1
    except ImportError as exc:
        # Name the module that is actually missing: this needs Pillow, numpy
        # and SciPy, and guessing wrong wastes the reader's time.
        missing = exc.name or "a required module"
        print(
            f"{missing} is not installed. Run: pip install -r tools/requirements.txt",
            file=sys.stderr,
        )
        return 1

    total = sum(
        (OUT_DIR / size["file"]).stat().st_size
        for view in manifest["views"]
        for size in view["sizes"].values()
    )
    print(f"Cut out {len(manifest['views'])} views to {OUT_DIR}")
    print(f"Widths {manifest['widths']} — {total / 1024:.0f} KB total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
