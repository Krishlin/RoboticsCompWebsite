"""Cut the photos picked for the past-events page down to web sizes.

Event photos arrive as a Drive download: gigabytes of camera JPEGs, iPhone
files, and video, most of it never meant for the site. The picks live in
app/past_events.py, named by source filename. This finds each one under the
folders you point it at, crops it if the entry says to, and writes WebP at
the widths the page asks for into app/static/img/events/<slug>/, with a
manifest the route joins the entries to.

Run it after adding or changing an event's photos:

    pip install -r tools/requirements.txt
    python tools/cut_event_photos.py "<download folder>" ["<another folder>" ...]

The download folders stay out of the repo and the deploy (.gitignore and
.vercelignore): they are large and full of students' faces, and only the
picked, resized copies are meant to be published.

Nothing is written unless every listed photo is found and opens, so a typo in
a filename never leaves an event with half a manifest. Metadata is not
carried over: the WebP files hold pixels only, with no EXIF, which on a phone
photo can include where it was taken.

Only formats Pillow reads are supported. The iPhone .DNG files in the
Summit 2026 download are JPEGs under a raw extension and open fine; true raw
files and HEIC do not, and are reported as unreadable.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "app" / "static" / "img" / "events"

# 640 is the gallery tile a phone downloads; 1280 covers a gallery tile on a
# 2x screen and the champions photo; 1920 is for the full-screen viewer. A
# source narrower than a width stops at its own width rather than upscaling.
WIDTHS = (640, 1280, 1920)

# Photographs, not flat art, so lower than the 84 the site art uses: at 80
# the gym's wood grain and the robots' wiring hold up and the files halve.
QUALITY = 80


def _load_events() -> tuple[list[dict], Callable[[dict], list[dict]]]:
    """PAST_EVENTS and all_photos from app/past_events.py, loaded by path.

    Importing it as app.past_events would run app/__init__.py first, which
    pulls in Flask and the database layer for no reason here.
    """
    path = ROOT / "app" / "past_events.py"
    spec = importlib.util.spec_from_file_location("past_events", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PAST_EVENTS, module.all_photos


def _index(folders: list[Path]) -> dict[str, list[Path]]:
    """Every file under the folders, by filename. Names can repeat."""
    found: dict[str, list[Path]] = {}
    for folder in folders:
        for path in folder.rglob("*"):
            if path.is_file():
                found.setdefault(path.name, []).append(path)
    return found


def _resolve(photos: list[dict], index: dict[str, list[Path]]) -> tuple[dict[str, Path], list[str]]:
    """Each photo's source file, plus a problem line for every one not usable."""
    sources: dict[str, Path] = {}
    problems: list[str] = []
    for photo in photos:
        name = photo["src"]
        matches = index.get(name, [])
        if not matches:
            problems.append(f"not found: {name}")
        elif len(matches) > 1:
            # Drive splits a big download into parts, so the same name in two
            # of them is possible. Picking one would be a guess.
            listed = ", ".join(str(m) for m in matches)
            problems.append(f"found more than once, rename one: {name} ({listed})")
        else:
            sources[name] = matches[0]
    return sources, problems


def _open(path: Path, crop: tuple[float, float, float, float] | None):
    """The photo upright, cropped, in sRGB, as an RGB image.

    Raises OSError if Pillow cannot read the file.
    """
    from PIL import Image, ImageCms, ImageOps

    image = Image.open(path)
    if crop is None:
        # Lets the JPEG decoder scale down while decoding: the iPhone frames
        # are 8064 px wide, and decoding at half size is most of the runtime
        # saved. draft never goes below the size asked for.
        image.draft("RGB", (max(WIDTHS), max(WIDTHS)))
    image = ImageOps.exif_transpose(image)

    # The iPhone photos are tagged Display P3. Dropping that tag without
    # converting would show them flat and dull in every browser, so convert
    # to sRGB first; a file whose profile will not parse keeps its pixels.
    icc = image.info.get("icc_profile")
    if icc:
        try:
            from io import BytesIO

            source_profile = ImageCms.ImageCmsProfile(BytesIO(icc))
            srgb = ImageCms.createProfile("sRGB")
            image = ImageCms.profileToProfile(image, source_profile, srgb, outputMode="RGB")
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass
    image = image.convert("RGB")

    if crop is not None:
        left, top, right, bottom = crop
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError(f"crop {crop} is not a box inside the frame")
        w, h = image.size
        image = image.crop((round(left * w), round(top * h), round(right * w), round(bottom * h)))
    return image


def _cut(image, stem: str, out_dir: Path) -> list[dict]:
    """Write each width of one photo; return them narrowest first."""
    from PIL import Image

    widths = [w for w in WIDTHS if w < image.width]
    # The source's own width is the largest it can honestly be served at.
    widths.append(min(image.width, max(WIDTHS)))

    sizes = []
    for width in sorted(set(widths)):
        height = round(image.height * width / image.width)
        resized = image if width == image.width else image.resize((width, height), Image.LANCZOS)
        name = f"{stem}-{width}.webp"
        resized.save(out_dir / name, "WEBP", quality=QUALITY, method=6)
        sizes.append({"file": name, "width": width, "height": height})
    return sizes


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.split("\n\n", 2)[1], file=sys.stderr)
        print("\nusage: python tools/cut_event_photos.py <folder> [<folder> ...]", file=sys.stderr)
        return 2

    folders = [Path(arg) for arg in argv]
    missing = [str(f) for f in folders if not f.is_dir()]
    if missing:
        print("not a folder: " + ", ".join(missing), file=sys.stderr)
        return 2

    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: pip install -r tools/requirements.txt", file=sys.stderr)
        return 1

    events, all_photos = _load_events()
    index = _index(folders)

    # Resolve everything before writing anything.
    plans = []
    problems: list[str] = []
    for event in events:
        photos = all_photos(event)
        sources, event_problems = _resolve(photos, index)
        problems.extend(f"{event['slug']}: {p}" for p in event_problems)
        plans.append((event, photos, sources))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"\n{len(problems)} problem(s); nothing written.", file=sys.stderr)
        return 1

    for event, photos, sources in plans:
        out_dir = OUT_ROOT / event["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)

        # Open everything for this event first, so an unreadable file stops
        # the run before any of the event's old files are replaced.
        images = {}
        for photo in photos:
            try:
                images[photo["src"]] = _open(sources[photo["src"]], photo.get("crop"))
            except (OSError, ValueError) as exc:
                problems.append(f"{event['slug']}: cannot read {photo['src']}: {exc}")
        if problems:
            print("\n".join(problems), file=sys.stderr)
            print("\nnothing written for this event.", file=sys.stderr)
            return 1

        manifest = {"photos": {}}
        written = set()
        total = 0
        for photo in photos:
            stem = Path(photo["src"]).stem.lower()
            sizes = _cut(images.pop(photo["src"]), stem, out_dir)
            manifest["photos"][photo["src"]] = {"sizes": sizes}
            for size in sizes:
                written.add(size["file"])
                total += (out_dir / size["file"]).stat().st_size

        # A photo dropped from the list leaves its old files behind otherwise,
        # and they would ship with every deploy for nothing.
        for old in out_dir.glob("*.webp"):
            if old.name not in written:
                old.unlink()

        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"{event['slug']}: {len(photos)} photos, {len(written)} files, {total / 1e6:.1f} MB")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
