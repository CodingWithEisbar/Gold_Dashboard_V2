import time
from collections import OrderedDict

from starlette.responses import JSONResponse


class RequestGate:
    """Bounded per-peer limiter. Edge proxy adds its own limit; do not trust client forwarding headers."""

    def __init__(self, app, max_body=16384, limit=120):
        self.app = app
        self.max_body = max_body
        self.limit = limit
        self.peers = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        if (
            scope["method"] == "POST"
            and headers.get(b"content-type", b"").split(b";")[0] != b"application/json"
        ):
            return await JSONResponse({"detail": "Yêu cầu application/json"}, 415)(scope, receive, send)
        client = (scope.get("client") or ("unknown", 0))[0]
        minute = int(time.monotonic() // 60)
        previous_minute, count = self.peers.pop(client, (minute, 0))
        count = count + 1 if previous_minute == minute else 1
        self.peers[client] = (minute, count)
        if len(self.peers) > 2048:
            self.peers.popitem(last=False)
        if count > self.limit and not scope["path"].startswith("/api/v1/health/"):
            return await JSONResponse({"detail": "Quá giới hạn yêu cầu"}, 429, headers={"Retry-After": "60"})(
                scope, receive, send
            )
        body = bytearray()
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_body:
                return await JSONResponse({"detail": "Payload quá lớn"}, 413)(scope, receive, send)
            more = message.get("more_body", False)
        received = False

        async def replay():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-content-type-options", b"nosniff"),
                    (b"cache-control", b"no-store"),
                    (b"referrer-policy", b"no-referrer"),
                ]
            await send(message)

        await self.app(scope, replay, secure_send)
