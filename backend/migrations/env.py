from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.models import Base, UTCDateTime

target_metadata = Base.metadata


def render_item(kind, obj, autogen_context):
    if kind == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations():
    url = get_settings().database_url.get_secret_value()
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, poolclass=pool.NullPool)
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                render_item=render_item,
            )
            with context.begin_transaction():
                context.run_migrations()


run_migrations()
