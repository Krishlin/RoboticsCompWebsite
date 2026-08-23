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


class Config:
    # SECRET_KEY signs session cookies. This is a placeholder for development
    # only — a real deployment must set a real secret via an environment
    # variable, not commit one to the repo.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # In production, Render/Railway will set DATABASE_URL to a Postgres URL.
    # Locally, we fall back to a SQLite file so `python run.py` just works.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "src.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Supabase project credentials. Not used by any route yet — nobody has
    # designed what Supabase is for in this app (extra Postgres database?
    # auth? file storage?). Whoever picks that up next reads these from
    # app.config within a route, the same way SQLALCHEMY_DATABASE_URI is
    # read above. Get the real values from whoever has the project's .env.
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")
    SUPABASE_JWKS_URL = os.environ.get("SUPABASE_JWKS_URL")
