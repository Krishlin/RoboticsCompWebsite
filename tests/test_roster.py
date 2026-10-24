"""Importing the real roster from the registration sheet's CSV export.

tests/fixtures/roster.csv has the sheet's exact columns and quirks (quoted
student lists, a "/" in a school name) with made-up people. The real sheet is
never committed: the repo is public and it holds names and emails.
"""

import io
from pathlib import Path

import pytest

from app.db import db
from app.models import Inspection, Match, Team
from app.roster import RosterError, decode, import_roster, parse_roster
from seed.teams import csv_url, main, read_source
from tests.conftest import _build, head_ref_auth, staff_auth

ROSTER = Path(__file__).parent / "fixtures" / "roster.csv"
HEAD = head_ref_auth()
HEADER = "Team Name,School Name,Division,Students,Adult Name,Adult Email\n"


# The head ref's pages are only registered with REGISTRATION_ONLY off.
@pytest.fixture
def app(tmp_path):
    return _build(tmp_path, REGISTRATION_ONLY=False)


def roster_text():
    return ROSTER.read_text(encoding="utf-8")


def test_the_sheet_parses_into_teams():
    rows = parse_roster(roster_text())
    assert len(rows) == 11
    assert rows[0].name == "Gear Grinders"
    assert rows[0].line == 2
    assert rows[2].students == ["Cal Demo", "Dee Demo"]
    assert rows[7].affiliation == "Southgate High School / Eastview High School"
    assert len(rows[7].students) == 4
    assert all(r.team_number is None for r in rows)


def test_headers_are_matched_loosely_and_blank_rows_skipped():
    # Students split on commas, semicolons and new lines alike.
    text = (
        " team name ,SCHOOL NAME,Students,Adult Name,adult email\n"
        '"A Team",A School,"Ann; Bob\nCid",Coach A,a@example.org\n'
        ",,,,\n"
    )
    rows = parse_roster(text)
    assert len(rows) == 1
    assert rows[0].students == ["Ann", "Bob", "Cid"]


def test_a_byte_order_mark_is_not_part_of_the_first_header():
    rows = parse_roster(decode(("﻿" + roster_text()).encode("utf-8")))
    assert len(rows) == 11


def test_every_problem_is_reported_at_once():
    text = HEADER + (
        "Good Team,School,High School,Ann,Coach,good@example.org\n"
        ",School,High School,Ann,Coach,noname@example.org\n"
        "No Email,School,High School,Ann,Coach,not-an-email\n"
        "good team,School,High School,Ann,Coach,other@example.org\n"
        "Same Email,School,High School,Ann,Coach,GOOD@example.org\n"
    )
    with pytest.raises(RosterError) as caught:
        parse_roster(text)
    problems = " | ".join(caught.value.problems)
    assert "Row 3 (no team name): Team Name is empty." in problems
    assert "'not-an-email' is not an email address" in problems
    assert "Rows 2 and 5 have the same team name." in problems
    assert "Rows 2 and 6 have the same adult email." in problems


def test_the_wrong_file_is_refused_with_a_reason():
    with pytest.raises(RosterError, match="doesn't look like the team sheet"):
        parse_roster("<!DOCTYPE html><html><body>Sign in</body></html>")
    with pytest.raises(RosterError, match="empty"):
        parse_roster("")
    with pytest.raises(RosterError, match="no teams"):
        parse_roster(HEADER)
    with pytest.raises(RosterError, match="isn't CSV text"):
        decode(b"\xff\xfe\x00\x00binary")


def test_import_numbers_teams_in_sheet_order_from_100(app):
    with app.app_context():
        summary = import_roster(parse_roster(roster_text()))
        assert len(summary.added) == 11
        teams = Team.query.order_by(Team.team_number).all()
        assert [t.team_number for t in teams] == list(range(100, 111))
        assert teams[0].name == "Gear Grinders"
        assert teams[2].students == "Cal Demo\nDee Demo"
        assert all(t.adult_email == t.adult_email.lower() for t in teams)
        assert {t.division for t in teams} == {"High School"}
        assert not any(t.checked_in for t in teams)


def test_reimporting_keeps_numbers_and_check_in_and_adds_late_teams(app):
    with app.app_context():
        import_roster(parse_roster(roster_text()))
        ramp = Team.query.filter_by(name="Ramp Rats").one()
        ramp.checked_in = True
        db.session.commit()

        edited = roster_text().replace("Cal Demo, Dee Demo", "Cal Demo, Dee Demo, Eli Demo")
        edited += "Late Comers,Late School,High School,Zed Late,Yan Late,yan.late@example.org\n"
        summary = import_roster(parse_roster(edited))

        assert [t.name for t in summary.added] == ["Late Comers"]
        assert summary.added[0].team_number == 111
        assert [t.name for t in summary.updated] == ["Ramp Rats"]
        assert len(summary.unchanged) == 10

        ramp = Team.query.filter_by(name="Ramp Rats").one()
        assert ramp.team_number == 102
        assert ramp.checked_in
        assert ramp.students.splitlines() == ["Cal Demo", "Dee Demo", "Eli Demo"]

        # And a third run with the same file changes nothing.
        again = import_roster(parse_roster(edited))
        assert not again.added and not again.updated and len(again.unchanged) == 12


def test_a_team_number_column_is_used_when_present(app):
    text = (
        "Team Number,Team Name,School Name,Students,Adult Name,Adult Email\n"
        "7,Seven,School,Ann,Coach,seven@example.org\n"
        ",Next,School,Bob,Coach,next@example.org\n"
    )
    with app.app_context():
        import_roster(parse_roster(text))
        numbers = {t.name: t.team_number for t in Team.query}
        # The numbered team keeps 7; the unnumbered one goes after everything taken.
        assert numbers == {"Seven": 7, "Next": 100}


def test_an_import_never_renumbers_a_team(app):
    with app.app_context():
        import_roster(parse_roster(roster_text()))
        text = (
            "Team Number,Team Name,School Name,Students,Adult Name,Adult Email\n"
            "555,Gear Grinders,Northfield Middle School,Ada Example,Pat Example,pat.example@example.org\n"
        )
        with pytest.raises(RosterError, match="already number 100"):
            import_roster(parse_roster(text))
        assert Team.query.filter_by(name="Gear Grinders").one().team_number == 100


def test_an_email_belonging_to_another_team_is_refused_and_nothing_is_written(app):
    with app.app_context():
        import_roster(parse_roster(roster_text()))
        text = HEADER + (
            "Brand New,School,High School,Ann,Coach,brand.new@example.org\n"
            "Another,School,High School,Bob,Coach,PAT.EXAMPLE@example.org\n"
        )
        with pytest.raises(RosterError, match="already the adult email of team 100"):
            import_roster(parse_roster(text))
        assert Team.query.count() == 11
        assert Team.query.filter_by(name="Brand New").first() is None


def test_remove_missing_clears_test_teams_but_never_one_in_a_match(app):
    with app.app_context():
        for number, name in ((1, "Test Team A"), (2, "Test Team B"), (3, "Test Team C")):
            db.session.add(
                Team(
                    team_number=number,
                    name=name,
                    affiliation="X",
                    division="High School",
                    students="S",
                    adult_name="A",
                    adult_email=f"t{number}@example.org",
                )
            )
        db.session.commit()
        a, b = (Team.query.filter_by(team_number=n).one() for n in (1, 2))
        db.session.add(
            Inspection(
                team_id=a.id,
                passed=True,
                size_ok=True,
                weight_ok=True,
                microbit_present=True,
                team_number_displayed=True,
                ref_start_stop_test=True,
            )
        )
        db.session.add(
            Match(
                match_number=1,
                phase="qualification",
                division="High School",
                arena="Arena 1",
                red_team_id=b.id,
                blue_team_id=b.id,
            )
        )
        db.session.commit()

        summary = import_roster(parse_roster(roster_text()), remove_missing=True)

        assert sorted(summary.removed) == ["1 Test Team A", "3 Test Team C"]
        assert [t.name for t in summary.not_in_file] == ["Test Team B"]
        assert Inspection.query.count() == 0
        assert Team.query.count() == 12
        # Numbering carries on after the team that stayed, not from 1.
        assert min(t.team_number for t in summary.added) == 100


def test_without_remove_missing_nothing_is_deleted(app):
    with app.app_context():
        db.session.add(
            Team(
                team_number=5,
                name="Old",
                affiliation="X",
                division="High School",
                students="S",
                adult_name="A",
                adult_email="old@example.org",
            )
        )
        db.session.commit()
        summary = import_roster(parse_roster(roster_text()))
        assert [t.name for t in summary.not_in_file] == ["Old"]
        assert Team.query.count() == 12


def test_the_head_ref_imports_from_the_browser(app, client):
    page = client.get("/admin/import-teams")
    assert page.status_code == 401
    assert client.get("/admin/import-teams", headers=staff_auth()).status_code == 401

    response = client.post(
        "/admin/import-teams",
        headers=HEAD,
        data={"roster": (io.BytesIO(ROSTER.read_bytes()), "Registration.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "11 added" in body
    assert "Gear Grinders" in body
    with app.app_context():
        assert Team.query.count() == 11


def test_a_bad_upload_says_why_and_imports_nothing(app, client):
    bad = HEADER + "Team,School,High School,Ann,Coach,nope\n"
    response = client.post(
        "/admin/import-teams",
        headers=HEAD,
        data={"roster": (io.BytesIO(bad.encode()), "Registration.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "Nothing was imported" in response.get_data(as_text=True)
    assert "is not an email address" in response.get_data(as_text=True)

    empty = client.post(
        "/admin/import-teams", headers=HEAD, data={}, content_type="multipart/form-data"
    )
    assert empty.status_code == 400
    assert "Choose the sheet" in empty.get_data(as_text=True)
    with app.app_context():
        assert Team.query.count() == 0


def test_the_command_line_reads_a_file_and_turns_sheet_links_into_csv_links():
    assert len(parse_roster(read_source(str(ROSTER)))) == 11
    with pytest.raises(RosterError, match="Could not read"):
        read_source("no/such/file.csv")

    sheet = "https://docs.google.com/spreadsheets/d/AbC-123_x/edit?usp=sharing"
    assert csv_url(sheet) == "https://docs.google.com/spreadsheets/d/AbC-123_x/export?format=csv"
    assert csv_url(sheet + "#gid=42").endswith("export?format=csv&gid=42")
    already = "https://docs.google.com/spreadsheets/d/AbC/export?format=csv"
    assert csv_url(already) == already
    assert csv_url("https://example.org/roster.csv") == "https://example.org/roster.csv"


def test_the_command_line_imports_into_the_configured_database(tmp_path, monkeypatch, capsys):
    dbfile = tmp_path / "cli.db"
    import seed.teams as cli

    monkeypatch.setattr(
        cli,
        "create_app",
        lambda: _build(tmp_path, SQLALCHEMY_DATABASE_URI=f"sqlite:///{dbfile.as_posix()}"),
    )
    assert main([str(ROSTER)]) == 0
    out = capsys.readouterr().out
    assert "11 added" in out
    assert main([str(ROSTER)]) == 0
    assert "0 added, 0 updated, 11 unchanged" in capsys.readouterr().out

    assert main(["no/such/file.csv"]) == 1
    assert "Nothing was imported" in capsys.readouterr().err
