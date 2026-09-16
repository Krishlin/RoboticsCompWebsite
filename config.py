# owner: shared / lead
# Settings for the app. In development we use a local SQLite file so nobody
# needs to install Postgres just to run the site on their own laptop.

import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Loads variables from a local .env file (if one exists) into the
# environment, so os.environ.get(...) below can see them. .env is
# gitignored — see .env.example for which variables to set, and ask
# whoever has the real values for this project's .env file.
load_dotenv(os.path.join(BASE_DIR, ".env"))


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
    # SECRET_KEY signs session cookies. This is a placeholder for development
    # only — a real deployment must set a real secret via an environment
    # variable, not commit one to the repo.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # In production, the host sets DATABASE_URL to a Postgres URL. Locally, we
    # fall back to a SQLite file so `python run.py` just works.
    SQLALCHEMY_DATABASE_URI = _normalise_db_url(
        os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "src.db"))
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

    # Supabase project credentials. Not used by any route yet — nobody has
    # designed what Supabase is for in this app (extra Postgres database?
    # auth? file storage?). Whoever picks that up next reads these from
    # app.config within a route, the same way SQLALCHEMY_DATABASE_URI is
    # read above. Get the real values from whoever has the project's .env.
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")
    SUPABASE_JWKS_URL = os.environ.get("SUPABASE_JWKS_URL")

    # Where a team pays the $20 registration fee. Registration saves the team
    # first and sends them here afterwards, so a form that is down, moved, or
    # replaced never costs us the registration itself — it only delays the
    # payment. Override with PAYMENT_FORM_URL when the form changes.
    PAYMENT_FORM_URL = os.environ.get(
        "PAYMENT_FORM_URL", "https://form.jotform.com/262558199273066"
    )

    # Outbound email, via Resend. With no key the app still runs and
    # registrations still save — the confirmation email is skipped and the
    # confirmation page says so rather than promising one.
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

    # Must be an address on a domain verified in Resend. The shared
    # onboarding@resend.dev sender only delivers to the Resend account's own
    # address, so it is good for a smoke test and nothing else.
    MAIL_FROM = os.environ.get("MAIL_FROM", "SRC Tournament <onboarding@resend.dev>")
