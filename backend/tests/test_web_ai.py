"""Tests for the Web-AI Mesh subsystem.

These tests stay self-contained: no real browser, no real LLM. Each layer
is exercised in isolation with small fakes for the page object.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from backend.app.web_ai import probe as probe_mod
from backend.app.web_ai.auto_learner import LearnPhase, SiteAutoLearner
from backend.app.web_ai.client import WebAIClient
from backend.app.web_ai.probe import ElementRole, RawElement, ScoredElement, SiteProbe
from backend.app.web_ai.profiles import (
    ProfileHealth,
    ProfileStore,
    SiteCategory,
    SiteProfile,
    slugify,
)
from backend.app.web_ai.provider import (
    WebAIProvider,
    model_id_for_profile,
    profile_id_for_model,
)
from backend.app.web_ai.social import PostRequest, SocialAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakePage:
    """Minimal Playwright Page substitute for tests."""

    def __init__(self, response_text: str = "Hello back", url: str = "https://example.com/"):
        self.response_text = response_text
        self._url = url
        self.keys_pressed: list[str] = []
        self.calls: list[str] = []
        self.clicked: list[str] = []
        self.typed: dict[str, str] = {}

    async def goto(self, url: str, **kwargs: Any) -> Any:
        self.calls.append(f"goto:{url}")
        self._url = url

    async def evaluate(self, script: str, *args: Any) -> Any:  # noqa: D401
        # Match the snippets used by WebAIClient._focus / _type / _read_response.
        self.calls.append("evaluate")
        # Disambiguate by arg shape: _type passes a dict, _focus + _read_response
        # pass a positional string selector.
        if args and isinstance(args[0], dict) and "text" in args[0]:
            self.typed[args[0].get("sel", "?")] = args[0].get("text", "")
            return True
        if "innerText || el.textContent" in script:
            return self.response_text
        if "focus()" in script and "querySelector(sel)" in script:
            return True
        if "innerText" in script and "querySelector(sel)" in script:
            return self.response_text
        return None

    async def fill(self, selector: str, value: str, **kwargs: Any) -> None:
        self.typed[selector] = value

    async def click(self, selector: str, **kwargs: Any) -> None:
        self.clicked.append(selector)

    async def keyboard_press(self, key: str) -> None:
        self.keys_pressed.append(key)

    def url(self) -> str:
        return self._url

    async def set_input_files(self, selector: str, paths: list[str]) -> None:
        self.typed[f"files:{selector}"] = ",".join(paths)


@pytest.fixture
def tmp_store(tmp_path: Path) -> ProfileStore:
    return ProfileStore(root=tmp_path / "profiles")


# ---------------------------------------------------------------------------
# Heuristic scoring
# ---------------------------------------------------------------------------


def test_score_prompt_box_textarea_with_placeholder():
    el = RawElement(
        selector="textarea#prompt-textarea",
        tag="textarea",
        placeholder="Send a message",
        rect={"x": 100, "y": 800, "w": 600, "h": 80},
    )
    assert probe_mod.score_prompt_box(el) > 0.7


def test_score_prompt_box_rejects_hidden_input():
    el = RawElement(
        selector="input[type=hidden]",
        tag="input",
        type="hidden",
        is_visible=False,
    )
    assert probe_mod.score_prompt_box(el) == 0.0


def test_score_send_button_recognises_data_testid():
    el = RawElement(
        selector="[data-testid=tweetButton]",
        tag="button",
        data_testid="tweetButton",
        text="Tweet",
        rect={"x": 600, "y": 700, "w": 80, "h": 40},
    )
    assert probe_mod.score_send_button(el) > 0.7


def test_score_response_root_long_assistant_block():
    el = RawElement(
        selector="div[data-message-author-role=assistant]",
        tag="div",
        classes=["model-response", "markdown"],
        children_text_len=600,
        data_testid="message",
    )
    assert probe_mod.score_response_root(el) > 0.6


def test_score_all_picks_best_per_role():
    elements = [
        RawElement(
            selector="textarea",
            tag="textarea",
            placeholder="Send a message",
            rect={"x": 0, "y": 500, "w": 400, "h": 80},
        ),
        RawElement(
            selector="button[data-testid=send-button]",
            tag="button",
            data_testid="send-button",
            text="Send",
            rect={"x": 410, "y": 500, "w": 60, "h": 40},
        ),
        RawElement(
            selector="div[data-message-author-role=assistant]",
            tag="div",
            classes=["markdown"],
            children_text_len=200,
            data_testid="message",
        ),
    ]
    result = probe_mod.score_all(elements, list(SiteProbe.AI_ROLES))
    assert "prompt_box" in result.picks
    assert "send_button" in result.picks
    assert "response_root" in result.picks
    assert result.confidence > 0.4


# ---------------------------------------------------------------------------
# Profile store
# ---------------------------------------------------------------------------


def test_profile_store_round_trip(tmp_store: ProfileStore):
    profile = tmp_store.upsert_from_url(
        url="https://example.com/", label="Example", category=SiteCategory.AI,
    )
    assert profile.id == "example"
    assert profile.host == "example.com"

    profile.selectors.prompt_box = "#x"
    profile.selectors.response_root = "#y"
    profile.health.status = ProfileHealth.OK
    tmp_store.save(profile)

    other = ProfileStore(root=tmp_store.root)
    fetched = other.get("example")
    assert fetched is not None
    assert fetched.selectors.prompt_box == "#x"
    assert fetched.is_ready()


def test_profile_store_delete(tmp_store: ProfileStore):
    p = tmp_store.upsert_from_url(url="https://a.test/", label="A")
    assert tmp_store.get(p.id) is not None
    assert tmp_store.delete(p.id) is True
    assert tmp_store.get(p.id) is None


def test_slugify_handles_uppercase_and_url():
    assert slugify("https://chat.openai.com/") == "chat-openai-com"
    assert slugify("Hello World!") == "hello-world"


def test_mark_failure_eventually_marks_broken(tmp_store: ProfileStore):
    p = tmp_store.upsert_from_url(url="https://a.test/", label="A")
    for _ in range(3):
        tmp_store.mark_failure(p.id, "boom")
    p2 = tmp_store.get(p.id)
    assert p2 is not None
    assert p2.health.status == ProfileHealth.BROKEN


# ---------------------------------------------------------------------------
# WebAIClient state machine
# ---------------------------------------------------------------------------


def _ready_profile(store: ProfileStore) -> SiteProfile:
    profile = store.upsert_from_url(url="https://example.com/chat", label="Example")
    profile.selectors.prompt_box = "#prompt"
    profile.selectors.send_button = "#send"
    profile.selectors.response_root = "#resp"
    profile.stream_settle.poll_ms = 1  # speed up tests
    profile.stream_settle.stable_cycles = 2
    profile.stream_settle.max_ms = 200
    profile.health.status = ProfileHealth.OK
    store.save(profile)
    return profile


@pytest.mark.asyncio
async def test_client_drive_page_happy_path(tmp_store: ProfileStore):
    profile = _ready_profile(tmp_store)
    page = FakePage(response_text="42")
    client = WebAIClient(profile=profile, store=tmp_store)
    result = await client.drive_page(page, "What is the answer?")
    assert result.ok
    assert result.text == "42"
    assert page.typed["#prompt"] == "What is the answer?"
    assert page.keys_pressed == ["Enter"]


@pytest.mark.asyncio
async def test_client_drive_page_no_selector(tmp_store: ProfileStore):
    profile = tmp_store.upsert_from_url(url="https://example.com/", label="No-selectors")
    page = FakePage()
    client = WebAIClient(profile=profile, store=tmp_store)
    result = await client.drive_page(page, "Hi")
    assert not result.ok
    assert "prompt_box" in result.error


# ---------------------------------------------------------------------------
# WebAIProvider model catalog
# ---------------------------------------------------------------------------


def test_provider_only_lists_ready_ai_profiles(tmp_store: ProfileStore):
    not_ready = tmp_store.upsert_from_url(url="https://nr.test/", label="NotReady")
    assert not_ready.is_ready() is False

    ready = tmp_store.upsert_from_url(url="https://r.test/", label="Ready")
    ready.selectors.prompt_box = "#p"
    ready.selectors.response_root = "#r"
    ready.health.status = ProfileHealth.OK
    tmp_store.save(ready)

    social = tmp_store.upsert_from_url(
        url="https://s.test/", label="Social", category=SiteCategory.SOCIAL,
    )
    social.selectors.compose_box = "#c"
    social.selectors.post_button = "#post"
    social.selectors.response_root = "#noop"
    social.selectors.prompt_box = "#noop2"
    social.health.status = ProfileHealth.OK
    tmp_store.save(social)

    provider = WebAIProvider(store=tmp_store)
    model_ids = [m.id for m in provider.models]
    assert model_id_for_profile("ready") in model_ids
    assert model_id_for_profile("notready") not in model_ids
    assert model_id_for_profile("social") not in model_ids


def test_provider_model_id_round_trip():
    assert profile_id_for_model(model_id_for_profile("gemini-web")) == "gemini-web"
    assert profile_id_for_model("groq:llama") is None


def test_provider_flatten_messages_collapses_roles():
    class M:  # noqa: D401
        def __init__(self, role: str, content: str):
            self.role = role
            self.content = content

    text = WebAIProvider._flatten_messages([
        M("system", "be terse"),
        M("user", "hello"),
        M("assistant", "world"),
        M("tool", "details" * 200),
    ])
    assert "[Context]" in text
    assert "[User]" in text
    assert "[Previously you said]" in text
    assert "[Tool output]" in text


# ---------------------------------------------------------------------------
# Auto-learner state machine
# ---------------------------------------------------------------------------


class FakeProbe(SiteProbe):
    def __init__(self, picks_confidence: float = 0.8):
        super().__init__()
        self._picks_confidence = picks_confidence

    async def probe(self, page: Any) -> probe_mod.ProbeResult:  # type: ignore[override]
        return probe_mod.ProbeResult(
            picks={
                "prompt_box": ScoredElement(
                    role=ElementRole.PROMPT_BOX, score=0.9, selector="#p",
                    element=RawElement(selector="#p", tag="textarea"),
                ),
                "response_root": ScoredElement(
                    role=ElementRole.RESPONSE_ROOT, score=0.8, selector="#r",
                    element=RawElement(selector="#r", tag="div"),
                ),
            },
            candidates=[],
            confidence=self._picks_confidence,
            snapshot_count=2,
        )


class LoginPage(FakePage):
    async def evaluate(self, script: str, *args: Any) -> Any:
        if "input[type=password]" in script:
            return True
        if "document.body" in script and "innerText" in script:
            return "Please sign in to continue with Google"
        return await super().evaluate(script, *args)


class FreshPage(FakePage):
    async def evaluate(self, script: str, *args: Any) -> Any:
        if "input[type=password]" in script:
            return False
        if "document.body" in script and "innerText" in script:
            return "welcome back!"
        return await super().evaluate(script, *args)


@pytest.mark.asyncio
async def test_auto_learner_awaits_login_when_password_field_present(tmp_store: ProfileStore):
    profile = tmp_store.upsert_from_url(url="https://x.test/", label="X")
    learner = SiteAutoLearner(profile=profile, store=tmp_store, probe=FakeProbe())
    state = await learner.learn(LoginPage())
    assert state.phase == LearnPhase.AWAITING_LOGIN
    refreshed = tmp_store.get(profile.id)
    assert refreshed is not None
    assert refreshed.health.status == ProfileHealth.NEEDS_LOGIN


@pytest.mark.asyncio
async def test_auto_learner_reaches_ready(tmp_store: ProfileStore):
    profile = tmp_store.upsert_from_url(url="https://y.test/", label="Y")
    learner = SiteAutoLearner(profile=profile, store=tmp_store, probe=FakeProbe())
    state = await learner.learn(FreshPage())
    assert state.phase == LearnPhase.READY
    refreshed = tmp_store.get(profile.id)
    assert refreshed is not None
    assert refreshed.selectors.prompt_box == "#p"
    assert refreshed.selectors.response_root == "#r"
    assert refreshed.health.status == ProfileHealth.OK


# ---------------------------------------------------------------------------
# Social adapter
# ---------------------------------------------------------------------------


class SocialFakePage(FakePage):
    def __init__(self):
        super().__init__()
        self.feed_rows = [
            {"text": "hello world", "author": "@a", "timestamp": "2024-01-01"},
            {"text": "another", "author": "@b", "timestamp": ""},
        ]

    async def evaluate(self, script: str, *args: Any) -> Any:
        if "querySelectorAll(sel)" in script and "feed" in script.lower() or "innerText || e.textContent" in script:
            return self.feed_rows
        if "querySelectorAll(sel)" in script:
            return self.feed_rows
        return await super().evaluate(script, *args)


@pytest.mark.asyncio
async def test_social_read_feed_parses_rows(tmp_store: ProfileStore):
    profile = tmp_store.upsert_from_url(
        url="https://x.com/home", label="X", category=SiteCategory.SOCIAL,
    )
    profile.selectors.feed_item = "article[data-testid=tweet]"
    tmp_store.save(profile)
    adapter = SocialAdapter(profile=profile, store=tmp_store)
    page = SocialFakePage()
    result = await adapter.read_feed(page, limit=10)
    assert len(result.items) == 2
    assert result.items[0].text == "hello world"


@pytest.mark.asyncio
async def test_social_execute_post_uses_compose_box(tmp_store: ProfileStore):
    profile = tmp_store.upsert_from_url(
        url="https://x.com/home", label="X", category=SiteCategory.SOCIAL,
    )
    profile.selectors.compose_box = "#compose"
    profile.selectors.post_button = "#post"
    tmp_store.save(profile)
    adapter = SocialAdapter(profile=profile, store=tmp_store)
    page = SocialFakePage()
    result = await adapter.execute_post(page, PostRequest(text="hello"))
    assert result.ok
    assert "#post" in page.clicked
