from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from .security import SAFE_METHODS


class RequestBoundary:
    """Apply request policy and populate payload-free context for future middleware."""

    def __init__(self, app, settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        request_id = str(uuid4())
        state.update(request_id=request_id, timestamp=datetime.now(UTC), started_at=perf_counter(),
                     request_bytes=0, response_bytes=0)
        headers = Headers(scope=scope)
        is_api = scope["path"].startswith("/api/")

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                outgoing = MutableHeaders(scope=message)
                outgoing["x-request-id"] = request_id
                outgoing["x-content-type-options"] = "nosniff"
                outgoing["x-frame-options"] = "DENY"
                outgoing["referrer-policy"] = "same-origin"
                outgoing["permissions-policy"] = "camera=(), microphone=(), geolocation=()"
                if self.settings.app_env == "production":
                    outgoing["strict-transport-security"] = "max-age=31536000"
                    outgoing["content-security-policy"] = (
                        "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                        "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
                        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
                    )
                if is_api:
                    outgoing["cache-control"] = "no-store"
                state["response_status"] = message["status"]
            elif message["type"] == "http.response.body":
                state["response_bytes"] += len(message.get("body", b""))
            await send(message)

        async def reject(code, detail):
            await JSONResponse({"detail": detail}, status_code=code)(scope, receive, guarded_send)

        if is_api and scope["method"] not in SAFE_METHODS:
            origin = headers.get("origin")
            if origin is not None and origin not in self.settings.origins:
                state["auth_outcome"] = "origin_denied"
                await reject(403, "Request origin is not allowed")
                return

            size_limit = self.settings.max_body_bytes
            try:
                length = int(headers.get("content-length", "0"))
            except ValueError:
                await reject(400, "Invalid content length")
                return
            if length > size_limit:
                await reject(413, "Request body is too large")
                return

            body = bytearray()
            more = True
            while more:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                part = message.get("body", b"")
                state["request_bytes"] += len(part)
                if state["request_bytes"] > size_limit:
                    await reject(413, "Request body is too large")
                    return
                body.extend(part)
                more = message.get("more_body", False)

            consumed = False

            async def replay():
                nonlocal consumed
                if consumed:
                    return await receive()
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay, guarded_send)
        else:
            await self.app(scope, receive, guarded_send)
