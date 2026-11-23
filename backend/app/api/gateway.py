import sqlite3
from hmac import compare_digest
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.request_log import PAGE_SIZE
from app.config import get_settings
from app.db import get_db
from app.models import DataSource, IngestionRun

bearer = HTTPBearer(auto_error=False)


def require_gateway_access(authorization: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    settings = get_settings()
    token = settings.api_gateway_token.get_secret_value()
    if not token:
        if settings.api_gateway_local_access:
            return
        raise HTTPException(503, "Cần cấu hình API_GATEWAY_TOKEN để mở trang theo dõi.")
    if not authorization or not compare_digest(authorization.credentials.encode(), token.encode()):
        raise HTTPException(401, "Nhập token truy cập API Gateway.", headers={"WWW-Authenticate": "Bearer"})


router = APIRouter(prefix="/api/v1/gateway", dependencies=[Depends(require_gateway_access)])
Page = Annotated[int, Query(ge=1, le=400)]


@router.get("/requests")
def request_logs(
    request: Request,
    page: Page = 1,
    method: Literal["GET", "POST"] | None = None,
    status_class: Annotated[int | None, Query(ge=2, le=5)] = None,
):
    store = request.app.state.api_request_log
    if store is None:
        raise HTTPException(503, "Kho log API tạm thời không sẵn sàng.")
    try:
        result = store.page(page, method, status_class)
    except sqlite3.Error:
        raise HTTPException(503, "Kho log API tạm thời không sẵn sàng.") from None
    return {**result, "write_failed": request.app.state.api_request_log_failed}


@router.get("/ingestion-runs")
def ingestion_runs(db: Annotated[Session, Depends(get_db)], page: Page = 1):
    entries = db.execute(
        select(IngestionRun, DataSource.name)
        .join(DataSource, DataSource.id == IngestionRun.provider_id)
        .order_by(IngestionRun.id.desc())
        .limit(PAGE_SIZE + 1)
        .offset((page - 1) * PAGE_SIZE)
    ).all()
    return {
        "data": [
            {
                "id": run.id,
                "source": source,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "status": run.status,
                "inserted": run.inserted,
                "duplicates": run.duplicates,
                "quarantined": run.quarantined,
                "error_code": run.error_code,
            }
            for run, source in entries[:PAGE_SIZE]
        ],
        "has_next": len(entries) > PAGE_SIZE,
    }
