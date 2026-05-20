"""Tool listing + manual invocation (for the UI's tools panel)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..tools import get_tools

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolCallRequest(BaseModel):
    name: str
    args: dict = {}


@router.get("")
def list_tools():
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "requires_confirmation": t.requires_confirmation,
            }
            for t in get_tools().all()
        ]
    }


@router.post("/call")
async def call_tool(req: ToolCallRequest):
    tool = get_tools().get(req.name)
    if not tool:
        raise HTTPException(status_code=404, detail="unknown tool")
    res = await tool.run(req.args)
    return res.model_dump()
