from alembic import context

from timmy.config import settings
from timmy.database import make_engine
from timmy.models import metadata

def include_name(name, type_, parent_names):
    return type_ != "table" or not name.startswith("session_trial_")


with make_engine(settings().database_url).connect() as connection:
    context.configure(connection=connection, target_metadata=metadata, render_as_batch=True, include_name=include_name)
    with context.begin_transaction():
        context.run_migrations()
