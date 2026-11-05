import argparse

from sqlalchemy.orm import Session

from app.catalog import seed_catalog
from app.db import engine
from app.models import DataSource


def main():
    parser = argparse.ArgumentParser(description="Catalog metadata và xác nhận hợp đồng nguồn")
    parser.add_argument("--license-metals", action="store_true")
    parser.add_argument("--license-note", default="")
    args = parser.parse_args()
    with Session(engine) as session:
        seed_catalog(session)
        if args.license_metals:
            if not 10 <= len(args.license_note) <= 1000:
                raise SystemExit("Cần --license-note mô tả hợp đồng/quyền sử dụng, không chứa API key")
            source = session.get(DataSource, "metals-dev")
            source.license_status = "licensed"
            source.license_note = args.license_note
        session.commit()


if __name__ == "__main__":
    main()
