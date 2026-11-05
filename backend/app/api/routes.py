import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.schemas import HistoricalRequest, IsoDate, ProductId, ScenarioRequest
from app.config import get_settings
from app.db import get_db
from app.domain.gold_math import VERSION, historical_pnl, scenario
from app.models import DataSource, FxSnapshot, GoldProduct, IngestionRun, QuoteSnapshot, SpotSnapshot
from app.repositories.prices import history, observed_on, quote_payload, vn_today

router = APIRouter(prefix="/api/v1")
Db = Annotated[Session, Depends(get_db)]


def serializable(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    return value


def response(data, **metadata):
    return JSONResponse(
        serializable(
            {"data": data, "calculation_version": VERSION, "currency": "VND", "unit": "VND/luong", **metadata}
        )
    )


def product_or_404(db: Session, product_id: str) -> GoldProduct:
    product = db.get(GoldProduct, product_id)
    if product is None:
        raise HTTPException(404, "Không tìm thấy sản phẩm")
    return product


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Db):
    try:
        db.execute(text("SELECT 1"))
        db.execute(select(GoldProduct.id).limit(1))
        if get_settings().app_env == "production":
            for model in (QuoteSnapshot, SpotSnapshot, FxSnapshot):
                if db.scalar(select(model.id).where(model.reference_type == "sample").limit(1)) is not None:
                    raise HTTPException(503, "Production chứa dữ liệu sample; cần database sạch")
    except SQLAlchemyError:
        raise HTTPException(503, "Database chưa sẵn sàng") from None
    return {"status": "ready"}


@router.get("/catalog/products")
def catalog(db: Db):
    return response(
        [
            {
                "id": p.id,
                "name": p.name,
                "provider_id": p.provider_id,
                "product_code": p.product_code,
                "location": p.location,
                "purity": p.purity,
                "currency": p.currency,
                "unit": p.unit,
            }
            for p in db.scalars(select(GoldProduct).order_by(GoldProduct.id))
        ]
    )


@router.get("/quotes/latest")
def latest(db: Db, product_id: ProductId):
    product_or_404(db, product_id)
    statement = select(QuoteSnapshot).where(
        QuoteSnapshot.product_id == product_id, QuoteSnapshot.quality_flag == "valid"
    )
    if get_settings().app_env == "production":
        statement = statement.where(QuoteSnapshot.reference_type != "sample")
    quote = db.scalar(statement.order_by(QuoteSnapshot.provider_timestamp.desc()).limit(1))
    return response(
        quote_payload(quote) if quote else None,
        data_status="missing" if quote is None else quote_payload(quote)["data_status"],
    )


@router.get("/prices/history")
@router.get("/premiums/history")
def price_history(
    db: Db,
    product_id: ProductId,
    start: Annotated[IsoDate, Query(alias="from")],
    end: Annotated[IsoDate, Query(alias="to")],
):
    if end < start or (end - start).days > 365 or end > vn_today():
        raise HTTPException(422, "Dải ngày tối đa 366 ngày, không gồm tương lai")
    product = product_or_404(db, product_id)
    return response(
        history(db, product, start, end, get_settings()),
        reference_type="daily",
        assumptions=[
            "Giá chốt ngày theo Asia/Ho_Chi_Minh; không carry-forward",
            "FX reference_mid là tham chiếu, không bảo đảm giao dịch được",
        ],
    )


def safe_csv_cell(value) -> str:
    text_value = str(value)
    if text_value.lstrip().startswith(("=", "+", "-", "@")) or text_value.startswith(("\t", "\r", "\n")):
        return "'" + text_value
    return text_value


@router.get("/prices/export.csv")
def export_prices(
    db: Db,
    product_id: ProductId,
    start: Annotated[IsoDate, Query(alias="from")],
    end: Annotated[IsoDate, Query(alias="to")],
):
    result = price_history(db, product_id, start, end)
    import json

    rows = json.loads(result.body)["data"]
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    fields = ["business_date", "bid", "ask", "source", "observed_at", "data_status", "reference_type"]
    writer.writerow(fields)
    for row in rows:
        writer.writerow([safe_csv_cell(row.get(key, "")) for key in fields])
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="gold-prices.csv"'},
    )


@router.get("/premiums/statistics")
def premium_statistics(
    db: Db,
    product_id: ProductId,
    start: Annotated[IsoDate, Query(alias="from")],
    end: Annotated[IsoDate, Query(alias="to")],
):
    import json

    rows = json.loads(price_history(db, product_id, start, end).body)["data"]
    values = [Decimal(row["premium"]["premium_pct"]) for row in rows if row.get("premium")]
    return response(
        {
            "count": len(values),
            "median_pct": median(values) if values else None,
            "percentile_rank_pct": Decimal(sum(v <= values[-1] for v in values)) / Decimal(len(values)) * 100
            if values
            else None,
        },
        reference_type="daily",
        assumptions=["Thống kê chỉ trong kỳ và cùng sản phẩm; không phải tín hiệu mua/bán"],
    )


@router.get("/data-sources/status")
def sources(db: Db):
    result = []
    for source in db.scalars(select(DataSource).order_by(DataSource.id)):
        latest_run = db.scalar(
            select(IngestionRun)
            .where(IngestionRun.provider_id == source.id)
            .order_by(IngestionRun.id.desc())
            .limit(1)
        )
        latest_observed = None
        kinds = set()
        for model in (QuoteSnapshot, SpotSnapshot, FxSnapshot):
            maximum = db.scalar(
                select(func.max(model.provider_timestamp)).where(model.provider_id == source.id)
            )
            if maximum and (latest_observed is None or maximum > latest_observed):
                latest_observed = maximum
            kinds.update(
                db.scalars(select(model.reference_type).where(model.provider_id == source.id).distinct())
            )
        result.append(
            {
                "id": source.id,
                "name": source.name,
                "source_url": source.source_url,
                "license_status": source.license_status,
                "license_note": source.license_note,
                "last_success_at": source.last_success_at,
                "latest_observed_at": latest_observed,
                "reference_types": sorted(kinds),
                "last_error_code": source.last_error_code,
                "status": latest_run.status if latest_run else "not_configured",
                "quota": "Xem hợp đồng/dashboard nhà cung cấp; chưa có credentials để xác minh",
            }
        )
    return response(result)


@router.post("/simulations/historical")
def historical(request: HistoricalRequest, db: Db):
    product_or_404(db, request.product_id)
    settings = get_settings()
    exit_date = request.exit_date
    if exit_date is None:
        statement = select(QuoteSnapshot).where(
            QuoteSnapshot.product_id == request.product_id, QuoteSnapshot.quality_flag == "valid"
        )
        if settings.app_env == "production":
            statement = statement.where(QuoteSnapshot.reference_type != "sample")
        quote = db.scalar(statement.order_by(QuoteSnapshot.provider_timestamp.desc()).limit(1))
        # Use a daily reference for that date; never silently fall back to an earlier day.
        exit_date = quote.business_date if quote else vn_today()
    if (
        exit_date < request.entry_date
        or (exit_date - request.entry_date).days > 3650
        or exit_date > vn_today()
    ):
        raise HTTPException(422, "Ngày mua/bán không hợp lệ")
    entry = observed_on(db, request.product_id, request.entry_date, settings)
    exit_quote = observed_on(db, request.product_id, exit_date, settings)
    if (entry is None and request.manual_entry_ask is None) or exit_quote is None:
        raise HTTPException(
            422, "missing: Không có báo giá đúng ngày. Chọn ngày có dữ liệu hoặc nhập giá mua manual"
        )
    entry_ask = request.manual_entry_ask if request.manual_entry_ask is not None else entry.ask
    costs = request.model_dump(
        include={
            "quantity",
            "unit",
            "buy_fees_vnd",
            "sell_fees_vnd",
            "storage_fees_vnd",
            "applicable_tax_vnd",
        }
    )
    result = historical_pnl(entry_ask=entry_ask, exit_bid=exit_quote.bid, **costs).to_dict()
    result.update(
        holding_days=(exit_date - request.entry_date).days,
        entry={
            "ask": entry_ask,
            "source": "manual",
            "reference_type": "manual",
            "business_date": request.entry_date,
        }
        if request.manual_entry_ask is not None
        else quote_payload(entry),
        exit=quote_payload(exit_quote),
    )
    if request.include_path:
        chart_start = max(request.entry_date, exit_date - timedelta(days=365))
        observations = history(db, product_or_404(db, request.product_id), chart_start, exit_date, settings)
        result["path"] = [
            {
                "business_date": row["business_date"],
                "data_status": row["data_status"],
                "net_pnl_vnd": historical_pnl(entry_ask=entry_ask, exit_bid=row["bid"], **costs).net_pnl_vnd
                if row.get("bid") is not None
                else None,
            }
            for row in observations
        ]
        result["path_assumption"] = (
            "Mark-to-market: cùng entry ask, toàn bộ phí giả định mỗi lần thanh lý; tối đa 366 ngày"
        )
    sample = exit_quote.reference_type == "sample" or (
        entry and entry.reference_type == "sample" and request.manual_entry_ask is None
    )
    return response(
        result,
        data_status="sample" if sample else "available",
        reference_type="historical_theoretical",
        assumptions=[
            "Mua theo ask; thanh lý theo bid, cùng sản phẩm/vùng",
            "Phí/thuế do người dùng nhập, mặc định 0",
            "Báo giá lý thuyết không bảo đảm thanh lý thực tế",
        ],
    )


@router.post("/simulations/scenario")
def scenario_simulation(request: ScenarioRequest):
    try:
        result = scenario(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return response(
        result,
        data_status="scenario",
        reference_type="scenario",
        source="user_assumptions",
        assumptions=[
            "SCENARIO, NOT OBSERVED PRICE",
            "Giữ tỷ giá không đổi trong world_reference_now",
            "Không phải dự báo; phí/thuế do người dùng cung cấp",
        ],
    )
