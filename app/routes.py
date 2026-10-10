# owner: shared / lead
# Home page. Lists every page in the app and who owns it, so anyone can
# find their way around while the real pages are still being built.

from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)

# Hand-maintained list of every route in the app. When you add a page to
# your blueprint, add one line here too, so it shows up on the home page.
ROUTE_INDEX = [
    {"owner": "Emily", "label": "Sign up a team", "path": "/register/"},
    {"owner": "Emily", "label": "Registration confirmation", "path": "/register/confirmation"},
    {"owner": "Emily", "label": "Team list / CSV export", "path": "/register/teams"},

    {"owner": "Shivani", "label": "Check-in list", "path": "/checkin/"},
    {"owner": "Shivani", "label": "Inspection form (team 101)", "path": "/checkin/inspect/101"},
    {"owner": "Shivani", "label": "Inspection history (team 102)", "path": "/checkin/history/102"},

    {"owner": "Shaurya", "label": "Full qualification schedule", "path": "/schedule/"},
    {"owner": "Shaurya", "label": "Schedule generator admin", "path": "/schedule/admin"},
    {"owner": "Shaurya", "label": "Schedule by arena", "path": "/schedule/arena/Arena_1"},
    {"owner": "Shaurya", "label": "Schedule by team (team 101)", "path": "/schedule/team/101"},

    {"owner": "Serena", "label": "Referee: current match", "path": "/referee/"},
    {"owner": "Serena", "label": "Referee: enter result", "path": "/referee/result/1"},
    {"owner": "Serena", "label": "Referee: confirm submission", "path": "/referee/confirm/1"},

    {"owner": "Jon", "label": "Rankings (Middle School)", "path": "/rankings/Middle_School"},
    {"owner": "Jon", "label": "Big-screen display (Middle School)", "path": "/rankings/display/Middle_School"},
    {"owner": "Jon", "label": "Pit lookup", "path": "/rankings/pit"},

    {"owner": "Krish S", "label": "Elimination bracket (Middle School)", "path": "/bracket/Middle_School"},

    {"owner": "Yueyue", "label": "Admin dashboard", "path": "/admin/"},
    {"owner": "Yueyue", "label": "Edit a result", "path": "/admin/edit/1"},
    {"owner": "Yueyue", "label": "Audit log", "path": "/admin/audit-log"},
]


@main_bp.route("/")
def home():
    return render_template("home.html", routes=ROUTE_INDEX)
