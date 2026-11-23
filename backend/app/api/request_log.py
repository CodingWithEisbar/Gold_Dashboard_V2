import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from starlette.concurrency import run_in_threadpool

PAGE_SIZE = 25
MAX_REQUESTS = 10_000


class RequestLog:
    def __init__(self, path: Path):
        self.lock = Lock()
        self.connection = sqlite3.connect(path, timeout=1, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        try:
            with closing(self.connection.execute("PRAGMA journal_mode=WAL")) as cursor:
                cursor.fetchone()
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS api_requests (
                    id INTEGER PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    method TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    status INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL
                )
            """)
        except sqlite3.Error:
            self.connection.close()
            raise

    def append(self, started_at: str, method: str, endpoint: str, status: int, duration_ms: int):
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """INSERT INTO api_requests (started_at, method, endpoint, status, duration_ms)
                   VALUES (?, ?, ?, ?, ?)""",
                (started_at, method, endpoint, status, duration_ms),
            )
            self.connection.execute("DELETE FROM api_requests WHERE id <= ?", (cursor.lastrowid - MAX_REQUESTS,))

    def page(self, page: int, method: str | None, status_class: int | None):
        lower = status_class * 100 if status_class is not None else 100
        upper = lower + 99 if status_class is not None else 599
        with self.lock:
            rows = self.connection.execute(
                """SELECT * FROM api_requests
                   WHERE (? IS NULL OR method = ?) AND status BETWEEN ? AND ?
                   ORDER BY id DESC LIMIT ? OFFSET ?""",
                (method, method, lower, upper, PAGE_SIZE + 1, (page - 1) * PAGE_SIZE),
            ).fetchall()
        return {"data": [dict(row) for row in rows[:PAGE_SIZE]], "has_next": len(rows) > PAGE_SIZE}

    def close(self):
        with self.lock:
            self.connection.close()


class ApiRequestLogging:
    def __init__(self, app, endpoints: frozenset[str]):
        self.app = app
        self.endpoints = endpoints

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"GET", "POST"}:
            return await self.app(scope, receive, send)
        path = scope["path"]
        if not path.startswith("/api/v1/") or path.startswith("/api/v1/gateway/"):
            return await self.app(scope, receive, send)
        store = scope["app"].state.api_request_log
        if store is None:
            return await self.app(scope, receive, send)

        started_at = datetime.now(UTC).isoformat()
        start = time.perf_counter()
        status = None

        async def capture(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        except Exception:
            if status is None:
                status = 500
            raise
        finally:
            if status is not None:
                route = getattr(scope.get("route"), "path", path)
                endpoint = route if route in self.endpoints else "(unknown)"
                duration_ms = round((time.perf_counter() - start) * 1000)
                try:
                    await run_in_threadpool(store.append, started_at, scope["method"], endpoint, status, duration_ms)
                except sqlite3.Error:
                    # Logging must never change the result of a market request.
                    scope["app"].state.api_request_log_failed = True
