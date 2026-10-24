# owner: shared / lead
#
# Load the real teams from the registration sheet into the database that
# DATABASE_URL points at (your local SQLite file when it is unset):
#
#   python -m seed.teams <sheet link, CSV link, or path to a .csv file>
#   python -m seed.teams <...> --remove-missing
#
# The ordinary Google Sheets link works; it is turned into the sheet's CSV
# export. The sheet has to be shared as "anyone with the link can view" for
# that, otherwise download it (File > Download > .csv) and pass the file.
#
# The link is not written down anywhere in this repo on purpose: the repo is
# public and the sheet holds students' and parents' names and emails.
#
# This is an import, not a wipe: teams already in the database keep their
# numbers and check-in, and are updated from the sheet (see app/roster.py).
# The head ref's "Import teams" page does the same thing from a browser.

import argparse
import re
import sys
import urllib.error
import urllib.request

from app import create_app
from app.roster import MAX_BYTES, RosterError, decode, import_roster, parse_roster

_SHEET_URL = re.compile(r"https://docs\.google\.com/spreadsheets/d/([\w-]+)")
_GID = re.compile(r"[#&?]gid=(\d+)")

DOWNLOAD_TIMEOUT_SECONDS = 20


def csv_url(source: str) -> str:
    """A Google Sheets link as its CSV export link. Anything else is unchanged."""
    match = _SHEET_URL.match(source)
    if match is None or "/export" in source:
        return source
    url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv"
    gid = _GID.search(source)
    return url + (f"&gid={gid.group(1)}" if gid else "")


def read_source(source: str) -> str:
    """The roster CSV text from a URL or a file. Raises RosterError."""
    if source.startswith(("https://", "http://")):
        url = csv_url(source)
        try:
            with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_BYTES + 1)
                content_type = response.headers.get("Content-Type", "")
        except (urllib.error.URLError, OSError) as exc:
            # URLError covers DNS failures and HTTP errors (a 404 for a deleted
            # sheet); OSError covers timeouts and dropped connections.
            raise RosterError([f"Could not download the sheet: {exc}."]) from None
        if "html" in content_type:
            # What Google serves when the sheet is no longer shared by link: a
            # sign-in page, with a 200.
            raise RosterError(
                [
                    "The link returned a web page, not CSV. The sheet is probably not shared "
                    "by link any more. Download it as .csv and pass the file instead."
                ]
            )
        return decode(raw)

    try:
        with open(source, "rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
    except OSError as exc:
        raise RosterError([f"Could not read {source}: {exc.strerror or exc}."]) from None
    return decode(raw)


def load_teams(source: str, remove_missing: bool = False):
    """Read, check and import a roster. Needs an app context. Raises RosterError."""
    return import_roster(parse_roster(read_source(source)), remove_missing=remove_missing)


def print_summary(summary) -> None:
    for team in summary.added:
        print(f"  added    {team.team_number}  {team.name}")
    for team in summary.updated:
        print(f"  updated  {team.team_number}  {team.name}")
    for label in summary.removed:
        print(f"  removed  {label}")
    for team in summary.not_in_file:
        print(f"  kept     {team.team_number}  {team.name}  (not in the sheet)")
    print(
        f"{len(summary.added)} added, {len(summary.updated)} updated, "
        f"{len(summary.unchanged)} unchanged, {len(summary.removed)} removed."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import the team roster from the registration sheet."
    )
    parser.add_argument("source", help="Google Sheets link, CSV link, or path to a .csv file")
    parser.add_argument(
        "--remove-missing",
        action="store_true",
        help="delete teams that are not in the sheet (never ones already in a match)",
    )
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1]}")
        try:
            summary = load_teams(args.source, remove_missing=args.remove_missing)
        except RosterError as exc:
            print("Nothing was imported:", file=sys.stderr)
            for problem in exc.problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
