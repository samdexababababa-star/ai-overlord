import { create } from 'zustand';
import { apiFetch, apiJSON, type AgentEvent, type AgentRole, type ConfiguredKeys, type Health, type ProviderInfo, type ProviderModel } from '../api';

type ChatTurn = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  meta?: Record<string, unknown>;
};

type State = {
  // Provisioning
  health: Health | null;
  providers: Record<string, ProviderInfo>;
  configuredKeys: ConfiguredKeys;
  models: ProviderModel[];
  roles: AgentRole[];

  // Chat
  turns: ChatTurn[];
  pending: boolean;

  // Events (council trace)
  events: AgentEvent[];
  eventsConnected: boolean;

  // UI
  showOnboarding: boolean;
  view: 'chat' | 'office' | 'memory' | 'tools' | 'settings';

  // Actions
  init: () => Promise<void>;
  loadProviders: () => Promise<void>;
  loadKeys: () => Promise<void>;
  loadModels: () => Promise<void>;
  loadRoles: () => Promise<void>;
  validateKey: (provider: string, value: string) => Promise<boolean>;
  addKey: (provider: string, label: string, value: string) => Promise<void>;
  removeKey: (provider: string, label: string) => Promise<void>;
  reloadKeys: () => Promise<void>;
  setView: (v: State['view']) => void;
  setShowOnboarding: (b: boolean) => void;
  ask: (msg: string) => Promise<void>;
  runObjective: (obj: string) => Promise<void>;
  connectEvents: () => void;
};

export const useStore = create<State>((set, get) => ({
  health: null,
  providers: {},
  configuredKeys: {},
  models: [],
  roles: [],
  turns: [],
  pending: false,
  events: [],
  eventsConnected: false,
  showOnboarding: false,
  view: 'chat',

  async init() {
    try {
      const health = await apiJSON<Health>('/health');
      set({ health });
      await Promise.all([get().loadProviders(), get().loadKeys(), get().loadModels(), get().loadRoles()]);
      if (!health.has_keys) set({ showOnboarding: true });
      get().connectEvents();
    } catch (e) {
      console.error('init failed', e);
    }
  },

  async loadProviders() {
    const providers = await apiJSON<Record<string, ProviderInfo>>('/onboarding/providers');
    set({ providers });
  },

  async loadKeys() {
    const configuredKeys = await apiJSON<ConfiguredKeys>('/onboarding/keys');
    set({ configuredKeys });
  },

  async loadModels() {
    const data = await apiJSON<{ models: ProviderModel[]; providers: string[] }>('/agents/models');
    set({ models: data.models });
  },

  async loadRoles() {
    const data = await apiJSON<{ roles: AgentRole[] }>('/agents/roles');
    set({ roles: data.roles });
  },

  async validateKey(provider, value) {
    const r = await apiJSON<{ ok: boolean }>('/onboarding/keys/validate', {
      method: 'POST',
      body: JSON.stringify({ provider, value }),
    });
    return r.ok;
  },

  async addKey(provider, label, value) {
    await apiJSON('/onboarding/keys', {
      method: 'POST',
      body: JSON.stringify({ provider, label, value }),
    });
    await get().loadKeys();
    await get().loadModels();
    const health = await apiJSON<Health>('/health');
    set({ health });
  },

  async removeKey(provider, label) {
    await apiFetch('/onboarding/keys', {
      method: 'DELETE',
      body: JSON.stringify({ provider, label }),
    });
    await get().loadKeys();
    await get().loadModels();
  },

  async reloadKeys() {
    await apiJSON('/onboarding/reload', { method: 'POST' });
    await get().loadKeys();
    await get().loadModels();
  },

  setView(v) { set({ view: v }); },
  setShowOnboarding(b) { set({ showOnboarding: b }); },

  async ask(msg) {
    const userTurn: ChatTurn = { id: crypto.randomUUID(), role: 'user', content: msg };
    set((s) => ({ turns: [...s.turns, userTurn], pending: true }));
    try {
      const r = await apiJSON<{ text: string }>('/chat/ask', {
        method: 'POST',
        body: JSON.stringify({ message: msg }),
      });
      const a: ChatTurn = { id: crypto.randomUUID(), role: 'assistant', content: r.text };
      set((s) => ({ turns: [...s.turns, a], pending: false }));
    } catch (e) {
      set((s) => ({
        turns: [...s.turns, { id: crypto.randomUUID(), role: 'assistant', content: `Error: ${(e as Error).message}` }],
        pending: false,
      }));
    }
  },

  async runObjective(obj) {
    const userTurn: ChatTurn = { id: crypto.randomUUID(), role: 'user', content: `[council] ${obj}` };
    set((s) => ({ turns: [...s.turns, userTurn], pending: true }));
    try {
      const r = await apiJSON<{ final: string; plan: string; critique: string; verdict: string }>(
        '/chat/run',
        { method: 'POST', body: JSON.stringify({ objective: obj }) },
      );
      const a: ChatTurn = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: r.final,
        meta: { plan: r.plan, critique: r.critique, verdict: r.verdict },
      };
      set((s) => ({ turns: [...s.turns, a], pending: false }));
    } catch (e) {
      set((s) => ({
        turns: [...s.turns, { id: crypto.randomUUID(), role: 'assistant', content: `Error: ${(e as Error).message}` }],
        pending: false,
      }));
    }
  },

  connectEvents() {
    if (get().eventsConnected) return;
    // Wrap the WS in async so we can resolve the base URL first.
    (async () => {
      try {
        let base = (typeof window !== 'undefined' && window.overlord?.backendUrl)
          ? await window.overlord.backendUrl()
          : 'http://127.0.0.1:8765';
        const wsUrl = base.replace(/^http/, 'ws') + '/agents/events';
        const ws = new WebSocket(wsUrl);
        ws.onopen = () => set({ eventsConnected: true });
        ws.onmessage = (e) => {
          try {
            const ev: AgentEvent = JSON.parse(e.data);
            if (ev.content === 'ping') return;
            set((s) => ({ events: [...s.events.slice(-499), ev] }));
          } catch { /* ignore parse errors */ }
        };
        ws.onclose = () => {
          set({ eventsConnected: false });
          setTimeout(() => get().connectEvents(), 2000);
        };
        ws.onerror = () => ws.close();
      } catch (e) {
        console.warn('events connect failed', e);
        setTimeout(() => get().connectEvents(), 3000);
      }
    })();
  },
}));
