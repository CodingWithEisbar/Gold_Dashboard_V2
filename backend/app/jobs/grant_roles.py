from sqlalchemy import text

from app.db import engine


def main():
    with engine.begin() as connection:
        connection.execute(text("GRANT UPDATE ON data_sources, daily_reference_prices TO gold_ingestor"))
        # IngestionRun is inserted completed; no UPDATE needed. Snapshots never get UPDATE or DELETE.


if __name__ == "__main__":
    main()
