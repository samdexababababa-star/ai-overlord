"""Semantic memory backed by ChromaDB.

We store free-form facts, summaries, and reflective notes. The embedding model
is delegated to whichever provider is currently available; on retrieval we
embed the query the same way.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..config import settings
from ..log import get_logger
from ..providers import get_registry
from ..providers.base import Provider

log = get_logger(__name__)


class SemanticMemory:
    def __init__(self, collection: str = "facts"):
        self.collection_name = collection
        self._client = None
        self._coll = None

    def _ensure(self):
        if self._coll is not None:
            return
        try:
            import chromadb  # noqa: PLC0415

            self._client = chromadb.PersistentClient(path=str(settings.chroma_path))
            self._coll = self._client.get_or_create_collection(self.collection_name)
        except Exception as e:  # noqa: BLE001
            log.warning("semantic.init.fail", error=str(e))
            self._client = None
            self._coll = None

    async def _embed(self, texts: list[str]) -> list[list[float]] | None:
        """Pick whichever embedding-capable provider is available."""
        reg = get_registry()
        embed_candidates: list[tuple[Provider, str]] = []
        for p in reg.providers():
            for m in p.models:
                if "embed" in m.capabilities:
                    embed_candidates.append((p, m.id))
        for prov, model in embed_candidates:
            try:
                resp = await prov.embed(model, texts)
                return resp.vectors
            except Exception as e:  # noqa: BLE001
                log.warning("semantic.embed.try.fail", provider=prov.name, error=str(e)[:120])
                continue
        return None

    async def add(self, text: str, meta: dict[str, Any] | None = None) -> str | None:
        self._ensure()
        if self._coll is None:
            return None
        vectors = await self._embed([text])
        if not vectors:
            return None
        rid = uuid.uuid4().hex
        self._coll.add(
            ids=[rid],
            embeddings=vectors,
            documents=[text],
            metadatas=[{**(meta or {}), "ts": time.time()}],
        )
        return rid

    async def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        self._ensure()
        if self._coll is None:
            return []
        vectors = await self._embed([query])
        if not vectors:
            return []
        res = self._coll.query(query_embeddings=vectors, n_results=k)
        out: list[dict[str, Any]] = []
        for doc, meta, dist in zip(
            res.get("documents", [[]])[0],
            res.get("metadatas", [[]])[0],
            res.get("distances", [[]])[0],
            strict=False,
        ):
            out.append({"text": doc, "meta": meta, "distance": dist})
        return out
