# owner: shared / lead
# Outbound email, sent through Resend's HTTP API.
#
# Deliberately dependency-free: this is one POST with a bearer token, which
# urllib does cleanly, so there is no mail library to install or keep patched.
# Nothing in here raises — every caller sends mail *after* the work that
# matters is already committed, and a dead network or an expired API key must
# never turn a saved registration into an error page.

import json
import logging
import urllib.error
import urllib.request

from flask import current_app

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"

# api.resend.com sits behind Cloudflare, which blocks urllib's default
# "Python-urllib/3.x" User-Agent outright: the reply is a 403 whose body is the
# bare string "error code: 1010", nothing like Resend's JSON errors. Any real
# User-Agent gets through, so send one.
USER_AGENT = "SRC-Tournament/1.0 (+registration confirmation mail)"


def send_email(to: str, subject: str, html: str, timeout: float = 10.0) -> bool:
    """Send one email. Returns True if Resend accepted it, False otherwise.

    A False return means the message did not go out and the caller should tell
    the user so — it does not mean anything else failed.
    """
    if current_app.config.get("MAIL_SENDER_IS_SHARED"):
        # Not fatal, and deliberately not a reason to skip the send: the one
        # address this does reach is the Resend account owner's, which is what
        # makes it useful for a smoke test. But it is logged at every send,
        # because the alternative is a deployment that looks healthy while no
        # registrant receives anything.
        logger.error(
            "MAIL_FROM is still Resend's shared sender (%s). Resend will accept "
            "this message and deliver it only to the Resend account owner - %s "
            "will not receive it. Verify a domain in Resend and set MAIL_FROM.",
            current_app.config["MAIL_FROM"],
            to,
        )

    api_key = current_app.config.get("RESEND_API_KEY")
    if not api_key:
        # Normal on a laptop, where nobody has the key. Logged so that "why
        # did no email arrive" has an answer in the console.
        logger.warning("RESEND_API_KEY is not set - skipping email to %s", to)
        return False

    payload = json.dumps(
        {
            "from": current_app.config["MAIL_FROM"],
            "to": [to],
            "subject": subject,
            "html": html,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        RESEND_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        logger.info("Resend accepted email to %s (id=%s)", to, body.get("id"))
        return True
    except urllib.error.HTTPError as exc:
        # Resend refused it: bad key, unverified sender domain, malformed
        # recipient. The response body names which, and is the only way to tell.
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        logger.error("Resend rejected email to %s: HTTP %s %s", to, exc.code, detail)
    except urllib.error.URLError as exc:
        logger.error("Could not reach Resend to email %s: %s", to, exc.reason)
    except (TimeoutError, ValueError) as exc:
        # ValueError covers a 200 whose body isn't the JSON we expect.
        logger.error("Unexpected reply from Resend emailing %s: %s", to, exc)
    except Exception:  # deliberately blind - see the module docstring
        # Wider than usual on purpose: the promise this module makes is that
        # sending mail cannot break the caller, and that promise is worth more
        # than surfacing an unforeseen urllib/ssl error to a registrant who is
        # already registered.
        logger.exception("Unhandled failure emailing %s", to)
    return False
