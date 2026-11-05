import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.api.security import RequestGate
from app.config import get_settings

settings = get_settings()
app = FastAPI(
    title="Gold Premium Tracker",
    debug=False,
    docs_url=None if settings.app_env == "production" else "/docs",
    redoc_url=None,
    openapi_url=None if settings.app_env == "production" else "/openapi.json",
)
app.add_middleware(RequestGate, max_body=settings.max_body_bytes, limit=settings.rate_limit_per_minute)
app.include_router(router)


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
