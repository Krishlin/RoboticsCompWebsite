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
# by real accounts in a later phase - see the plan - and nothing else should
# be built on top of it in the meantime.
#
# What it is NOT: per-person identity. Everyone shares one passcode, so it
# cannot answer "who exported the list". That is exactly why AuditEntry keeps
# waiting for real accounts rather than being wired to this.

import hmac
import logging
from functools import wraps

from flask import Response, abort, current_app, request

logger = logging.getLogger(__name__)

_REALM = 'Basic realm="Summit staff", charset="UTF-8"'


def _passcode_matches(supplied: str | None) -> bool:
    """Constant-time comparison against the configured passcode.

    compare_digest rather than == so the comparison does not return early on
    the first wrong character. The timing signal is tiny over HTTP, but this
    costs nothing and the habit is worth more than the microseconds.
    """
    expected = current_app.config.get("STAFF_PASSCODE") or ""
    return bool(supplied) and hmac.compare_digest(supplied, expected)


def staff_required(view):
    """Require the shared staff passcode before running *view*.

    Fails closed on a deployment: with no STAFF_PASSCODE set, the route 403s
    rather than serving the data. An unset variable is a configuration
    mistake, and the safe reading of "I don't know who may see this" is
    nobody.

    Locally it falls open with a warning instead, so `python run.py` keeps
    working with no configuration at all - the same trade config.py already
    makes for SECRET_KEY and DATABASE_URL. Local is not where the leak is.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        configured = current_app.config.get("STAFF_PASSCODE")

        if not configured:
            if current_app.config.get("ON_VERCEL"):
                logger.error(
                    "STAFF_PASSCODE is not set on this deployment - refusing to "
                    "serve %s rather than publishing it. Set it in the Vercel "
                    "project's environment variables.",
                    request.path,
                )
                abort(403)
            logger.warning(
                "STAFF_PASSCODE is not set - serving %s unprotected because this "
                "is not a deployment. Set STAFF_PASSCODE in your .env to "
                "exercise the real behaviour.",
                request.path,
            )
            return view(*args, **kwargs)

        auth = request.authorization
        # Only the password is checked. Any username is accepted because there
        # are no usernames yet; inventing one here would imply an identity the
        # system cannot actually verify.
        if auth is not None and _passcode_matches(auth.password):
            return view(*args, **kwargs)

        return Response(
            "This page is for event staff.\n",
            401,
            {"WWW-Authenticate": _REALM, "Content-Type": "text/plain; charset=utf-8"},
        )

    return wrapped
