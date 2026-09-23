# owner: shared / lead
# Settings for the app. In development we use a local SQLite file so nobody
# needs to install Postgres just to run the site on their own laptop.

import os
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Loads variables from a local .env file (if one exists) into the
# environment, so os.environ.get(...) below can see them. .env is
# gitignored — see .env.example for which variables to set, and ask
# whoever has the real values for this project's .env file.
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Vercel sets VERCEL_ENV to "production", "preview" or "development" on every
# deployment. Its presence is what tells a deployed function apart from a
# laptop; nothing else about the environment is a reliable signal.
ON_VERCEL = bool(os.environ.get("VERCEL_ENV"))


def _require_on_vercel(name: str, why: str) -> str | None:
    """Return os.environ[name], raising on a deployment if it is missing.

    Locally this returns None and the caller's own default applies, so
    `python run.py` still works with nothing configured. On a deployment a
    missing value is a deploy-time mistake that can only be fixed by setting
    the variable, so it fails at import: that surfaces on the first preview
    instead of being discovered weeks later through missing data.

    This does not weaken the "keep the front door up" rule in app/__init__.py.
    That one covers the database being *unreachable at runtime*, where the
    landing page reads no database and should still render. This covers the
    app never having been *configured* at all.
    """
    value = os.environ.get(name)
    if not value and ON_VERCEL:
        raise RuntimeError(f"{name} is not set on this deployment. {why}")
    return value


def _normalise_db_url(url: str) -> str:
    """Return *url* in the form SQLAlchemy 2.x accepts.

    Most managed Postgres providers hand out a "postgres://" URL. SQLAlchemy
    dropped that alias in 1.4 and raises on it, so the scheme is rewritten to
    "postgresql://" here rather than in every place that reads the setting.
    Anything else (a SQLite path, a URL that already names a driver) is
    returned untouched.
    """
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


class Config:
    # SECRET_KEY signs session cookies, and once people can log in it is what
    # stands between a reader of this repo and a forged session. The literal
    # below is for laptops only; a deployment without a real one refuses to
    # start rather than signing with a value anyone can look up.
    SECRET_KEY = (
        _require_on_vercel(
            "SECRET_KEY",
            "Generate one with `python -c \"import secrets; "
            'print(secrets.token_hex(32))"` and set it in the Vercel project.',
        )
        or "dev-secret-key-change-me"
    )

    # In production the host sets DATABASE_URL to a Postgres URL. Locally we
    # fall back to a SQLite file so `python run.py` just works.
    #
    # There is deliberately no fallback on a deployment. The only writable
    # path on Vercel is /tmp, which is wiped between cold starts, so a SQLite
    # file there accepts writes, reports success, and loses them — survivable
    # when the casualty was a re-enterable registration, not survivable now
    # that the same request can take someone's money.
    SQLALCHEMY_DATABASE_URI = _normalise_db_url(
        _require_on_vercel(
            "DATABASE_URL",
            "Set it to the Neon pooled connection string in the Vercel "
            "project's environment variables and redeploy.",
        )
        or "sqlite:///" + os.path.join(BASE_DIR, "src.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Serverless hosts freeze a container between requests and thaw it later,
    # by which point Postgres has usually dropped the connections the pool
    # still believes in. pre_ping spends one cheap round trip proving a
    # connection is alive rather than failing the first real query on it, and
    # a short recycle keeps us from holding connections across a long freeze.
    # Each instance keeps its own pool, so the pool itself stays small.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {
            "pool_pre_ping": True,
            "pool_recycle": 280,
            "pool_size": 2,
            "max_overflow": 3,
            # Neon scales its compute to zero when idle. Without a timeout a
            # request that arrives cold can spend the function's whole budget
            # waiting on the connect; five seconds fails fast enough to show
            # an error instead of a gateway timeout.
            "connect_args": {"connect_timeout": 5},
        }
        if SQLALCHEMY_DATABASE_URI.startswith("postgresql")
        # SQLite's default pool takes none of these, and passing them raises.
        else {}
    )

    # Registration is the only module finished enough to publish, so every
    # other blueprint is left unregistered — those paths 404 rather than
    # showing a half-built page. Set REGISTRATION_ONLY=0 in your .env (or
    # your shell) to get the whole app back while working locally.
    REGISTRATION_ONLY = os.environ.get("REGISTRATION_ONLY", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )

    # Exposed through app.config so request-time code (app/security.py) can
    # tell a deployment from a laptop without importing this module directly.
    ON_VERCEL = ON_VERCEL

    # Shared passcode for the interim staff gate on the pages that publish
    # coach and student personal data. One passcode for everyone, so it proves
    # "staff" and never "which member of staff" - see app/security.py. Unset on
    # a deployment means those pages 403 rather than publish.
    STAFF_PASSCODE = os.environ.get("STAFF_PASSCODE")

    # Session cookies. SECURE only on a deployment: forcing it locally means
    # the cookie is never sent over http://localhost and nobody can stay
    # logged in while developing. SAMESITE is "Lax" and not "Strict" because
    # "Strict" drops the cookie on the way back from an external redirect —
    # which is exactly how a magic-link click and a return from Stripe both
    # arrive, and both would land the user logged out.
    SESSION_COOKIE_SECURE = ON_VERCEL
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    PREFERRED_URL_SCHEME = "https" if ON_VERCEL else "http"

    # Where "Register a team" sends people. This is a Jotform, not the in-app
    # form at /register/ — the app's own signup still exists and still works,
    # but nothing public links to it. One setting rather than four literals
    # because the landing page links to it from four places, and three of them
    # being updated when the form changes is worse than none.
    REGISTRATION_FORM_URL = os.environ.get(
        "REGISTRATION_FORM_URL", "https://pci.jotform.com/form/262558199273066?utm_id=97760_v0_s00_e0_tv4"
    )

    # Google Form for people interested in competing — not a team
    # registration, so it's kept separate from REGISTRATION_FORM_URL.
    INTEREST_FORM_URL = os.environ.get(
        "INTEREST_FORM_URL",
        "https://docs.google.com/forms/d/e/1FAIpQLSf3rqziN51fZmo9F91nlbyWPIH1NjurJJY3YT0fbwdohZfJjw/viewform?usp=send_form",
    )

    # Where a team pays the $20 registration fee. Registration saves the team
    # first and sends them here afterwards, so a form that is down, moved, or
    # replaced never costs us the registration itself — it only delays the
    # payment. Override with PAYMENT_FORM_URL when the form changes.
    PAYMENT_FORM_URL = os.environ.get(
        "PAYMENT_FORM_URL", "https://form.jotform.com/262558199273066"
    )

    # Stripe. Test keys (sk_test_…) belong on Preview and Development, live
    # keys on Production only — mixing the two is the classic launch bug, and
    # a live key on a preview deploy means a test click takes real money.
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")

    # Signs the webhook. Different per mode AND per endpoint: the secret the
    # Stripe CLI prints for `stripe listen` is not the one the deployed
    # endpoint uses, and swapping them fails every signature check.
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

    # Where Stripe returns the buyer. Must be the real public address, not
    # whatever hostname happened to serve the request — on Vercel that would
    # be a per-deployment preview URL. No trailing slash.
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5000")

    # Outbound email, via Resend. With no key the app still runs and
    # registrations still save — the confirmation email is skipped and the
    # confirmation page says so rather than promising one.
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

    # Must be an address on a domain verified in Resend. The shared
    # onboarding@resend.dev sender only delivers to the Resend account's own
    # address, so it is good for a smoke test and nothing else.
    MAIL_FROM = os.environ.get("MAIL_FROM", "SRC Tournament <onboarding@resend.dev>")

    # True while MAIL_FROM is still Resend's shared sender. This matters more
    # than it looks: Resend *accepts* a message from that address and returns
    # a message id, so send_email reports success, and then the mail is only
    # ever delivered to the Resend account owner. Every other recipient gets
    # nothing, and nothing anywhere reports a failure.
    #
    # So "did Resend accept it" is not the same question as "will it arrive",
    # and anything that promises a registrant an email has to consult this as
    # well. Setting MAIL_FROM to an address on a verified domain turns it off.
    MAIL_SENDER_IS_SHARED = "onboarding@resend.dev" in MAIL_FROM
