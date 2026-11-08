import argparse

from sqlalchemy.orm import Session

from app.catalog import seed_catalog
from app.db import engine
from app.models import DataSource


def main():
    parser = argparse.ArgumentParser(description="Catalog metadata và xác nhận hợp đồng nguồn")
    parser.add_argument("--license-metals", action="store_true")
    btmh = parser.add_mutually_exclusive_group()
    btmh.add_argument("--license-btmh", action="store_true")
    btmh.add_argument("--revoke-btmh", action="store_true")
    parser.add_argument("--license-note", default="")
    args = parser.parse_args()
    with Session(engine) as session:
        seed_catalog(session)
        if args.license_metals or args.license_btmh:
            if not 10 <= len(args.license_note) <= 1000:
                raise SystemExit("Cần --license-note mô tả hợp đồng/quyền sử dụng, không chứa API key")
            for source_id, selected in (("metals-dev", args.license_metals), ("btmh", args.license_btmh)):
                if selected:
                    source = session.get(DataSource, source_id)
                    source.license_status = "licensed"
                    source.license_note = args.license_note
        if args.revoke_btmh:
            source = session.get(DataSource, "btmh")
            source.license_status = "unverified"
            source.license_note = "Đã thu hồi xác nhận; dừng thu thập tự động BTMH"
        session.commit()


if __name__ == "__main__":
    main()
