# owner: shared / lead
#
# The interim staff gate. This is deliberately the smallest thing that closes
# the hole: /register/teams and /register/teams.csv publish every coach's name,
# email and phone plus every student's name, and until today they did it to
# anyone on the internet who guessed the URL.
#
# HTTP Basic rather than a login page, on purpose. There is no Account model
# yet, no session login, and no CSRF protection on forms, so a hand-rolled
# login form would need all three before it protected anything. Basic auth
# needs none of them, the browser draws the prompt, and `curl -u` still works
# for a check-in desk pulling the CSV onto a laptop. It is replaced wholesale
# by real accounts in a later phase - see the plan - and nothing beyond the
# two gates below should be built on top of it in the meantime.
#
# What it is NOT: verified per-person identity. Everyone shares one passcode,
# so it proves "staff", never "which member of staff". The Basic-auth
# username is the one place a person's name can ride along, so the head-ref
# gate below insists on one and the audit log records it — self-reported, the
# same standing as Inspection.inspector_name, and labelled as such. Real
# accounts replace all of this in a later phase.
#
# Two gates, because the game manual and the project plan both separate the
# people at the arenas from the person whose decision is final (T7):
#   staff_required     referees, check-in and inspection volunteers
#   head_ref_required  results editing, the audit log, pause/resume, the
#                      schedule generator, building the bracket, exports

import hmac
import logging
from functools import wraps

from flask import Response, abort, current_app, request

logger = logging.getLogger(__name__)

_STAFF_REALM = 'Basic realm="Summit staff", charset="UTF-8"'
# A different realm, so a browser that already holds the staff passcode still
# asks for the head ref's instead of replaying the wrong one.
_HEAD_REF_REALM = 'Basic realm="Summit head referee", charset="UTF-8"'


def _passcode_matches(supplied: str | None, expected: str) -> bool:
    """Constant-time comparison against the configured passcode.

    compare_digest rather than == so the comparison does not return early on
    the first wrong character. The timing signal is tiny over HTTP, but this
    costs nothing and the habit is worth more than the microseconds.
    """
    if not supplied:
        return False
    # Bytes, because compare_digest raises TypeError on a str with non-ASCII
    # characters, which would turn a typed "é" into a 500 instead of a 401.
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def current_staff_name() -> str | None:
    """The name typed as the Basic-auth username, if any. Self-reported."""
    auth = request.authorization
    if auth is None or not auth.username:
        return None
    name = auth.username.strip()
    return name[:120] or None


def _gate(config_key: str, realm: str, require_name: bool):
    """Build a decorator that requires the passcode stored at *config_key*.

    Fails closed on a deployment: with no passcode set, the route 403s rather
    than serving the data. An unset variable is a configuration mistake, and
    the safe reading of "I don't know who may see this" is nobody.

    Locally it falls open with a warning instead, so `python run.py` keeps
    working with no configuration at all - the same trade config.py already
    makes for SECRET_KEY and DATABASE_URL. Local is not where the leak is.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            configured = current_app.config.get(config_key)

            if not configured:
                if current_app.config.get("ON_VERCEL"):
                    logger.error(
                        "%s is not set on this deployment - refusing to serve %s "
                        "rather than publishing it. Set it in the Vercel "
                        "project's environment variables.",
                        config_key,
                        request.path,
                    )
                    abort(403)
                logger.warning(
                    "%s is not set - serving %s unprotected because this is not "
                    "a deployment. Set %s in your .env to exercise the real "
                    "behaviour.",
                    config_key,
                    request.path,
                    config_key,
                )
                return view(*args, **kwargs)

            auth = request.authorization
            if auth is not None and _passcode_matches(auth.password, configured):
                if require_name and current_staff_name() is None:
                    return Response(
                        "Type your name as the username. The audit log records "
                        "who made each change.\n",
                        401,
                        {"WWW-Authenticate": realm, "Content-Type": "text/plain; charset=utf-8"},
                    )
                return view(*args, **kwargs)

            return Response(
                "This page is for event staff.\n",
                401,
                {"WWW-Authenticate": realm, "Content-Type": "text/plain; charset=utf-8"},
            )

        return wrapped

    return decorator


# Any username is accepted here: referees and volunteers may type their name
# (the referee page records it as submitted_by) but nothing depends on it.
staff_required = _gate("STAFF_PASSCODE", _STAFF_REALM, require_name=False)

head_ref_required = _gate("HEAD_REF_PASSCODE", _HEAD_REF_REALM, require_name=True)
