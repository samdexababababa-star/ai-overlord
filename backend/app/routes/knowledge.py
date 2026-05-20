"""Knowledge graph API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..memory.knowledge_graph import KnowledgeGraph, extract_entities_and_relations
from ..providers import get_registry
from ..providers.router import ModelRouter

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_kg = KnowledgeGraph()


class AddEntityRequest(BaseModel):
    entity_id: str
    label: str
    entity_type: str = "concept"
    meta: dict[str, Any] | None = None


class AddRelationshipRequest(BaseModel):
    source: str
    target: str
    relation: str
    weight: float = 1.0
    meta: dict[str, Any] | None = None


class ExtractRequest(BaseModel):
    text: str


@router.get("/graph")
def get_graph() -> dict:
    return _kg.export_graph()


@router.get("/stats")
def graph_stats() -> dict:
    return _kg.stats()


@router.get("/entity/{entity_id}")
def get_entity(entity_id: str) -> dict:
    entity = _kg.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="entity not found")
    return {"id": entity_id, **entity}


@router.get("/neighbors/{entity_id}")
def get_neighbors(entity_id: str, depth: int = 1) -> dict:
    return _kg.get_neighbors(entity_id, max_depth=min(depth, 3))


@router.get("/search")
def search_entities(q: str, limit: int = 20) -> dict:
    return {"results": _kg.search(q, limit=min(limit, 100))}


@router.post("/entity")
def add_entity(req: AddEntityRequest) -> dict:
    _kg.add_entity(req.entity_id, req.label, req.entity_type, req.meta)
    return {"ok": True}


@router.post("/relationship")
def add_relationship(req: AddRelationshipRequest) -> dict:
    _kg.add_relationship(
        req.source, req.target, req.relation, req.weight, req.meta
    )
    return {"ok": True}


@router.post("/extract")
async def extract(req: ExtractRequest) -> dict:
    reg = get_registry()
    if not reg.has_any():
        raise HTTPException(status_code=412, detail="no providers configured")
    router_obj = ModelRouter(reg)
    entities, relations = await extract_entities_and_relations(
        req.text, router_obj
    )
    for e in entities:
        _kg.add_entity(
            e.get("id", e.get("label", "")),
            e.get("label", ""),
            e.get("type", "concept"),
        )
    for r in relations:
        _kg.add_relationship(
            r.get("source", ""),
            r.get("target", ""),
            r.get("relation", "related_to"),
        )
    return {"entities": entities, "relationships": relations}


@router.post("/consolidate")
def consolidate() -> dict:
    return _kg.consolidate()
