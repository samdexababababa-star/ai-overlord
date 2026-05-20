"""Memory inspection / search endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..memory import EpisodicMemory, SemanticMemory

router = APIRouter(prefix="/memory", tags=["memory"])

_episodic = EpisodicMemory()
_semantic = SemanticMemory()


class MemoryAdd(BaseModel):
    text: str
    tags: list[str] = []


@router.get("/episodic")
def episodic(session: str = "default", limit: int = 100, kind: str | None = None):
    kinds = [kind] if kind else None
    return {"items": _episodic.recent(session=session, limit=limit, kinds=kinds)}


@router.get("/episodic/search")
def episodic_search(q: str, limit: int = 20):
    return {"items": _episodic.search(q, limit=limit)}


@router.post("/semantic/add")
async def semantic_add(req: MemoryAdd):
    rid = await _semantic.add(req.text, meta={"tags": req.tags})
    return {"ok": rid is not None, "id": rid}


@router.get("/semantic/search")
async def semantic_search(q: str, k: int = 5):
    return {"items": await _semantic.search(q, k=k)}
