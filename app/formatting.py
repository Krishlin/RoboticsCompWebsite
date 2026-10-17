# owner: shared / lead
# Small Jinja filters every blueprint's templates can use. Registered in
# app/__init__.py.

from datetime import timedelta

from flask import current_app


def clock(value) -> str:
    """A scheduled time as people say it at the event: "10:15 AM".

    Scheduled times are approximate and the event is one day, so the date and
    the seconds are noise on a match list. None (a bracket series, which has
    no fixed time) reads as "TBD" rather than the word "None".
    """
    if value is None:
        return "TBD"
    hour = value.hour % 12 or 12
    return f"{hour}:{value.minute:02d} {'AM' if value.hour < 12 else 'PM'}"


def seconds(value) -> str:
    """A win time to one decimal place, or a dash when there isn't one."""
    if value is None:
        return "—"
    return f"{value:.1f}s"


def local_clock(value, seconds: bool = False) -> str:
    """A stored UTC time (models.py utcnow) as the event's wall-clock time.

    Created-at stamps - inspections, audit entries, the bracket - are UTC, but
    the people reading them are in a gym in Arcadia, and "5:15 PM" for a
    10:15 AM inspection is wrong in a way nobody would catch. Scheduled match
    times are already local, so they use `clock` instead.

    An offset rather than a zone name: zoneinfo needs the tzdata package on
    Windows, and the event is one day with no clock change in it.
    """
    if value is None:
        return "—"
    offset = current_app.config.get("EVENT_UTC_OFFSET_HOURS", -7)
    local = value + timedelta(hours=offset)
    text = clock(local)
    if seconds:
        hour, rest = text.split(":", 1)
        text = f"{hour}:{rest[:2]}:{local.second:02d}{rest[2:]}"
    return text
