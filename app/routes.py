# owner: shared / lead
# The public landing page, plus the developer route index that used to live
# at "/". The index moved to /routes so the front door can be the real site.

import json
import logging
import os

from flask import Blueprint, current_app, jsonify, render_template, send_from_directory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.db import db
from app.security import staff_required

logger = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)

# Link targets SRC has not given us yet. The landing template renders plain
# text in place of any entry left as None, so an unfilled value never ships
# as a link that goes nowhere. Fill one in and it becomes a link.
SITE_LINKS = {
    "email": None,
    "instagram": None,
    "consent_form": None,
    "starter_code": None,
    "build_guide": None,
    "print_files": None,
    "filament_list": None,
}

# The manual is served from a fixed path so the address in the printed
# manual, the emails, and the site never has to change. Dropping a new
# PDF in app/static/docs and updating this name is the whole release.
MANUAL_FILENAME = "summit-manual-v1.0.pdf"

# Hand-maintained list of every route in the app. When you add a page to
# your blueprint, add one line here too, so it shows up on the home page.
ROUTE_INDEX = [
    {"owner": "Emily", "label": "Sign up a team", "path": "/register/"},
    {"owner": "Emily", "label": "Registration confirmation (team 101)", "path": "/register/confirmation/101"},
    {"owner": "Emily", "label": "Team list / CSV export", "path": "/register/teams"},

    {"owner": "Shivani", "label": "Check-in list", "path": "/checkin/"},
    {"owner": "Shivani", "label": "Inspection form (team 101)", "path": "/checkin/inspect/101"},
    {"owner": "Shivani", "label": "Inspection history (team 102)", "path": "/checkin/history/102"},

    {"owner": "Shaurya", "label": "Full qualification schedule", "path": "/schedule/"},
    {"owner": "Shaurya", "label": "Schedule by arena", "path": "/schedule/arena/Arena_1"},
    {"owner": "Shaurya", "label": "Schedule by team (team 101)", "path": "/schedule/team/101"},

    {"owner": "Serena", "label": "Referee: current match", "path": "/referee/"},
    {"owner": "Serena", "label": "Referee: enter result", "path": "/referee/result/1"},
    {"owner": "Serena", "label": "Referee: confirm submission (reached from the result form)", "path": "/referee/confirm/1"},

    {"owner": "Jon", "label": "Rankings (High School)", "path": "/rankings/High_School"},
    {"owner": "Jon", "label": "Big-screen display (High School)", "path": "/rankings/display/High_School"},
    {"owner": "Jon", "label": "Pit lookup", "path": "/rankings/pit"},

    {"owner": "Krish S", "label": "Elimination bracket (High School)", "path": "/bracket/High_School"},

    {"owner": "Yueyue", "label": "Admin dashboard", "path": "/admin/"},
    {"owner": "Yueyue", "label": "Edit a result", "path": "/admin/edit/1"},
    {"owner": "Yueyue", "label": "Audit log", "path": "/admin/audit-log"},
]


# The kit robot, one view per entry, in the order the gallery shows them.
# Slugs are written by tools/render_bot_views.py; the words are ours, so they
# live here with the rest of the page's copy rather than in the build tool.
# A slug with no rendered images is skipped, so the gallery shrinks rather
# than breaking if a view is dropped from the renders.
#
# Nothing prints the label: the picture is its own caption, and the paragraph
# under it was only ever saying what the reader could already see. It names
# the view for the image's alt text and for the thumbnail rail, both of which
# assistive tech reads and neither of which is on screen.
# One view, so the label is only ever read by assistive tech on the image
# itself; the thumbnail rail it also names does not render below two views.
# The rest of the set is listed in tools/render_bot_views.py.
BOT_VIEWS = [
    {"slug": "three-quarter-rear", "label": "Three-quarter"},
]


# Spelled-out counts, because the number sits mid-sentence on the page.
_NUMBER_WORDS = [
    "zero", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "eleven", "twelve",
]


def _read_manifest(*parts):
    """A JSON object written by tools/, or None if it is not usable.

    None covers all three ways a build artefact can be absent rather than
    wrong: the file is missing, it is unreadable, or it does not parse. It
    also covers a file that parses into something that is not an object,
    because every caller goes on to look up keys and a stray list would
    otherwise take the whole landing page down with an AttributeError — a
    500 on the front door over a build step nobody ran.
    """
    path = os.path.join(current_app.static_folder, "img", *parts)
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def _manual_pages():
    """Page thumbnails for the manual contact sheet, or None if unavailable.

    Written by tools/render_manual_thumbs.py. Read fresh each request so
    regenerating the images after a new manual shows up without a restart;
    the file is about a kilobyte, so the read costs nothing worth caching.

    Returns None on a missing, unreadable, or malformed manifest. The
    template renders a plain link to the PDF in that case, so a landing page
    is never blocked on a tooling step nobody ran.
    """
    manifest = _read_manifest("manual", "manifest.json")
    if manifest is None:
        return None

    pages = manifest.get("pages")
    if not pages:
        return None

    count = len(pages)
    return {
        "pages": pages,
        "count": count,
        "count_word": _NUMBER_WORDS[count] if count < len(_NUMBER_WORDS) else count,
    }


def _bot_gallery():
    """The kit-robot views, ready to render, or None if unavailable.

    Joins the words in BOT_VIEWS to the files written by
    tools/render_bot_views.py. Read fresh each request for the same reason the
    manual manifest is: re-cutting the renders should show up without a
    restart, and the file is a couple of kilobytes.

    Returns None on a missing, unreadable, or malformed manifest, and drops
    any single view whose images are absent. The template falls back to the
    still photograph of the kit in that case, so the section always has
    something to show.
    """
    manifest = _read_manifest("bot", "manifest.json")
    if manifest is None:
        return None

    try:
        by_slug = {view["slug"]: view["sizes"] for view in manifest["views"]}
        aspect = manifest["aspect"]
        widths = sorted(int(w) for w in manifest["widths"])
    except (KeyError, TypeError, ValueError):
        return None

    views = []
    for view in BOT_VIEWS:
        sizes = by_slug.get(view["slug"])
        if not sizes:
            continue
        # Widest last so the browser's own choice, not source order, decides.
        ordered = [sizes[str(w)] for w in widths if str(w) in sizes]
        if not ordered:
            continue
        views.append({**view, "sizes": ordered, "largest": ordered[-1]})

    if not views:
        return None
    return {"views": views, "aspect": aspect}


def _art():
    """WebP sizes for the page's flat artwork, keyed by source filename.

    Written by tools/convert_site_art.py. Returns an empty dict on a missing,
    unreadable, or malformed manifest, and the template then serves the
    original PNG — heavier, but never a broken image because a build step was
    skipped.
    """
    manifest = _read_manifest("art-manifest.json")
    if manifest is None:
        return {}

    art = {}
    for name, entry in manifest.items():
        sizes = entry.get("sizes") if isinstance(entry, dict) else None
        if sizes:
            art[name] = sizes
    return art


@main_bp.route("/")
def home():
    return render_template(
        "landing.html",
        links=SITE_LINKS,
        manual=_manual_pages(),
        bot=_bot_gallery(),
        art=_art(),
    )


@main_bp.route("/summit/manual")
def manual():
    """Permanent address for the current game manual.

    send_from_directory 404s on a missing file rather than raising, so a
    release that forgets to copy the PDF shows a normal 404 instead of a
    stack trace on a page competitors are told to visit.
    """
    return send_from_directory(
        current_app.static_folder + "/docs",
        MANUAL_FILENAME,
        mimetype="application/pdf",
    )


@main_bp.route("/healthz")
def healthz():
    """Is this deployment actually wired up?

    Answers the three questions that a deploy gets wrong silently: can we reach
    the database, is a Stripe key present, is a Resend key present. Booleans
    only for the keys, and the database host without its credentials — this is
    an unauthenticated route and must never become a way to read secrets.

    503 rather than 500 when the database is down, so an uptime check can tell
    "configured but unreachable" apart from "the app is broken".
    """
    try:
        url = make_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
        # SQLite has no host, only a path — and the full path is somebody's home
        # directory, so report just the filename.
        db_host = url.host or os.path.basename(url.database or "") or "unknown"
    except (ArgumentError, ValueError):
        # A URI SQLAlchemy cannot parse is a configuration error, but it must
        # not take the health check itself down — that is the one route that
        # has to answer when everything else is wrong.
        db_host = "unparseable"

    body = {
        "database_host": db_host,
        "stripe_key_present": bool(current_app.config.get("STRIPE_SECRET_KEY")),
        "resend_key_present": bool(current_app.config.get("RESEND_API_KEY")),
        "mail_sender_is_shared": bool(current_app.config.get("MAIL_SENDER_IS_SHARED")),
    }

    try:
        db.session.execute(text("SELECT 1"))
    except Exception as exc:
        # Deliberately broad: anything at all that stops a trivial query is a
        # failed health check, and the caller wants the class of failure rather
        # than a traceback. The full exception goes to the log, not the body.
        logger.exception("healthz: database unreachable")
        body["database"] = "unreachable"
        body["error"] = type(exc).__name__
        return jsonify(body), 503

    body["database"] = "ok"
    return jsonify(body), 200


@main_bp.route("/routes")
@staff_required
def route_index():
    # The build-status index. Lists every page in the app and who owns it,
    # including the ones that 404 while REGISTRATION_ONLY is on.
    #
    # Staff only. Published, this is a directory of every endpoint in the app
    # - including the unfinished ones - annotated with the first name of the
    # student who owns each. Neither half belongs on the public internet.
    return render_template("home.html", routes=ROUTE_INDEX)
