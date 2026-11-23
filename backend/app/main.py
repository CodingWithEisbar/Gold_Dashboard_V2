import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.gateway import router as gateway_router
from app.api.request_log import ApiRequestLogging, RequestLog
from app.api.routes import router
from app.api.security import RequestGate
from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    log_path = get_settings().api_log_path
    store = None
    if log_path:
        try:
            store = RequestLog(log_path)
        except sqlite3.Error:
            logging.getLogger("gold").error('{"event":"api_request_log_unavailable"}')
    application.state.api_request_log = store
    application.state.api_request_log_failed = False
    try:
        yield
    finally:
        if store is not None:
            store.close()


app = FastAPI(
    title="Gold Premium Tracker",
    lifespan=lifespan,
    debug=False,
    docs_url=None if settings.app_env == "production" else "/docs",
    redoc_url=None,
    openapi_url=None if settings.app_env == "production" else "/openapi.json",
)
app.add_middleware(RequestGate, max_body=settings.max_body_bytes, limit=settings.rate_limit_per_minute)
app.add_middleware(ApiRequestLogging, endpoints=frozenset(route.path for route in router.routes))
app.include_router(router)
app.include_router(gateway_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not reflect arbitrary user/provider input into errors.
    return JSONResponse(
        {
            "detail": "Dữ liệu không hợp lệ",
            "errors": [
                {"field": ".".join(str(item) for item in error["loc"]), "type": error["type"]}
                for error in exc.errors()
            ],
        },
        status_code=422,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logging.getLogger("gold").error('{"event":"database_error"}')
    return JSONResponse({"detail": "Dịch vụ dữ liệu tạm thời không sẵn sàng"}, status_code=503)
