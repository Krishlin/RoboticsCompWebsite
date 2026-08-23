# owner: Krish S
# Renders the elimination bracket. Seeds from final qualification rankings,
# advances winners as results arrive. A tie inserts a replay match instead
# of advancing anyone.

from flask import render_template

from app.fake_data import BRACKET_ROUNDS
from app.bracket import bracket_bp


@bracket_bp.route("/<division>")
def view_bracket(division):
    division_name = division.replace("_", " ")
    # TODO(Krish S): real bracket depends on division + single vs double
    # elimination (configurable per division). Fake data below is single
    # elimination only, for one division.
    return render_template(
        "bracket/bracket.html",
        division=division_name,
        rounds=BRACKET_ROUNDS,
    )
