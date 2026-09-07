# owner: shared / lead
#
# This file is the data contract for the whole app. Every blueprint reads
# and writes these tables — nobody creates their own tables or invents a
# parallel shape for the same data. If a field you need isn't here, ask
# before adding it, so everyone stays on the same page.
#
# All datetimes are stored in UTC.

from datetime import datetime

from app.db import db


class Team(db.Model):
    __tablename__ = "team"

    id = db.Column(db.Integer, primary_key=True)
    team_number = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    affiliation = db.Column(db.String(120), nullable=False)  # school name, or "Independent"
    division = db.Column(db.String(50), nullable=False)  # e.g. "Middle School", "Elementary"

    # Stored as a single string with one student name per line. SQLite/Postgres
    # don't have a native "list of strings" column, so this is the simplest
    # thing that works. Split on "\n" to get the list back.
    students = db.Column(db.Text, nullable=False)

    adult_name = db.Column(db.String(120), nullable=False)
    adult_email = db.Column(db.String(200), unique=True, nullable=False)
    adult_phone = db.Column(db.String(30), nullable=True)

    kit_ordered = db.Column(db.Boolean, default=False, nullable=False)
    checked_in = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Inspection(db.Model):
    __tablename__ = "inspection"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)

    passed = db.Column(db.Boolean, nullable=False)
    size_ok = db.Column(db.Boolean, nullable=False)
    weight_ok = db.Column(db.Boolean, nullable=False)
    microbit_present = db.Column(db.Boolean, nullable=False)
    team_number_displayed = db.Column(db.Boolean, nullable=False)
    ref_start_stop_test = db.Column(db.Boolean, nullable=False)

    notes = db.Column(db.Text, nullable=True)
    inspector_name = db.Column(db.String(120), nullable=True)

    # A team may have several Inspections (re-inspection is allowed and both
    # attempts are kept). The one with the latest inspected_at is current.
    inspected_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Match(db.Model):
    __tablename__ = "match"

    id = db.Column(db.Integer, primary_key=True)
    match_number = db.Column(db.Integer, nullable=False)
    phase = db.Column(db.String(20), nullable=False)  # "qualification" or "elimination"
    division = db.Column(db.String(50), nullable=False)
    arena = db.Column(db.String(50), nullable=False)  # e.g. "Arena 1"
    scheduled_time = db.Column(db.DateTime, nullable=True)  # approximate

    red_team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=True)  # nullable: TBD in bracket
    blue_team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=True)

    status = db.Column(db.String(20), default="scheduled", nullable=False)  # scheduled/in_progress/complete
    is_replay = db.Column(db.Boolean, default=False, nullable=False)

    bracket_round = db.Column(db.Integer, nullable=True)  # elimination only
    bracket_slot = db.Column(db.Integer, nullable=True)  # elimination only


class MatchResult(db.Model):
    __tablename__ = "match_result"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)

    outcome = db.Column(db.String(20), nullable=False)  # "red", "blue", "tie", "double_dq"
    win_time_seconds = db.Column(db.Float, nullable=True)  # start button to winner tap
    red_final_zone = db.Column(db.String(50), nullable=False)
    blue_final_zone = db.Column(db.String(50), nullable=False)

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    submitted_by = db.Column(db.String(120), nullable=False)  # referee name or arena id

    # Rule: a MatchResult is created once, by the referee blueprint. After
    # that it may only be changed through the admin blueprint, and every
    # change must write an AuditEntry.


class AuditEntry(db.Model):
    __tablename__ = "audit_entry"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    changed_by = db.Column(db.String(120), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    field = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.String(200), nullable=True)
    new_value = db.Column(db.String(200), nullable=True)


class ScheduleState(db.Model):
    __tablename__ = "schedule_state"

    id = db.Column(db.Integer, primary_key=True)
    is_paused = db.Column(db.Boolean, default=False, nullable=False)
    changed_by = db.Column(db.String(120), nullable=True)  # who paused/resumed the schedule
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)  # when the state last changed

    # Use single-row design: always maintain exactly one row with id=1
    # for global schedule state.
