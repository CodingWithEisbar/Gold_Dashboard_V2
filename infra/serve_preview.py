"""Loopback-only QA server for the built SPA. Never use this as the production web server."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{ROOT / '.tools' / 'ui-preview.db'}"

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.catalog import seed_catalog
from app.db import engine
from app.ingestion.service import VN, ingest, reconcile_day
from app.main import app
from app.config import get_settings
from app.providers.csv_provider import parse_csv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    with Session(engine) as session:
        seed_catalog(session)
        if args.sample:
            observations = parse_csv((ROOT / "sample-data/quotes.sample.csv").read_bytes())
            ingest(session, observations, get_settings())
            for day in {o.provider_timestamp.astimezone(VN).date() for o in observations}:
                reconcile_day(session, day, get_settings())
        session.commit()
    app.mount("/", StaticFiles(directory=ROOT / "frontend/dist", html=True))
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)


if __name__ == "__main__":
    main()
