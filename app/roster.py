# owner: shared / lead
#
# Loading the real teams from the registration spreadsheet. Teams register
# through a Jotform that fills a Google Sheet, not through the in-app form, so
# the sheet is the roster. Its CSV export comes in here two ways: uploaded on
# the head ref's "Import teams" page, or from the command line (seed/teams.py).
#
# The sheet holds students' and parents' names and emails, and this repo is
# public, so neither the file nor its link is ever committed.
#
# An import is all or nothing. Every row is checked first; if any row is
# wrong, nothing is written and every problem is reported at once, so the head
# ref fixes the sheet in one pass instead of one error per upload.
#
# Re-importing is safe and is how a late registration gets in: a team is
# matched to its row by team name, keeps its team number and check-in, and has
# its school, students and adult updated from the sheet.

import csv
import io
import re
from dataclasses import dataclass, field

from sqlalchemy.exc import IntegrityError

from app.db import db
from app.event import DIVISION, FIRST_TEAM_NUMBER
from app.models import Inspection, Match, Order, Team
from app.registration.routes import EMAIL_RE

# The sheet's headers, matched without regard to case or surrounding spaces.
# Its "Division" column is deliberately not read: the event has one division,
# High School, and every team goes in it whatever that column says.
COLUMNS = {
    "name": "Team Name",
    "affiliation": "School Name",
    "students": "Students",
    "adult_name": "Adult Name",
    "adult_email": "Adult Email",
}

# Optional. If the sheet has this column, a filled-in number is used as the
# team's number; otherwise new teams are numbered in sheet order.
NUMBER_COLUMN = "Team Number"

# The model's column sizes, so a long value is reported here rather than
# failing (Postgres) or being kept whole (SQLite) at save time.
MAX_LENGTHS = {"name": 120, "affiliation": 120, "adult_name": 120, "adult_email": 200}

# A roster is a few kilobytes. Anything near this is the wrong file.
MAX_BYTES = 1_000_000

# Students are typed into one box, separated by commas (the sheet does this
# today), semicolons or new lines.
_STUDENT_SPLIT = re.compile(r"[,;\n]+")


class RosterError(Exception):
    """The roster can't be imported as it is. `problems` lists every reason."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class RosterRow:
    line: int  # the spreadsheet's row number; the header is row 1
    name: str
    affiliation: str
    students: list[str]
    adult_name: str
    adult_email: str
    team_number: int | None


@dataclass
class ImportSummary:
    added: list[Team] = field(default_factory=list)
    updated: list[Team] = field(default_factory=list)
    unchanged: list[Team] = field(default_factory=list)
    # In the database but not in the file. Removed only when asked, and never
    # once the team has a match or an order.
    removed: list[str] = field(default_factory=list)
    not_in_file: list[Team] = field(default_factory=list)


def _key(name: str) -> str:
    """How two team names are compared: case and spacing don't matter."""
    return " ".join(name.split()).casefold()


def decode(raw: bytes) -> str:
    """The upload as text. utf-8-sig, because Excel and Sheets may add a BOM."""
    if len(raw) > MAX_BYTES:
        raise RosterError(["That file is far too big to be the team sheet."])
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RosterError(
            [
                "That file isn't CSV text. In the Google Sheet use File > Download > "
                "Comma-separated values (.csv), then choose that file."
            ]
        ) from None


def parse_roster(text: str) -> list[RosterRow]:
    """Every team in a roster CSV, checked. Raises RosterError on any problem."""
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise RosterError([f"That file isn't readable as CSV ({exc})."]) from None
    if not rows:
        raise RosterError(["The file is empty."])

    header = {cell.strip().casefold(): index for index, cell in enumerate(rows[0])}
    missing = [label for label in COLUMNS.values() if label.casefold() not in header]
    if missing:
        raise RosterError(
            [
                "This doesn't look like the team sheet: it has no "
                + ", ".join(f'"{label}"' for label in missing)
                + " column. The first row must be the sheet's headers."
            ]
        )
    number_index = header.get(NUMBER_COLUMN.casefold())

    def cell(row: list[str], label: str) -> str:
        index = header[label.casefold()]
        return row[index].strip() if index < len(row) else ""

    problems: list[str] = []
    parsed: list[RosterRow] = []
    for line, row in enumerate(rows[1:], start=2):
        if not any(value.strip() for value in row):
            continue  # a blank row at the bottom of a sheet

        values = {attr: cell(row, label) for attr, label in COLUMNS.items()}
        where = f"Row {line} ({values['name'] or 'no team name'})"
        row_problems = []

        for attr, label in COLUMNS.items():
            if not values[attr]:
                row_problems.append(f"{where}: {label} is empty.")
            elif attr in MAX_LENGTHS and len(values[attr]) > MAX_LENGTHS[attr]:
                row_problems.append(
                    f"{where}: {label} is longer than {MAX_LENGTHS[attr]} characters."
                )
        if values["adult_email"] and not EMAIL_RE.match(values["adult_email"]):
            row_problems.append(f"{where}: {values['adult_email']!r} is not an email address.")

        students = [s.strip() for s in _STUDENT_SPLIT.split(values["students"]) if s.strip()]

        team_number = None
        raw_number = (
            row[number_index].strip()
            if number_index is not None and number_index < len(row)
            else ""
        )
        if raw_number:
            if raw_number.isdigit() and 1 <= int(raw_number) <= 99999:
                team_number = int(raw_number)
            else:
                row_problems.append(f"{where}: team number {raw_number!r} is not a whole number.")

        problems.extend(row_problems)
        if not row_problems:
            parsed.append(
                RosterRow(
                    line=line,
                    name=" ".join(values["name"].split()),
                    affiliation=values["affiliation"],
                    students=students,
                    adult_name=values["adult_name"],
                    # Lowercased, as the registration form stores it, so its
                    # "one adult, one team" check sees imported teams too.
                    adult_email=values["adult_email"].lower(),
                    team_number=team_number,
                )
            )

    _check_unique(parsed, lambda r: _key(r.name), "team name", problems)
    _check_unique(parsed, lambda r: r.adult_email.casefold(), "adult email", problems)
    _check_unique(parsed, lambda r: r.team_number, "team number", problems)

    if problems:
        raise RosterError(problems)
    if not parsed:
        raise RosterError(["The file has headers but no teams."])
    return parsed


def _check_unique(rows, key, what, problems):
    seen: dict[object, RosterRow] = {}
    for row in rows:
        value = key(row)
        if value is None:
            continue
        if value in seen:
            extra = (
                " Each team needs its own, because the app uses it to tell teams apart."
                if what == "adult email"
                else ""
            )
            problems.append(f"Rows {seen[value].line} and {row.line} have the same {what}.{extra}")
        else:
            seen[value] = row


def _removable(team: Team) -> bool:
    """A team can be deleted only while nothing else points at it."""
    in_a_match = Match.query.filter(
        db.or_(Match.red_team_id == team.id, Match.blue_team_id == team.id)
    ).first()
    has_order = Order.query.filter_by(team_id=team.id).first()
    return in_a_match is None and has_order is None


def import_roster(rows: list[RosterRow], remove_missing: bool = False) -> ImportSummary:
    """Add and update teams to match `rows`, and commit. All or nothing.

    With remove_missing, teams that are not in `rows` are deleted (with their
    inspections), except any team already in a match or tied to an order:
    those are kept and listed in not_in_file instead.
    """
    existing = Team.query.order_by(Team.team_number).all()
    by_key = {_key(team.name): team for team in existing}
    matched = {id(by_key[_key(r.name)]) for r in rows if _key(r.name) in by_key}

    summary = ImportSummary()
    to_remove = []
    for team in existing:
        if id(team) in matched:
            continue
        if remove_missing and _removable(team):
            to_remove.append(team)
        else:
            summary.not_in_file.append(team)
    staying = [t for t in existing if t not in to_remove]

    # Emails and numbers are unique in the database, so a row may not take
    # one that belongs to a different team that is staying.
    problems = []
    for row in rows:
        own = by_key.get(_key(row.name))
        for team in staying:
            if team is own:
                continue
            if team.adult_email.casefold() == row.adult_email.casefold():
                problems.append(
                    f"Row {row.line} ({row.name}): {row.adult_email} is already the adult "
                    f"email of team {team.team_number} {team.name}."
                )
            if row.team_number is not None and team.team_number == row.team_number:
                problems.append(
                    f"Row {row.line} ({row.name}): team number {row.team_number} already "
                    f"belongs to {team.name}."
                )
        if own is not None and row.team_number is not None and own.team_number != row.team_number:
            problems.append(
                f"Row {row.line} ({row.name}): this team is already number {own.team_number}. "
                "Team numbers aren't changed by an import, because robots are "
                "programmed with them."
            )
    if problems:
        raise RosterError(problems)

    for team in to_remove:
        summary.removed.append(f"{team.team_number} {team.name}")
        Inspection.query.filter_by(team_id=team.id).delete()
        db.session.delete(team)
    # Deletes first, so a removed team's email or number is free for a new row.
    db.session.flush()

    taken = {t.team_number for t in staying} | {r.team_number for r in rows if r.team_number}
    next_number = max(taken | {FIRST_TEAM_NUMBER - 1}) + 1

    for row in rows:
        students = "\n".join(row.students)
        team = by_key.get(_key(row.name))
        if team is None:
            number = row.team_number
            if number is None:
                number = next_number
                next_number += 1
            team = Team(
                team_number=number,
                name=row.name,
                affiliation=row.affiliation,
                division=DIVISION,
                students=students,
                adult_name=row.adult_name,
                adult_email=row.adult_email,
            )
            db.session.add(team)
            summary.added.append(team)
            continue

        changed = False
        for attr, value in (
            ("name", row.name),
            ("affiliation", row.affiliation),
            ("students", students),
            ("adult_name", row.adult_name),
            ("adult_email", row.adult_email),
        ):
            if getattr(team, attr) != value:
                setattr(team, attr, value)
                changed = True
        (summary.updated if changed else summary.unchanged).append(team)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise RosterError(
            [
                "Saving failed because a team number or email clashed with another team, "
                "probably one added at the same moment. Nothing was imported. Try again."
            ]
        ) from None
    return summary
