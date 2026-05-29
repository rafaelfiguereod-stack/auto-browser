from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from ..models import ShareSessionRequest
from ._utils import internal_error

logger = logging.getLogger(__name__)


def create_share_router(*, manager: Any, share_manager: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/sessions/{session_id}/share")
    async def share_session(session_id: str, payload: ShareSessionRequest | None = None) -> dict[str, Any]:
        try:
            await manager.get_session(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown session") from None

        ttl_minutes = payload.ttl_minutes if payload is not None else 60
        try:
            return share_manager.create_token(session_id, ttl_seconds=ttl_minutes * 60)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid request") from None

    @router.get("/share/{token}/observe")
    async def shared_observe(token: str) -> dict[str, Any]:
        info = share_manager.token_info(token)
        if not info.get("valid"):
            raise HTTPException(status_code=403, detail="Invalid token")
        try:
            return await manager.observe(info["session_id"])
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown session") from None
        except Exception:
            raise internal_error(logger, "shared observe failed") from None

    @router.get("/share/{token}", response_class=HTMLResponse)
    async def shared_session_view(token: str) -> HTMLResponse:
        info = share_manager.token_info(token)
        if not info.get("valid"):
            raise HTTPException(status_code=403, detail="Invalid token")
        try:
            await manager.get_session(info["session_id"])
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown session") from None

        html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Shared Session Observer</title>
    <style>
      :root {
        color-scheme: dark;
        --bg: #111418;
        --panel: #1a2027;
        --panel-border: #2b3440;
        --text: #f5f7fa;
        --muted: #9aa6b2;
        --accent: #7dd3fc;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: ui-sans-serif, system-ui, sans-serif;
        background:
          radial-gradient(circle at top, rgba(125, 211, 252, 0.16), transparent 28%),
          linear-gradient(180deg, #0b0f14, var(--bg));
        color: var(--text);
      }
      main {
        max-width: 1180px;
        margin: 0 auto;
        padding: 24px;
      }
      header {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 18px;
      }
      h1 {
        margin: 0;
        font-size: 1.2rem;
      }
      .meta {
        color: var(--muted);
        font-size: 0.95rem;
      }
      .panel {
        background: rgba(26, 32, 39, 0.92);
        border: 1px solid var(--panel-border);
        border-radius: 18px;
        overflow: hidden;
        box-shadow: 0 18px 40px rgba(0, 0, 0, 0.24);
      }
      .toolbar {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
        justify-content: space-between;
        padding: 14px 18px;
        border-bottom: 1px solid var(--panel-border);
      }
      .status {
        color: var(--muted);
        font-size: 0.95rem;
      }
      .status strong {
        color: var(--accent);
      }
      .frame {
        aspect-ratio: 16 / 10;
        width: 100%;
        background: #0b0f14;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      img {
        width: 100%;
        height: 100%;
        object-fit: contain;
        display: block;
      }
      .error {
        padding: 24px;
        color: #fecaca;
      }
      a {
        color: var(--accent);
      }
    </style>
  </head>
  <body>
    <main>
      <header>
        <div>
          <h1>Shared Session Observer</h1>
          <div class="meta">Session <code id="session-id"></code></div>
        </div>
        <div class="meta" id="url">Waiting for first snapshot…</div>
      </header>
      <section class="panel">
        <div class="toolbar">
          <div class="status"><strong id="state">Connecting</strong> <span id="detail">Fetching shared observe payload…</span></div>
          <div class="meta" id="updated">Never updated</div>
        </div>
        <div class="frame" id="frame">
          <div class="meta">Loading screenshot…</div>
        </div>
      </section>
    </main>
    <script>
      const token = window.location.pathname.split("/").filter(Boolean).pop() || "";
      const observeUrl = `/share/${token}/observe`;
      const imageEl = document.createElement("img");
      const frameEl = document.getElementById("frame");
      const stateEl = document.getElementById("state");
      const detailEl = document.getElementById("detail");
      const updatedEl = document.getElementById("updated");
      const urlEl = document.getElementById("url");
      const sessionIdEl = document.getElementById("session-id");
      const safeHttpUrl = (value) => {
        if (!value) return null;
        try {
          const parsed = new URL(String(value), window.location.origin);
          if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
        } catch (_) {}
        return null;
      };
      const setSnapshotUrl = (value) => {
        urlEl.replaceChildren();
        const href = safeHttpUrl(value);
        if (!href) {
          urlEl.textContent = "No URL available";
          return;
        }
        const link = document.createElement("a");
        link.href = href;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = href;
        urlEl.appendChild(link);
      };
      const showFrameError = (message) => {
        const errorEl = document.createElement("div");
        errorEl.className = "error";
        errorEl.textContent = `Unable to refresh shared session: ${message}`;
        frameEl.replaceChildren(errorEl);
      };

      async function refresh() {
        try {
          const response = await fetch(observeUrl, { cache: "no-store" });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const payload = await response.json();
          const sessionId = payload.session && payload.session.id ? payload.session.id : "Shared session";
          sessionIdEl.textContent = sessionId;
          imageEl.src = `${payload.screenshot_url}?ts=${Date.now()}`;
          imageEl.alt = payload.title || payload.url || sessionId;
          if (!imageEl.isConnected) {
            frameEl.replaceChildren(imageEl);
          }
          stateEl.textContent = "Live";
          detailEl.textContent = payload.title || "Shared observe payload loaded";
          setSnapshotUrl(payload.url);
          updatedEl.textContent = `Updated ${new Date().toLocaleTimeString()}`;
        } catch (error) {
          showFrameError(error.message);
          stateEl.textContent = "Error";
          detailEl.textContent = "Retrying every 5 seconds";
          updatedEl.textContent = `Last attempt ${new Date().toLocaleTimeString()}`;
        }
      }

      refresh();
      setInterval(refresh, 5000);
    </script>
  </body>
</html>"""
        return HTMLResponse(content=html)

    return router
