"""Local administration only. No HTTP upload, arbitrary URL, or path endpoint."""

import csv
import hashlib
import io
import re
from pathlib import Path

from app.providers.base import Observation

HEADERS = [
    "kind",
    "provider_id",
    "product_id",
    "provider_timestamp",
    "bid",
    "ask",
    "value",
    "unit",
    "reference_type",
]
DECIMAL = re.compile(r"\d{1,13}(?:\.\d{1,8})?\Z")
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10000


def parse_csv(raw: bytes) -> list[Observation]:
    if len(raw) > MAX_BYTES:
        raise ValueError("CSV vượt 2 MiB")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    if reader.fieldnames not in (HEADERS, [*HEADERS, "contract"]):
        raise ValueError("CSV sai schema hoặc thứ tự header")
    observations = []
    for row in reader:
        if len(observations) >= MAX_ROWS or None in row or any(v is None for v in row.values()):
            raise ValueError("CSV quá số dòng hoặc sai số cột")
        if any(len(v) > 200 for v in row.values()):
            raise ValueError("CSV field quá dài")
        for field in ("bid", "ask", "value"):
            if row[field] and not DECIMAL.fullmatch(row[field]):
                raise ValueError(f"{field}: dùng chuỗi số thập phân không dấu phân cách")
        identity_fields = reader.fieldnames if row.get("contract") else HEADERS
        payload_hash = hashlib.sha256("\x1f".join(row[k] for k in identity_fields).encode("utf-8")).hexdigest()
        observations.append(
            Observation(**{k: v or None for k, v in row.items()}, raw_payload_hash=payload_hash)
        )
    if not observations:
        raise ValueError("CSV không có dữ liệu")
    return sorted(observations, key=lambda o: o.provider_timestamp)


def read_csv(path: Path, import_root: Path) -> list[Observation]:
    root = import_root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved.suffix.lower() != ".csv":
        raise ValueError("CSV phải nằm trong import root và có đuôi .csv")
    with resolved.open("rb") as stream:
        return parse_csv(stream.read(MAX_BYTES + 1))
