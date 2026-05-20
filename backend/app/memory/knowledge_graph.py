"""Knowledge graph — persistent entity-relationship store.

Built on NetworkX (in-memory graph) with JSON persistence. The LLM extracts
entities and relationships from text, building a growing knowledge base.

Capabilities:
- Entity extraction via LLM (named entities, concepts, facts)
- Relationship extraction (causal, temporal, semantic links)
- Graph queries (shortest path, neighbors, subgraph)
- Integration with the reasoning engine for fact lookup
- Periodic consolidation (merge duplicate entities, prune stale facts)

Inspired by:
- Knowledge Graph Embedding research (Bordes et al. 2013, TransE)
- GraphRAG (Microsoft 2024) — graph-based retrieval augmented generation
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..config import settings
from ..log import get_logger

log = get_logger(__name__)


class KnowledgeGraph:
    """In-memory knowledge graph backed by NetworkX with JSON persistence."""

    def __init__(self, path: Path | None = None):
        self.path = path or (settings.data_dir / "knowledge_graph.json")
        self._graph: dict[str, dict[str, Any]] = {}  # node_id -> attrs
        self._edges: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._graph = data.get("nodes", {})
                self._edges = data.get("edges", [])
                log.info(
                    "knowledge_graph.loaded",
                    nodes=len(self._graph),
                    edges=len(self._edges),
                )
            except Exception as e:
                log.warning("knowledge_graph.load_fail", error=str(e)[:200])

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"nodes": self._graph, "edges": self._edges}
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def add_entity(
        self,
        entity_id: str,
        label: str,
        entity_type: str = "concept",
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Add or update an entity node."""
        existing = self._graph.get(entity_id, {})
        self._graph[entity_id] = {
            **existing,
            "label": label,
            "type": entity_type,
            "updated_at": time.time(),
            **(meta or {}),
        }
        self._save()

    def add_relationship(
        self,
        source: str,
        target: str,
        relation: str,
        weight: float = 1.0,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Add a directed edge between two entities."""
        self._edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "weight": weight,
            "created_at": time.time(),
            **(meta or {}),
        })
        self._save()

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        return self._graph.get(entity_id)

    def get_neighbors(self, entity_id: str, max_depth: int = 1) -> dict[str, Any]:
        """Return entities connected to *entity_id* up to *max_depth* hops."""
        visited: set[str] = set()
        frontier = {entity_id}
        result_nodes: dict[str, dict[str, Any]] = {}
        result_edges: list[dict[str, Any]] = []

        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for node_id in frontier:
                if node_id in visited:
                    continue
                visited.add(node_id)
                if node_id in self._graph:
                    result_nodes[node_id] = self._graph[node_id]
                for edge in self._edges:
                    if edge["source"] == node_id:
                        result_edges.append(edge)
                        next_frontier.add(edge["target"])
                    elif edge["target"] == node_id:
                        result_edges.append(edge)
                        next_frontier.add(edge["source"])
            frontier = next_frontier - visited

        return {"nodes": result_nodes, "edges": result_edges}

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Simple text search across entity labels and types."""
        query_lower = query.lower()
        results = []
        for eid, attrs in self._graph.items():
            label = attrs.get("label", "").lower()
            etype = attrs.get("type", "").lower()
            if query_lower in label or query_lower in etype:
                results.append({"id": eid, **attrs})
            if len(results) >= limit:
                break
        return results

    def get_relationships(
        self, entity_id: str, direction: str = "both"
    ) -> list[dict[str, Any]]:
        """Get all edges involving *entity_id*."""
        result = []
        for edge in self._edges:
            if direction in ("both", "out") and edge["source"] == entity_id or direction in ("both", "in") and edge["target"] == entity_id:
                result.append(edge)
        return result

    def consolidate(self) -> dict[str, int]:
        """Merge duplicate entities and prune orphans."""
        label_map: dict[str, list[str]] = {}
        for eid, attrs in self._graph.items():
            label = attrs.get("label", "").lower().strip()
            if label:
                label_map.setdefault(label, []).append(eid)

        merged = 0
        for _label, ids in label_map.items():
            if len(ids) <= 1:
                continue
            primary = ids[0]
            for dup in ids[1:]:
                for edge in self._edges:
                    if edge["source"] == dup:
                        edge["source"] = primary
                    if edge["target"] == dup:
                        edge["target"] = primary
                del self._graph[dup]
                merged += 1

        # Remove self-loops
        self._edges = [
            e for e in self._edges if e["source"] != e["target"]
        ]

        # Remove orphan nodes (no edges)
        connected = set()
        for edge in self._edges:
            connected.add(edge["source"])
            connected.add(edge["target"])
        orphans = [
            eid for eid in self._graph if eid not in connected
        ]
        pruned = 0
        for eid in orphans:
            node = self._graph[eid]
            age = time.time() - node.get("updated_at", 0)
            if age > 86400 * 7:  # prune orphans older than a week
                del self._graph[eid]
                pruned += 1

        self._save()
        return {"merged": merged, "pruned": pruned}

    def stats(self) -> dict[str, int]:
        return {
            "total_nodes": len(self._graph),
            "total_edges": len(self._edges),
            "entity_types": len(
                {a.get("type", "") for a in self._graph.values()}
            ),
        }

    def export_graph(self) -> dict[str, Any]:
        """Export the full graph for visualization."""
        return {
            "nodes": [
                {"id": eid, **attrs}
                for eid, attrs in self._graph.items()
            ],
            "edges": self._edges,
        }


async def extract_entities_and_relations(
    text: str, router: Any
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Use an LLM to extract entities and relationships from text.

    Returns (entities, relationships) where each entity is
    {id, label, type} and each relationship is {source, target, relation}.
    """
    from ..providers.base import ChatMessage
    from ..providers.router import TaskProfile

    prompt = (
        "Extract named entities and relationships from this text.\n\n"
        f"Text: {text[:3000]}\n\n"
        "Return JSON with two arrays:\n"
        '{"entities": [{"id": "...", "label": "...", "type": "person|org|concept|place|event"}], '
        '"relationships": [{"source": "id1", "target": "id2", "relation": "verb or description"}]}\n\n'
        "Return ONLY valid JSON."
    )

    resp = await router.chat(
        [ChatMessage(role="user", content=prompt)],
        profile=TaskProfile(capability="reason"),
        temperature=0.1,
        max_tokens=1024,
    )

    try:
        raw = resp.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        entities = data.get("entities", [])
        relations = data.get("relationships", [])
        return entities, relations
    except (json.JSONDecodeError, KeyError):
        log.warning("knowledge_graph.extract_fail", text=resp.text[:200])
        return [], []
