"""Preset hints for popular AI and social sites.

These are *starting* configurations only — the probe will refine them. We
keep selectors deliberately loose (role-based, ARIA-based) so they keep
working through UI churn.

References to public docs / source layouts:
- ChatGPT: ``main form textarea`` + send button with ``data-testid``.
- Gemini: ``rich-textarea div[contenteditable]`` + send button aria-label.
- Claude: ``ProseMirror`` editor + ``button[aria-label="Send Message"]``.
- Mistral Le Chat: similar contenteditable pattern.
- X/Twitter: ``[data-testid=tweetTextarea_0]`` + ``[data-testid=tweetButton]``.
- LinkedIn: ``[data-test-share-form__main-text-input]`` + share post button.
- Reddit (new): ``[data-testid=post-content]`` textarea + post button.

These hints are only used as a head start; the actual values written to the
profile come from the probe, so updates upstream don't require code changes.
"""

from __future__ import annotations

from pydantic import BaseModel

from .profiles import (
    AuthState,
    CalibrationSpec,
    Selectors,
    SiteCategory,
    SiteProfile,
    StreamSettleConfig,
    SubmitConfig,
)


class Preset(BaseModel):
    id: str
    label: str
    url: str
    category: SiteCategory
    selectors: Selectors
    submit: SubmitConfig = SubmitConfig()
    stream_settle: StreamSettleConfig = StreamSettleConfig()
    auth: AuthState = AuthState()
    calibration: CalibrationSpec = CalibrationSpec()
    notes: str = ""


PRESETS: list[Preset] = [
    Preset(
        id="chatgpt-web",
        label="ChatGPT Web",
        url="https://chatgpt.com/",
        category=SiteCategory.AI,
        selectors=Selectors(
            prompt_box="textarea#prompt-textarea, div#prompt-textarea[contenteditable='true']",
            send_button="button[data-testid='send-button']",
            response_root="div[data-message-author-role='assistant']:last-of-type",
            confidence=0.7,
        ),
    ),
    Preset(
        id="gemini-web",
        label="Gemini",
        url="https://gemini.google.com/app",
        category=SiteCategory.AI,
        selectors=Selectors(
            prompt_box="rich-textarea div[contenteditable='true']",
            send_button="button[aria-label*='Send' i], button[aria-label*='Envoyer' i]",
            response_root="model-response:last-of-type, message-content:last-of-type",
            confidence=0.7,
        ),
    ),
    Preset(
        id="claude-web",
        label="Claude",
        url="https://claude.ai/new",
        category=SiteCategory.AI,
        selectors=Selectors(
            prompt_box="div.ProseMirror[contenteditable='true']",
            send_button="button[aria-label='Send Message'], button[aria-label='Envoyer']",
            response_root="div[data-test-render-count]:last-of-type",
            confidence=0.7,
        ),
    ),
    Preset(
        id="lechat-mistral",
        label="Le Chat (Mistral)",
        url="https://chat.mistral.ai/chat",
        category=SiteCategory.AI,
        selectors=Selectors(
            prompt_box="div[contenteditable='true'][role='textbox']",
            send_button="button[type='submit']",
            response_root="article[data-role='assistant']:last-of-type",
            confidence=0.6,
        ),
    ),
    Preset(
        id="perplexity-web",
        label="Perplexity",
        url="https://www.perplexity.ai/",
        category=SiteCategory.AI,
        selectors=Selectors(
            prompt_box="textarea[placeholder*='Ask' i], div[contenteditable='true']",
            send_button="button[aria-label*='Submit' i]",
            response_root="div[class*='prose']:last-of-type",
            confidence=0.6,
        ),
    ),
    Preset(
        id="x-twitter",
        label="X (Twitter)",
        url="https://x.com/home",
        category=SiteCategory.SOCIAL,
        selectors=Selectors(
            compose_box="[data-testid='tweetTextarea_0']",
            post_button="[data-testid='tweetButton'], [data-testid='tweetButtonInline']",
            media_input="[data-testid='fileInput']",
            feed_item="article[data-testid='tweet']",
            confidence=0.7,
        ),
    ),
    Preset(
        id="linkedin-feed",
        label="LinkedIn",
        url="https://www.linkedin.com/feed/",
        category=SiteCategory.SOCIAL,
        selectors=Selectors(
            compose_box="div.ql-editor[contenteditable='true']",
            post_button="button.share-actions__primary-action",
            media_input="input[type='file'][accept*='image']",
            feed_item="div.feed-shared-update-v2",
            confidence=0.6,
        ),
    ),
    Preset(
        id="reddit-home",
        label="Reddit",
        url="https://www.reddit.com/submit",
        category=SiteCategory.SOCIAL,
        selectors=Selectors(
            compose_box="textarea[name='title'], textarea[placeholder*='title' i]",
            post_button="button[type='submit']",
            feed_item="shreddit-post, [data-testid='post-container']",
            confidence=0.5,
        ),
    ),
]


PRESETS_BY_ID: dict[str, Preset] = {p.id: p for p in PRESETS}


def apply_preset(profile: SiteProfile, preset: Preset) -> SiteProfile:
    """Merge a preset's hints into a (probably empty) profile."""
    profile.label = profile.label or preset.label
    profile.url = profile.url or preset.url
    profile.category = preset.category
    # Only fill blanks; never overwrite something the probe has learned.
    if not profile.selectors.prompt_box:
        profile.selectors.prompt_box = preset.selectors.prompt_box
    if not profile.selectors.send_button:
        profile.selectors.send_button = preset.selectors.send_button
    if not profile.selectors.response_root:
        profile.selectors.response_root = preset.selectors.response_root
    if not profile.selectors.feed_item:
        profile.selectors.feed_item = preset.selectors.feed_item
    if not profile.selectors.compose_box:
        profile.selectors.compose_box = preset.selectors.compose_box
    if not profile.selectors.post_button:
        profile.selectors.post_button = preset.selectors.post_button
    if not profile.selectors.media_input:
        profile.selectors.media_input = preset.selectors.media_input
    profile.selectors.confidence = max(profile.selectors.confidence, preset.selectors.confidence)
    profile.submit = preset.submit
    profile.stream_settle = preset.stream_settle
    profile.calibration = preset.calibration
    return profile
