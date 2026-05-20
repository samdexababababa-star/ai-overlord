"""Chat & council endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agents import Council
from ..memory import EpisodicMemory
from ..providers import ChatMessage, get_registry
from ..providers.router import ModelRouter, TaskProfile

router = APIRouter(tags=["chat"])

_council = Council()
_episodic = EpisodicMemory()


class AskRequest(BaseModel):
    message: str
    session: str = "default"


class RunRequest(BaseModel):
    objective: str
    session: str = "default"


class StreamRequest(BaseModel):
    message: str
    capability: str = "chat"
    session: str = "default"


@router.post("/chat/ask")
async def ask(req: AskRequest) -> dict:
    if not get_registry().has_any():
        raise HTTPException(status_code=412, detail="no providers configured; complete onboarding")
    text = await _council.ask(req.message, session=req.session)
    return {"text": text}


@router.post("/chat/run")
async def run_objective(req: RunRequest) -> dict:
    if not get_registry().has_any():
        raise HTTPException(status_code=412, detail="no providers configured; complete onboarding")
    result = await _council.run_objective(req.objective, session=req.session)
    return result


@router.post("/chat/stream")
async def chat_stream(req: StreamRequest):
    if not get_registry().has_any():
        raise HTTPException(status_code=412, detail="no providers configured; complete onboarding")
    router_obj = ModelRouter(get_registry())
    pick = router_obj.pick(TaskProfile(capability=req.capability))  # type: ignore[arg-type]
    if not pick:
        raise HTTPException(status_code=412, detail="no model available for capability")
    provider, model = pick

    async def gen():
        from ..providers.base import ChatRequest

        creq = ChatRequest(
            model=model.id,
            messages=[
                ChatMessage(
                    role="system",
                    content="You are AI Overlord. Be concise. Match user's language.",
                ),
                ChatMessage(role="user", content=req.message),
            ],
            stream=True,
        )
        try:
            async for piece in provider.chat_stream(creq):
                yield piece
        except Exception as e:  # noqa: BLE001
            yield f"\n[error: {e}]"

    return StreamingResponse(gen(), media_type="text/plain")


@router.get("/chat/history")
def history(session: str = "default", limit: int = 50) -> dict:
    eps = _episodic.recent(session=session, limit=limit, kinds=["user_msg", "assistant_msg"])
    return {"items": eps}
