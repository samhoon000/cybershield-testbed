from alembic import context

from app.config import Settings
from app.db import make_engine
from app.models import Base

existing = context.config.attributes.get("connection")
if existing is not None:
    context.configure(connection=existing, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(Settings().sqlite_path)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
