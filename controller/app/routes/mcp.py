from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..models import McpToolCallRequest


def create_mcp_router(*, mcp_transport: Any, tool_gateway: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/mcp")
    async def get_mcp_transport(request: Request):
        return await mcp_transport.handle_get_request(request)

    @router.post("/mcp")
    async def post_mcp_transport(request: Request):
        return await mcp_transport.handle_post_request(request)

    @router.delete("/mcp")
    async def delete_mcp_transport(request: Request):
        return await mcp_transport.handle_delete_request(request)

    @router.get("/mcp/tools")
    async def list_mcp_tools() -> list[dict[str, Any]]:
        return tool_gateway.list_tools()

    @router.post("/mcp/tools/call")
    async def call_mcp_tool(payload: McpToolCallRequest) -> dict[str, Any]:
        return (await tool_gateway.call_tool(payload)).model_dump(exclude_none=True, by_alias=True)

    return router
