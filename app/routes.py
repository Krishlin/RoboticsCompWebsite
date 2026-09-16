# owner: shared / lead
# The public landing page, plus the developer route index that used to live
# at "/". The index moved to /routes so the front door can be the real site.

import json
import os

from flask import Blueprint, current_app, render_template, send_from_directory

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


# Spelled-out counts, because the number sits mid-sentence on the page.
_NUMBER_WORDS = [
    "zero", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "eleven", "twelve",
]


def _manual_pages():
    """Page thumbnails for the manual contact sheet, or None if unavailable.

    Written by tools/render_manual_thumbs.py. Read fresh each request so
    regenerating the images after a new manual shows up without a restart;
    the file is about a kilobyte, so the read costs nothing worth caching.

    Returns None on a missing, unreadable, or malformed manifest. The
    template renders a plain link to the PDF in that case, so a landing page
    is never blocked on a tooling step nobody ran.
    """
    path = os.path.join(
        current_app.static_folder, "img", "manual", "manifest.json"
    )
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError):
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


@main_bp.route("/")
def home():
    return render_template(
        "landing.html", links=SITE_LINKS, manual=_manual_pages()
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


@main_bp.route("/routes")
def route_index():
    # The build-status index. Lists every page in the app and who owns it,
    # including the ones that 404 while REGISTRATION_ONLY is on.
    return render_template("home.html", routes=ROUTE_INDEX)
