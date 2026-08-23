# owner: shared / lead
# One SQLAlchemy object, shared by every blueprint. Models import `db` from
# here instead of each creating their own database connection.

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
