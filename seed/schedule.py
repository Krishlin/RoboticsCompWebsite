# owner: shared / lead
#
# Pre-make the qualification schedule from the registration sheet, so it is
# already on the site when teams arrive:
#
#   python -m seed.schedule <sheet link or .csv> --leave-out "Team Name"
#
# It imports the sheet first (adding or updating teams, never deleting; see
# app/roster.py), then schedules every team in the sheet except the ones left
# out: 6 best-of-three series each (game manual T3), never two in a row, on
# the arenas and times given. A left-out team stays registered but is not
# scheduled, so it is not ranked or seeded either.
#
# Like the head ref's Generate button, it replaces a schedule nobody has
# played yet and refuses once any qualification series has started. It writes
# to whatever DATABASE_URL points at (your local SQLite file when unset).
#
# The schedule is the same every time for the same teams and settings, so a
# run against a scratch database previews exactly what the real run writes.

import argparse
import random
import sys
from datetime import datetime

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.formatting import clock
from app.models import Team
from app.roster import RosterError, import_roster, parse_roster
from app.scheduler.generator import (
    DEFAULT_SERIES_PER_TEAM,
    DEFAULT_SLOT_MINUTES,
    generate_advanced_schedule,
    validate_schedule,
)
from app.scheduler.service import played_qualification_count, save_schedule
from seed.teams import print_summary, read_source

DEFAULT_ARENAS = 2

# Fixed, so the same teams and settings always give the same schedule.
SCHEDULE_SEED = 2026


class ScheduleError(Exception):
    pass


def _key(name: str) -> str:
    return " ".join(name.split()).casefold()


def premake_schedule(
    source: str,
    leave_out: list[str],
    arenas: int = DEFAULT_ARENAS,
    start: datetime | None = None,
    round_minutes: int = DEFAULT_SLOT_MINUTES,
    series_per_team: int = DEFAULT_SERIES_PER_TEAM,
    round_robin: bool = False,
):
    """Import the sheet and save a schedule. Needs an app context.

    Returns (import summary, scheduled teams, schedule). Raises RosterError
    for a bad sheet and ScheduleError when the schedule can't be made; in
    both cases nothing about the schedule has changed.
    """
    rows = parse_roster(read_source(source))
    wanted = {_key(name) for name in leave_out}
    unknown = wanted - {_key(row.name) for row in rows}
    if unknown:
        raise ScheduleError(
            "No team in the sheet is called "
            + ", ".join(repr(n) for n in leave_out if _key(n) in unknown)
            + ". Check the spelling against the sheet."
        )
    # Checked before the import writes anything.
    played = played_qualification_count()
    if played:
        raise ScheduleError(
            f"{played} qualification series have already been played or started, so "
            "the schedule can't be replaced."
        )

    summary = import_roster(rows)
    in_sheet = {_key(row.name) for row in rows} - wanted
    teams = [t for t in Team.query.order_by(Team.team_number) if _key(t.name) in in_sheet]
    if len(teams) < 2:
        raise ScheduleError("Need at least two teams to schedule.")

    if round_robin:
        # Everyone plays everyone once.
        series_per_team = len(teams) - 1

    random.seed(SCHEDULE_SEED)  # the generator draws from the module-level random
    schedule = generate_advanced_schedule(
        [{"team_number": t.team_number, "division": t.division} for t in teams],
        arenas=[f"Arena {i}" for i in range(1, arenas + 1)],
        matches_per_team=series_per_team,
        start_time=start,
        slot_minutes=round_minutes,
    )
    violations = validate_schedule(schedule)
    if violations:
        raise ScheduleError(
            "Could not build a schedule that meets every rule with these settings "
            f"({', '.join(violations)}). Fewer arenas usually fixes back-to-back series."
        )
    try:
        save_schedule(schedule, teams)
    except SQLAlchemyError as exc:
        raise ScheduleError(f"Could not save the schedule: {exc.__class__.__name__}.") from None
    return summary, teams, schedule


def print_schedule(teams, schedule) -> None:
    names = {t.team_number: t.name for t in teams}
    print(f"\n{'Match':>5}  {'Arena':<8} {'Time':>8}  Red  v  Blue")
    for entry in schedule:
        when = clock(datetime.strptime(entry["scheduled_time"], "%Y-%m-%d %H:%M"))
        red, blue = entry["red_team_number"], entry["blue_team_number"]
        print(
            f"{entry['match_number']:>5}  {entry['arena']:<8} {when:>8}  "
            f"{red} {names[red]}  v  {blue} {names[blue]}"
        )
    counts = {t.team_number: 0 for t in teams}
    for entry in schedule:
        counts[entry["red_team_number"]] += 1
        counts[entry["blue_team_number"]] += 1
    print(
        f"\n{len(schedule)} series for {len(teams)} teams, "
        f"{' or '.join(str(c) for c in sorted(set(counts.values())))} each."
    )


def _start(raw: str) -> datetime:
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        raise argparse.ArgumentTypeError(f"use the form 2026-10-24 10:00, not {raw!r}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-make the qualification schedule.")
    parser.add_argument("source", help="Google Sheets link, CSV link, or path to a .csv file")
    parser.add_argument(
        "--leave-out",
        action="append",
        default=[],
        metavar="TEAM",
        help="a team in the sheet that isn't coming (repeat for more than one)",
    )
    parser.add_argument("--arenas", type=int, default=DEFAULT_ARENAS)
    parser.add_argument(
        "--start",
        type=_start,
        default=None,
        help="first round, like '2026-10-24 10:00' (default: EVENT_QUAL_START)",
    )
    parser.add_argument(
        "--round-minutes",
        type=int,
        default=DEFAULT_SLOT_MINUTES,
        help=f"minutes between rounds (the app's default is {DEFAULT_SLOT_MINUTES}; "
        "the manual sets no round length)",
    )
    parser.add_argument("--series", type=int, default=DEFAULT_SERIES_PER_TEAM)
    parser.add_argument(
        "--round-robin", action="store_true",
        help="everyone plays everyone once (overrides --series)",
    )
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1]}")
        start = args.start
        if start is None:
            try:
                start = datetime.strptime(
                    current_app.config.get("EVENT_QUAL_START") or "", "%Y-%m-%d %H:%M"
                )
            except ValueError:
                start = datetime(2026, 10, 24, 10, 0)
        try:
            summary, teams, schedule = premake_schedule(
                args.source,
                args.leave_out,
                args.arenas,
                start,
                args.round_minutes,
                args.series,
                round_robin=args.round_robin,
            )
        except (RosterError, ScheduleError) as exc:
            problems = exc.problems if isinstance(exc, RosterError) else [str(exc)]
            print("No schedule was made:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print_summary(summary)
        print_schedule(teams, schedule)
    return 0


if __name__ == "__main__":
    sys.exit(main())
