/* Tiny fetch wrapper that resolves the backend URL via Electron's preload,
 * with a sensible localhost fallback for `vite dev` in a regular browser. */

let cachedBase: string | null = null;

export async function apiBase(): Promise<string> {
  if (cachedBase) return cachedBase;
  if (typeof window !== 'undefined' && window.overlord?.backendUrl) {
    cachedBase = await window.overlord.backendUrl();
  } else {
    cachedBase = 'http://127.0.0.1:8765';
  }
  return cachedBase;
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const base = await apiBase();
  return fetch(`${base}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
}

export async function apiJSON<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(path, init);
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status}: ${text.slice(0, 240)}`);
  }
  return r.json() as Promise<T>;
}

// ---- Domain helpers ----

export type ProviderInfo = {
  label: string;
  console: string;
  signup: string;
  steps: string[];
  tier_note: string;
  models: ProviderModel[];
};

export type ProviderModel = {
  id: string;
  provider: string;
  label: string;
  capabilities: string[];
  context_window: number;
  cost_tier: number;
  daily_request_limit?: number | null;
};

export type ConfiguredKeys = Record<string, { label: string; masked: string }[]>;

export type Health = {
  ok: boolean;
  providers: string[];
  has_keys: boolean;
};

export type AgentRole = {
  id: string;
  name: string;
  title: string;
  room: string;
  color: string;
  system_prompt: string;
};

export type AgentEvent = {
  id?: string;
  ts?: number;
  kind: string;
  actor: string;
  content?: string;
  meta?: Record<string, unknown>;
};

// ---- Web-AI Mesh ----

export type WebAISiteHealth = {
  status: 'unknown' | 'ok' | 'degraded' | 'broken' | 'needs_login';
  consecutive_failures: number;
  last_success_at: number;
  last_error: string;
};

export type WebAIAuth = {
  mode: string;
  needs_login: boolean;
  last_checked_at: number;
};

export type WebAISite = {
  id: string;
  label: string;
  url: string;
  host: string;
  category: 'ai' | 'social' | 'custom';
  include_in_council: boolean;
  health: WebAISiteHealth;
  auth: WebAIAuth;
  confidence: number;
  last_verified_at: number;
  is_ready: boolean;
  selectors?: Record<string, unknown>;
  submit?: Record<string, unknown>;
  stream_settle?: Record<string, unknown>;
  calibration?: Record<string, unknown>;
  notes?: string;
};

export type WebAIPreset = {
  id: string;
  label: string;
  url: string;
  category: 'ai' | 'social' | 'custom';
};

export type WebAILearnState = {
  profile_id: string;
  phase: 'opened' | 'awaiting_login' | 'probing' | 'calibrating' | 'ready' | 'failed';
  started_at: number;
  last_update_at: number;
  notes: string[];
  error: string;
  discovered_selectors: Record<string, string>;
  confidence: number;
};

export type WebAIAskResult = {
  ok: boolean;
  text: string;
  elapsed_ms: number;
  retries: number;
  selector_repaired: boolean;
  error: string;
};
