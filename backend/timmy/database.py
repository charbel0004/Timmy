from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if make_url(url).get_backend_name() != "sqlite":
        raise ValueError("Phase 1 requires SQLite")
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # Serialise concurrent writers instead of failing a workflow mid-resume.
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine
