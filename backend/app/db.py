from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import get_settings

engine = create_engine(get_settings().database_url.get_secret_value(), pool_pre_ping=True)


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session
