"""
ApexML → Auto Browser Gateway Integration
==========================================
Wraps the Auto Browser controller behind ApexML's RBAC layer, adds
Prometheus metrics, structured JSON audit logging, and retry/timeout
guardrails per the ApexML S-Tier SRE standard.

Usage (FastAPI app):
    from integrations.apexml_gateway import router as auto_browser_router
    app.include_router(auto_browser_router, prefix="/auto-browser")

Environment variables (add to your .env / docker-compose.yml):
    AUTO_BROWSER_BASE_URL   = http://127.0.0.1:8000      (controller host)
    AUTO_BROWSER_BEARER_TOKEN = <token>                  (empty = no auth)
    AUTO_BROWSER_TIMEOUT_S  = 30                         (per-request timeout)
    AUTO_BROWSER_RETRIES    = 2                          (retry count on 5xx)
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# Structured JSON logger (ApexML standard)
# ---------------------------------------------------------------------------
logger = logging.getLogger("apexml.auto_browser")

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
AB_REQUESTS = Counter(
    "auto_browser_proxy_requests_total",
    "Total requests proxied to Auto Browser controller",
    ["method", "path", "status_code", "operator_id"],
)
AB_LATENCY = Histogram(
    "auto_browser_proxy_latency_seconds",
    "End-to-end latency of proxied Auto Browser requests",
    ["method", "path"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)
AB_ERRORS = Counter(
    "auto_browser_proxy_errors_total",
    "Total errors (timeouts + 5xx) proxying to Auto Browser controller",
    ["error_type"],
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_BASE_URL = os.getenv("AUTO_BROWSER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
_BEARER   = os.getenv("AUTO_BROWSER_BEARER_TOKEN", "")
_TIMEOUT  = float(os.getenv("AUTO_BROWSER_TIMEOUT_S", "30"))
_RETRIES  = int(os.getenv("AUTO_BROWSER_RETRIES", "2"))

# Headers Auto Browser understands for operator identity (RBAC pass-through)
_OPERATOR_ID_HEADER   = os.getenv("OPERATOR_ID_HEADER",   "X-Operator-Id")
_OPERATOR_NAME_HEADER = os.getenv("OPERATOR_NAME_HEADER", "X-Operator-Name")

# ---------------------------------------------------------------------------
# RBAC dependency  (swap in your real RBAC logic here)
# ---------------------------------------------------------------------------

def _get_operator(request: Request) -> dict[str, str]:
    """
    Extract operator identity from the incoming request.

    Reads X-Operator-Id / X-Operator-Name headers set by an upstream
    auth gateway (nginx, API-gateway JWT middleware, etc.).
    Returns a dict that is forwarded to Auto Browser as RBAC context.
    """
    operator_id   = request.headers.get(_OPERATOR_ID_HEADER,   "anonymous")
    operator_name = request.headers.get(_OPERATOR_NAME_HEADER, "anonymous")
    return {"id": operator_id, "name": operator_name}


def require_auto_browser_role(request: Request) -> dict[str, str]:
    """
    Dependency: raises 403 if the operator is not allowed to use Auto Browser.

    Replace the stub allowlist with a real DB/RBAC lookup.
    """
    operator = _get_operator(request)
    # ---- stub: all non-anonymous operators are allowed ----
    if operator["id"] == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Auto Browser requires an authenticated operator.",
        )
    return operator


# ---------------------------------------------------------------------------
# Proxy helper
# ---------------------------------------------------------------------------

async def _proxy(
    method:   str,
    path:     str,
    request:  Request,
    operator: dict[str, str],
) -> Response:
    """Forward *method*+*path* to the Auto Browser controller with retries."""

    target_url = f"{_BASE_URL}{path}"
    body       = await request.body()
    trace_id   = str(uuid.uuid4())

    # Build upstream headers (strip hop-by-hop, inject RBAC + trace)
    headers: dict[str, str] = {}
    hop_by_hop = {
        "host", "content-length", "transfer-encoding",
        "connection", "keep-alive", "upgrade",
        "proxy-authenticate", "proxy-authorization", "te", "trailers",
    }
    for k, v in request.headers.items():
        if k.lower() not in hop_by_hop:
            headers[k] = v

    headers[_OPERATOR_ID_HEADER]   = operator["id"]
    headers[_OPERATOR_NAME_HEADER] = operator["name"]
    headers["X-Trace-Id"]          = trace_id
    if _BEARER:
        headers["Authorization"] = f"Bearer {_BEARER}"

    attempt   = 0
    last_exc: Exception | None = None

    t0 = time.perf_counter()

    while attempt <= _RETRIES:
        attempt += 1
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.request(
                    method  = method.upper(),
                    url     = target_url,
                    headers = headers,
                    content = body,
                    params  = dict(request.query_params),
                )

            elapsed = time.perf_counter() - t0

            # Audit log (S-Tier JSON)
            logger.info(
                "auto_browser_proxy",
                extra={
                    "trace_id":    trace_id,
                    "operator_id": operator["id"],
                    "method":      method.upper(),
                    "path":        path,
                    "status":      resp.status_code,
                    "latency_s":   round(elapsed, 4),
                    "attempt":     attempt,
                },
            )

            # Prometheus
            AB_REQUESTS.labels(
                method      = method.upper(),
                path        = path,
                status_code = str(resp.status_code),
                operator_id = operator["id"],
            ).inc()
            AB_LATENCY.labels(method=method.upper(), path=path).observe(elapsed)

            # Retry on 5xx
            if resp.status_code >= 500 and attempt <= _RETRIES:
                AB_ERRORS.labels(error_type="upstream_5xx").inc()
                await _async_sleep(min(0.5 * attempt, 2.0))
                continue

            return Response(
                content    = resp.content,
                status_code = resp.status_code,
                headers    = {
                    k: v for k, v in resp.headers.items()
                    if k.lower() not in hop_by_hop
                },
                media_type = resp.headers.get("content-type", "application/json"),
            )

        except httpx.TimeoutException as exc:
            elapsed = time.perf_counter() - t0
            AB_ERRORS.labels(error_type="timeout").inc()
            logger.warning(
                "auto_browser_timeout",
                extra={
                    "trace_id": trace_id, "attempt": attempt,
                    "elapsed_s": round(elapsed, 4),
                },
            )
            last_exc = exc
            if attempt <= _RETRIES:
                await _async_sleep(min(0.5 * attempt, 2.0))
                continue

        except Exception as exc:
            AB_ERRORS.labels(error_type="unknown").inc()
            logger.error(
                "auto_browser_error",
                extra={"trace_id": trace_id, "error": str(exc)},
                exc_info=True,
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    raise HTTPException(
        status_code=504,
        detail=f"Auto Browser controller did not respond after {_RETRIES+1} attempts.",
    )


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


# ---------------------------------------------------------------------------
# Router  (catch-all proxy — maps /auto-browser/** → controller/**)
# ---------------------------------------------------------------------------
router = APIRouter(tags=["auto-browser"])


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_to_auto_browser(
    path:     str,
    request:  Request,
    operator: dict[str, str] = Depends(require_auto_browser_role),
) -> Any:
    return await _proxy(
        method   = request.method,
        path     = f"/{path}",
        request  = request,
        operator = operator,
    )


# ---------------------------------------------------------------------------
# Health check (no auth required — safe for load-balancer probes)
# ---------------------------------------------------------------------------
@router.get("/healthz", include_in_schema=False)
async def healthz(request: Request) -> dict[str, str]:
    """Liveness probe: pings the Auto Browser controller /healthz endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_BASE_URL}/healthz")
        return {"status": "ok", "upstream": str(r.status_code)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
