# Auto Browser → ApexML Platform Integration Guide

## Architecture Overview

```
Claude Desktop (MCP)
       │ stdio
       ▼
scripts/mcp_stdio_bridge.py
       │ HTTP
       ▼
Auto Browser Controller  :8000   ←── ApexML Gateway router (this file)
       │ WebSocket
       ▼
Browser Node (Playwright + noVNC)  :6080 / :9223
```

---

## Step 1 — Wire the router into your FastAPI api-gateway

In your ApexML `api-gateway/main.py` (or wherever your FastAPI `app` lives):

```python
from integrations.apexml_gateway import router as auto_browser_router

# Add after all your existing routers:
app.include_router(auto_browser_router, prefix="/auto-browser", tags=["auto-browser"])
```

All Auto Browser endpoints will then be available under `/auto-browser/...` with:

- RBAC enforcement (Bearer token via X-Operator-Id header)
- Prometheus metrics (auto_browser_proxy_requests_total, auto_browser_proxy_latency_seconds)
- Retry + timeout (configurable via env vars)
- Structured JSON audit log on every request

---

## Step 2 — Environment variables

Add to your `api-gateway/.env` or `docker-compose.yml` service env:

```env
AUTO_BROWSER_BASE_URL=http://127.0.0.1:8000
AUTO_BROWSER_BEARER_TOKEN=          # leave empty if no auth configured
AUTO_BROWSER_TIMEOUT_S=30
AUTO_BROWSER_RETRIES=2
```

---

## Step 3 — Prometheus scrape config

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: auto_browser_gateway
    static_configs:
      - targets: ['localhost:8001']   # adjust to your api-gateway port
    metrics_path: /metrics
```

Key metrics to alert on:

- `auto_browser_proxy_errors_total{error_type="timeout"}` — browser node unresponsive
- `auto_browser_proxy_errors_total{error_type="upstream_5xx"}` — controller crashes
- `auto_browser_proxy_latency_seconds_p99 > 10` — slow browser actions

---

## Step 4 — RBAC usage

Pass the operator identity in every request from internal services:

```http
GET /auto-browser/mcp/tools
X-Operator-Id: worker-service
Authorization: Bearer <AUTO_BROWSER_BEARER_TOKEN>
```

The gateway logs `operator_id` on every audit entry and labels all Prometheus counters with it.

---

## Daily Operations

TaskCommandStart stack (after reboot)`start_auto_browser_stack.bat`Check health`curl http://localhost:8000/healthz`View browser live<http://localhost:6080> (noVNC)Tail controller logs`wsl -d Ubuntu -u root docker compose -f auto-browser/docker-compose.yml logs -f controller`Full rebuild`wsl -d Ubuntu -u root docker compose -f auto-browser/docker-compose.yml up -d --build`

---

## MCP via Claude Desktop

Config already written to: `%APPDATA%\Claude\claude_desktop_config.json`

After restarting Claude Desktop, the `auto-browser` MCP server will appear in Claude's tool list. The bridge runs: `scripts/mcp_stdio_bridge.py`

---

## File Map

```
auto-browser/
├── controller/            FastAPI MCP controller (port 8000)
│   └── app/
│       └── mcp_stdio.py   MCP stdio entry point used by bridge
├── browser-node/          Playwright + noVNC container (port 6080/9223)
├── scripts/
│   └── mcp_stdio_bridge.py  Claude Desktop MCP stdio bridge
├── integrations/
│   ├── apexml_gateway.py  ← ApexML RBAC/metrics proxy router (THIS)
│   └── INTEGRATION.md     ← You are here
└── docker-compose.yml
```
