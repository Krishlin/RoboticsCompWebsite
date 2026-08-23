# owner: Emily
# Pure functions for registration: no Flask, no database. Each one takes
# plain Python values in and returns a plain Python value out, so they can
# be tested by calling them directly.


def assign_team_number(division, existing_team_numbers):
    """Pick the next free team number for a division.

    division: str, e.g. "Middle School"
    existing_team_numbers: list of ints already in use

    Should return an int that isn't already in existing_team_numbers.
    """
    pass


def is_email_unique(email, existing_emails):
    """Return True if `email` isn't already used by another team's adult.

    Registration requires adult_email to be unique across all teams.
    """
    pass


def validate_student_count(students):
    """Return True if `students` (a list of names) has between 1 and 4 names.

    Also worth deciding here: should blank names count? Duplicate names?
    """
    pass
