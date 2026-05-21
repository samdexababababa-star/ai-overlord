"""Site probing — figure out a page's prompt / send / response anchors.

The probe pulls a snapshot of *candidate* interactive elements from the page
(via Playwright's ``evaluate`` injecting a tiny JS DOM walker), scores each
candidate with deterministic heuristics inspired by Browser-Use / Skyvern,
and falls back to **Set-of-Marks** vision when no candidate clears the
confidence threshold (cf. WebVoyager, Yang et al. 2023).

The scoring layer is deliberately a *pure function* over plain JSON snapshots
of elements so that it can be unit-tested without a real browser.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field

from ..log import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Roles & data shapes
# ---------------------------------------------------------------------------


class ElementRole(enum.StrEnum):
    PROMPT_BOX = "prompt_box"
    SEND_BUTTON = "send_button"
    RESPONSE_ROOT = "response_root"
    COMPOSE_BOX = "compose_box"
    POST_BUTTON = "post_button"
    MEDIA_INPUT = "media_input"
    FEED_ITEM = "feed_item"


class RawElement(BaseModel):
    """JSON snapshot of one DOM element produced by the page walker."""

    selector: str
    tag: str
    role: str = ""
    aria_label: str = ""
    placeholder: str = ""
    name: str = ""
    text: str = ""
    type: str = ""
    classes: list[str] = Field(default_factory=list)
    data_testid: str = ""
    is_editable: bool = False
    is_visible: bool = True
    rect: dict[str, float] = Field(default_factory=dict)  # x, y, w, h
    children_text_len: int = 0


class ScoredElement(BaseModel):
    """A candidate element together with its computed score for a role."""

    role: ElementRole
    score: float
    selector: str
    element: RawElement


class ProbeResult(BaseModel):
    """Outcome of a probing pass."""

    picks: dict[str, ScoredElement] = Field(default_factory=dict)  # role -> best
    candidates: list[ScoredElement] = Field(default_factory=list)  # all scored
    confidence: float = 0.0
    needs_vision_fallback: bool = False
    snapshot_count: int = 0


# ---------------------------------------------------------------------------
# Heuristic scoring (pure function)
# ---------------------------------------------------------------------------


SEND_KEYWORDS = (
    "send", "submit", "envoyer", "post", "publier", "publish",
    "tweet", "share", "partager", "go", "ask",
)
COMPOSE_KEYWORDS = (
    "what's happening", "what is happening", "quoi de neuf", "start a post",
    "post", "publier", "tweet", "share an update", "compose",
    "create post", "say something", "create a post",
)
PROMPT_PLACEHOLDERS = (
    "ask anything", "message", "type", "send a message", "ask",
    "écrivez", "posez", "poser une question", "envoyez", "tape", "tapez",
    "ask claude", "ask perplexity", "demander", "talk to",
)
RESPONSE_KEYWORDS = (
    "assistant", "model-response", "ai-response", "result", "answer",
    "response", "prose", "markdown",
)
FEED_KEYWORDS = (
    "feed", "tweet", "post", "card", "story", "update", "activity-item",
)


def _has_keyword(haystack: str, needles: tuple[str, ...]) -> bool:
    h = haystack.lower()
    return any(n in h for n in needles)


def _rect_score(rect: dict[str, float], prefer_bottom: bool = True) -> float:
    """Big things near the bottom-middle of the viewport score higher."""
    w = float(rect.get("w", 0))
    h = float(rect.get("h", 0))
    y = float(rect.get("y", 0))
    if w <= 0 or h <= 0:
        return 0.0
    size = min(w * h, 250_000) / 250_000  # cap so giant elements don't dominate
    pos = min(y / 1200, 1.0) if prefer_bottom else max(0.0, 1.0 - y / 800)
    return 0.6 * size + 0.4 * pos


def score_prompt_box(el: RawElement) -> float:
    if not el.is_visible:
        return 0.0
    base = 0.0
    if el.tag == "textarea":
        base += 0.55
    elif el.is_editable:
        base += 0.5
    elif el.tag == "input" and el.type in ("text", "search", "url", ""):
        base += 0.2
    else:
        return 0.0
    if el.role in ("textbox",):
        base += 0.1
    if _has_keyword(el.placeholder + " " + el.aria_label, PROMPT_PLACEHOLDERS):
        base += 0.2
    if "prompt" in el.selector.lower() or "prompt" in " ".join(el.classes).lower():
        base += 0.1
    if el.data_testid and any(k in el.data_testid.lower() for k in ("prompt", "input", "compose", "textarea")):
        base += 0.1
    base += 0.3 * _rect_score(el.rect, prefer_bottom=True)
    return min(base, 1.0)


def score_send_button(el: RawElement) -> float:
    if not el.is_visible:
        return 0.0
    if el.tag not in ("button", "div", "span"):
        return 0.0
    base = 0.0
    if el.tag == "button":
        base += 0.45
    if el.role == "button":
        base += 0.1
    if _has_keyword(el.aria_label + " " + el.text + " " + el.name, SEND_KEYWORDS):
        base += 0.35
    if el.data_testid and any(k in el.data_testid.lower() for k in ("send", "submit", "tweet")):
        base += 0.2
    if el.type == "submit":
        base += 0.15
    base += 0.15 * _rect_score(el.rect, prefer_bottom=True)
    return min(base, 1.0)


def score_response_root(el: RawElement) -> float:
    if not el.is_visible:
        return 0.0
    base = 0.0
    role_or_class = el.role + " " + " ".join(el.classes) + " " + el.selector
    if _has_keyword(role_or_class, RESPONSE_KEYWORDS):
        base += 0.4
    if el.children_text_len > 80:
        base += 0.25
    if el.tag in ("article", "section", "div") and el.children_text_len > 40:
        base += 0.15
    if "message" in role_or_class.lower():
        base += 0.1
    if el.data_testid and "message" in el.data_testid.lower():
        base += 0.1
    return min(base, 1.0)


def score_compose_box(el: RawElement) -> float:
    if not el.is_visible:
        return 0.0
    base = 0.0
    if el.is_editable or el.tag == "textarea":
        base += 0.4
    if _has_keyword(el.placeholder + " " + el.aria_label, COMPOSE_KEYWORDS):
        base += 0.4
    if el.data_testid and "tweet" in el.data_testid.lower():
        base += 0.2
    if el.role == "textbox":
        base += 0.1
    base += 0.15 * _rect_score(el.rect, prefer_bottom=False)
    return min(base, 1.0)


def score_post_button(el: RawElement) -> float:
    if not el.is_visible or el.tag not in ("button", "div", "span"):
        return 0.0
    base = 0.0
    if el.tag == "button":
        base += 0.4
    if _has_keyword(el.aria_label + " " + el.text, ("post", "tweet", "share", "publish", "publier")):
        base += 0.45
    if el.data_testid and any(k in el.data_testid.lower() for k in ("post", "tweet", "share", "submit")):
        base += 0.25
    return min(base, 1.0)


def score_media_input(el: RawElement) -> float:
    if el.tag != "input" or el.type != "file":
        return 0.0
    base = 0.6
    if "image" in el.aria_label.lower() or "media" in el.aria_label.lower():
        base += 0.2
    if el.data_testid and "media" in el.data_testid.lower():
        base += 0.2
    return min(base, 1.0)


def score_feed_item(el: RawElement) -> float:
    role_or_class = (
        el.tag + " "
        + el.role + " "
        + " ".join(el.classes) + " "
        + el.selector + " "
        + el.data_testid
    )
    if not _has_keyword(role_or_class, FEED_KEYWORDS):
        return 0.0
    if el.children_text_len < 20:
        return 0.0
    base = 0.4
    if el.tag in ("article", "li"):
        base += 0.25
    if "data-testid" in el.selector and "tweet" in el.selector.lower():
        base += 0.25
    return min(base, 1.0)


SCORERS = {
    ElementRole.PROMPT_BOX: score_prompt_box,
    ElementRole.SEND_BUTTON: score_send_button,
    ElementRole.RESPONSE_ROOT: score_response_root,
    ElementRole.COMPOSE_BOX: score_compose_box,
    ElementRole.POST_BUTTON: score_post_button,
    ElementRole.MEDIA_INPUT: score_media_input,
    ElementRole.FEED_ITEM: score_feed_item,
}


def pick_best(
    elements: list[RawElement],
    role: ElementRole,
    min_score: float = 0.5,
) -> ScoredElement | None:
    scorer = SCORERS[role]
    best: ScoredElement | None = None
    for el in elements:
        s = scorer(el)
        if s >= min_score and (best is None or s > best.score):
            best = ScoredElement(role=role, score=s, selector=el.selector, element=el)
    return best


def score_all(elements: list[RawElement], roles: list[ElementRole]) -> ProbeResult:
    picks: dict[str, ScoredElement] = {}
    all_scored: list[ScoredElement] = []
    for role in roles:
        best = pick_best(elements, role, min_score=0.4)
        if best is not None:
            picks[role.value] = best
            all_scored.append(best)
    confidence = (
        sum(p.score for p in picks.values()) / len(picks)
        if picks else 0.0
    )
    return ProbeResult(
        picks=picks,
        candidates=all_scored,
        confidence=confidence,
        needs_vision_fallback=confidence < 0.6,
        snapshot_count=len(elements),
    )


# ---------------------------------------------------------------------------
# Page walker (Playwright JS injection) + Set-of-Marks
# ---------------------------------------------------------------------------


PAGE_WALKER_JS = r"""
() => {
  const items = [];
  const candidates = document.querySelectorAll(
    'textarea, input, button, [contenteditable="true"], [role="button"], [role="textbox"], '
    + 'article, section, [data-testid], [data-message-author-role]'
  );
  let idx = 0;
  const seen = new WeakSet();
  for (const el of candidates) {
    if (seen.has(el)) continue;
    seen.add(el);
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const visible = (
      style.visibility !== 'hidden'
      && style.display !== 'none'
      && rect.width > 0 && rect.height > 0
    );
    if (!visible && el.tagName !== 'INPUT') continue;

    // Build a stable selector: prefer data-testid, then id, then nth-of-type chain.
    let selector = '';
    if (el.dataset && el.dataset.testid) {
      selector = `[data-testid="${el.dataset.testid}"]`;
    } else if (el.id) {
      selector = `#${CSS.escape(el.id)}`;
    } else {
      // Best-effort: tag + class + nth-of-type
      const parts = [el.tagName.toLowerCase()];
      if (el.classList && el.classList.length) {
        parts.push('.' + Array.from(el.classList).slice(0, 2).map(CSS.escape).join('.'));
      }
      if (el.parentElement) {
        const siblings = Array.from(el.parentElement.children).filter(
          c => c.tagName === el.tagName
        );
        const i = siblings.indexOf(el);
        if (i >= 0) parts.push(`:nth-of-type(${i + 1})`);
      }
      selector = parts.join('');
    }

    const textContent = (el.innerText || el.textContent || '').slice(0, 300);
    items.push({
      selector,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      aria_label: el.getAttribute('aria-label') || '',
      placeholder: el.getAttribute('placeholder') || '',
      name: el.getAttribute('name') || '',
      text: textContent,
      type: (el.getAttribute('type') || '').toLowerCase(),
      classes: Array.from(el.classList || []),
      data_testid: (el.dataset && el.dataset.testid) || '',
      is_editable: el.getAttribute('contenteditable') === 'true',
      is_visible: visible,
      rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
      children_text_len: textContent.length,
    });

    idx++;
    if (idx > 200) break;  // hard cap
  }
  return items;
}
"""


SET_OF_MARKS_JS = r"""
(items) => {
  // items: [{selector, label}, …]; we draw badges at the bbox of each match.
  const layerId = '__overlord_som_layer__';
  document.getElementById(layerId)?.remove();
  const layer = document.createElement('div');
  layer.id = layerId;
  layer.style.cssText = (
    'position:fixed;inset:0;pointer-events:none;z-index:2147483647;'
    + 'font-family:monospace;font-weight:700;font-size:12px;'
  );
  let drawn = 0;
  for (const item of items) {
    let el = null;
    try { el = document.querySelector(item.selector); } catch (_) {}
    if (!el) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    const box = document.createElement('div');
    box.style.cssText = (
      'position:absolute;outline:2px solid #ff3aa1;border-radius:6px;'
      + `left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;`
    );
    const badge = document.createElement('div');
    badge.textContent = String(item.label);
    badge.style.cssText = (
      'position:absolute;left:-2px;top:-22px;background:#ff3aa1;color:#fff;'
      + 'padding:2px 6px;border-radius:4px;'
    );
    box.appendChild(badge);
    layer.appendChild(box);
    drawn++;
  }
  document.body.appendChild(layer);
  return drawn;
}
"""


CLEAR_MARKS_JS = (
    "() => { document.getElementById('__overlord_som_layer__')?.remove(); }"
)


class SiteProbe:
    """Runs the page walker + scoring against a live Playwright page.

    Parameters
    ----------
    roles : list[ElementRole]
        Which roles to discover. Defaults to the AI chat triplet.
    """

    AI_ROLES: list[ElementRole] = [
        ElementRole.PROMPT_BOX,
        ElementRole.SEND_BUTTON,
        ElementRole.RESPONSE_ROOT,
    ]
    SOCIAL_ROLES: list[ElementRole] = [
        ElementRole.COMPOSE_BOX,
        ElementRole.POST_BUTTON,
        ElementRole.MEDIA_INPUT,
        ElementRole.FEED_ITEM,
    ]

    def __init__(self, roles: list[ElementRole] | None = None):
        self.roles = roles or list(self.AI_ROLES)

    async def snapshot(self, page: Any) -> list[RawElement]:
        """Run the JS walker on a live Playwright Page."""
        raw = await page.evaluate(PAGE_WALKER_JS)
        return [RawElement(**r) for r in raw]

    def score_snapshot(self, elements: list[RawElement]) -> ProbeResult:
        return score_all(elements, self.roles)

    async def probe(self, page: Any) -> ProbeResult:
        elements = await self.snapshot(page)
        return self.score_snapshot(elements)

    async def draw_marks(self, page: Any, candidates: list[ScoredElement]) -> int:
        """Overlay numbered badges on candidates (returns how many were drawn)."""
        items = [
            {"selector": c.selector, "label": i + 1}
            for i, c in enumerate(candidates)
        ]
        return int(await page.evaluate(SET_OF_MARKS_JS, items))

    async def clear_marks(self, page: Any) -> None:
        await page.evaluate(CLEAR_MARKS_JS)
