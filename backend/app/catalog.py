from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import DataSource, GoldProduct

SOURCES = [
    ("sjc", "SJC", "https://www.sjc.com.vn/gia-vang-online"),
    ("pnj", "PNJ", "https://giavang.pnj.com.vn/"),
    ("btmh", "Bảo Tín Mạnh Hải", "https://baotinmanhhai.vn/bang-gia-vang"),
    ("metals-dev", "Metals.Dev", "https://www.metals.dev/docs"),
    ("manual-spot", "Spot nhập CSV", "https://www.metals.dev/docs"),
    (
        "manual-fx",
        "FX tham chiếu nhập CSV",
        "https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-tien-ich/Ty-gia",
    ),
]
PRODUCTS = [
    ("sjc-bar-1l-hcm", "sjc", "BAR_1_LUONG", "SJC vàng miếng 1 lượng", "HCM"),
    ("sjc-bar-1c-hcm", "sjc", "BAR_1_CHI", "SJC vàng miếng 1 chỉ", "HCM"),
    ("sjc-ring-9999-hcm", "sjc", "RING_9999", "SJC nhẫn 9999", "HCM"),
    ("pnj-ring-9999-hcm", "pnj", "RING_9999", "PNJ nhẫn 9999", "HCM"),
    (
        "btmh-kgb-24k-listed",
        "btmh",
        "KIM_GIA_BAO_24K",
        "BTMH Kim Gia Bảo 24K (giá niêm yết)",
        "BTMH_LISTED",
    ),
]


def seed_catalog(session: Session) -> None:
    """Metadata only. Never seed market observations."""
    for source_id, name, url in SOURCES:
        if session.get(DataSource, source_id) is None:
            session.add(DataSource(id=source_id, name=name, source_url=url))
    session.flush()
    for product_id, provider_id, code, name, location in PRODUCTS:
        if session.get(GoldProduct, product_id) is None:
            session.add(
                GoldProduct(
                    id=product_id,
                    provider_id=provider_id,
                    product_code=code,
                    name=name,
                    location=location,
                    purity=Decimal("0.9999"),
                )
            )
    session.flush()
