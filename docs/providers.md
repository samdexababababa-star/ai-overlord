# Provider research notes

Snapshot of what each provider offers and how the app wires it up. Daily
limits and exact model IDs change frequently — verify in the provider's
console.

## Mistral

- Console: <https://console.mistral.ai/api-keys/>
- Auth: `Authorization: Bearer …`
- Endpoints: `POST /v1/chat/completions`, `POST /v1/embeddings`
- Wired models:
  - `mistral-large-latest` — flagship reasoning, 128 k ctx
  - `mistral-medium-latest` — strong reasoning
  - `mistral-small-latest` — fast
  - `ministral-8b-latest`, `ministral-3b-latest` — edge-class
  - `codestral-latest` — coding
  - `pixtral-large-latest` — vision
  - `mistral-embed` — embeddings (1024 d)

The free workspace grants a per-month token budget; spreading across multiple
keys (multiple workspaces) scales it linearly.

## NVIDIA NIM (build.nvidia.com)

- Console: <https://build.nvidia.com/>
- Auth: `Authorization: Bearer nvapi-…`
- Endpoints: OpenAI-compatible `POST /v1/chat/completions`, `POST /v1/embeddings`
- Wired models (subset of 80+):
  - `meta/llama-3.3-70b-instruct`
  - `nvidia/llama-3.1-nemotron-70b-instruct`
  - `nvidia/llama-3.1-nemotron-ultra-253b-v1`
  - `deepseek-ai/deepseek-r1`
  - `qwen/qwen2.5-72b-instruct`, `qwen/qwen2.5-coder-32b-instruct`
  - `meta/llama-3.2-90b-vision-instruct`
  - `microsoft/phi-3.5-vision-instruct`
  - `nvidia/llama-3.2-nv-embedqa-1b-v2`

Free monthly credit pool, shared across model catalog.

## Google AI Studio (Gemini / Gemma)

- Console: <https://aistudio.google.com/apikey>
- Auth: `?key=AIza…` query param
- Endpoints: `POST /v1beta/models/{model}:generateContent` (and `streamGenerateContent`)
- Wired models:
  - `gemini-2.5-pro`
  - `gemini-2.5-flash` — best price/perf
  - `gemini-2.5-flash-lite` — generous free quota (500 RPD)
  - `gemma-3-27b-it`
  - `text-embedding-004`

Free tier is per-key per-day; create multiple projects/keys for more headroom.

## Groq

- Console: <https://console.groq.com/keys>
- Auth: `Authorization: Bearer gsk_…`
- Endpoints: OpenAI-compatible
- Wired models:
  - `llama-3.3-70b-versatile`
  - `llama-3.1-8b-instant`
  - `meta-llama/llama-4-scout-17b-16e-instruct`
  - `qwen/qwen3-32b`

~800 tok/s on Llama 3.3 70B. Daily TPM caps; key rotation amortises.

## Extensibility

Adding another provider is a ~150 line task:

1. Create `backend/app/providers/<name>.py` subclassing :class:`Provider`.
2. Implement `chat`, `chat_stream`, optional `embed`, and `validate_key`.
3. Append it to `PROVIDER_CLASSES` in `providers/registry.py`.
4. Add metadata + onboarding steps to `routes/onboarding.py:PROVIDER_INFO`.

Candidate next providers: OpenRouter (free models), Cerebras, Together,
Anthropic if user has a paid key, Cloudflare Workers AI.
