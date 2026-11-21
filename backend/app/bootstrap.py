import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings
from .db import make_engine, make_sessions
from .seed import seed_demo


def initialize(settings: Settings):
    engine = make_engine(settings.sqlite_path)
    try:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        print("SQLite schema is current.")
        if settings.seed_demo_data:
            seeded = seed_demo(settings, make_sessions(engine))
            print("Demo data initialized." if seeded else "Demo records already exist.")
    except SQLAlchemyError:
        sys.exit("SQLite initialization failed. Check the database path, permissions, and existing demo accounts.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        settings = Settings()
    except ValidationError as error:
        for issue in error.errors(include_input=False, include_context=False, include_url=False):
            location = ".".join(str(part) for part in issue["loc"])
            print(location.upper() or "Configuration", issue["msg"], file=sys.stderr)
        sys.exit(1)
    initialize(settings)
