"""Re-encode the teaser for the web, and cut its poster frame.

The teaser arrives from SRC the way a phone or an editor exports it: HEVC in a
QuickTime container, 66 MB for 35 seconds. Neither half of that is servable.
HEVC does not play in Chrome on Windows or Android, or in Firefox anywhere, so
most of the families this page is written for would get an empty player. And
66 MB is about 15 Mbps for a 1180x642 picture — ten times what it needs, on a
page whose whole argument is that it works on a cheap laptop and a gym's cell
signal.

So the source stays a source, the way the CAD renders do: .vercelignore keeps
it out of the deploy and only the file written here ships.

Run this when the teaser is replaced:

    pip install -r tools/requirements.txt
    python tools/encode_teaser.py

H.264 High in yuv420p is the one combination that plays everywhere, including
the old Android tablets a school lends out. -movflags +faststart moves the
index to the front of the file so the video starts on the first chunk instead
of after the whole download.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "SUMMIT_robotics_teaser.mov"
OUT_VIDEO = ROOT / "app" / "static" / "video" / "summit-teaser.mp4"
OUT_POSTER = ROOT / "app" / "static" / "img" / "summit_teaser_poster.webp"

# Constant-quality rather than a target bitrate: the teaser is one clip and
# nobody is going to re-grade it against a size budget. 23 is visually clean
# at this resolution and lands the file in single-digit megabytes.
CRF = "23"
PRESET = "slow"

# The frame the poster is cut from, and the one thing here worth re-checking
# when the teaser is recut: it is what a visitor stares at until they press
# play. 11.2s is past the title cards and the fade, both robots locked
# together on the Plateau, no hands in shot.
POSTER_AT = "00:00:11.2"

# The poster is shown at the same width as the widest art on the page, so it
# is cut to match rather than shipped at the video's native size.
POSTER_WIDTH = 1100


def _ffmpeg() -> str:
    """Path to the bundled ffmpeg binary.

    imageio-ffmpeg carries a static build, so this needs no system install and
    no PATH entry. Raises ImportError if the tooling dependency is absent;
    main() reports that with a fix.
    """
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str]) -> None:
    """Run ffmpeg, raising with the tail of its log if it fails.

    ffmpeg writes progress to stderr and only the last lines say what went
    wrong, so the whole log is captured and trimmed rather than streamed.
    """
    done = subprocess.run(args, capture_output=True, text=True)
    if done.returncode != 0:
        tail = "\n".join(done.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"ffmpeg exited {done.returncode}:\n{tail}")


def encode(source: Path, out_video: Path, out_poster: Path) -> None:
    """Write the web copy of *source* and its poster frame.

    Raises FileNotFoundError if the source is missing and RuntimeError if
    ffmpeg fails; main() reports both.
    """
    if not source.is_file():
        raise FileNotFoundError(source)

    ffmpeg = _ffmpeg()
    out_video.parent.mkdir(parents=True, exist_ok=True)
    out_poster.parent.mkdir(parents=True, exist_ok=True)

    _run([
        ffmpeg, "-y", "-i", str(source),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-crf", CRF, "-preset", PRESET,
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart",
        str(out_video),
    ])

    _run([
        ffmpeg, "-y", "-ss", POSTER_AT, "-i", str(source),
        "-frames:v", "1", "-vf", f"scale={POSTER_WIDTH}:-2",
        "-quality", "84",
        str(out_poster),
    ])


def main() -> int:
    try:
        encode(SOURCE, OUT_VIDEO, OUT_POSTER)
    except FileNotFoundError as missing:
        print(f"Source not found: {missing}", file=sys.stderr)
        return 1
    except ImportError:
        print(
            "imageio-ffmpeg is not installed.\n"
            "    pip install -r tools/requirements.txt",
            file=sys.stderr,
        )
        return 1
    except RuntimeError as failure:
        print(str(failure), file=sys.stderr)
        return 1

    before = SOURCE.stat().st_size / 1024
    after = OUT_VIDEO.stat().st_size / 1024
    print(
        f"{SOURCE.name}: {before / 1024:.0f} MB -> {after / 1024:.1f} MB"
        f"  ({OUT_VIDEO.relative_to(ROOT)})"
    )
    print(f"poster: {OUT_POSTER.stat().st_size / 1024:.0f} KB"
          f"  ({OUT_POSTER.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
