import { useEffect, useMemo, useState } from 'react';
import { Network, Sparkles, Trash2, RefreshCw, ChevronRight, Send } from 'lucide-react';
import clsx from 'clsx';
import { useStore } from '../store';
import type { WebAISite } from '../api';

const HEALTH_PILL: Record<WebAISite['health']['status'], string> = {
  ok: 'bg-emerald-500/20 text-emerald-300',
  degraded: 'bg-amber-500/20 text-amber-200',
  broken: 'bg-rose-500/20 text-rose-200',
  needs_login: 'bg-violet-500/20 text-violet-200',
  unknown: 'bg-white/10 text-ink-200',
};

const CATEGORY_PILL: Record<WebAISite['category'], string> = {
  ai: 'bg-sky-500/15 text-sky-200',
  social: 'bg-pink-500/15 text-pink-200',
  custom: 'bg-white/10 text-ink-200',
};

const PHASE_TEXT: Record<string, string> = {
  opened: 'Page opened',
  awaiting_login: 'Awaiting login',
  probing: 'Probing DOM',
  calibrating: 'Calibrating',
  ready: 'Ready',
  failed: 'Failed',
};

export function WebAIPanel() {
  const sites = useStore((s) => s.webAiSites);
  const presets = useStore((s) => s.webAiPresets);
  const learn = useStore((s) => s.webAiLearn);
  const ask = useStore((s) => s.webAiLastAsk);
  const pending = useStore((s) => s.webAiPending);
  const register = useStore((s) => s.registerWebAiSite);
  const patch = useStore((s) => s.patchWebAiSite);
  const del = useStore((s) => s.deleteWebAiSite);
  const learnSite = useStore((s) => s.learnWebAiSite);
  const refresh = useStore((s) => s.loadWebAiSites);
  const refreshLearn = useStore((s) => s.refreshLearnState);
  const askWebAi = useStore((s) => s.askWebAi);

  const [url, setUrl] = useState('');
  const [label, setLabel] = useState('');
  const [category, setCategory] = useState<'ai' | 'social'>('ai');
  const [presetId, setPresetId] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState('');

  useEffect(() => { refresh(); }, [refresh]);

  // Poll the learn state of any site currently learning.
  useEffect(() => {
    const learning = Object.values(learn).filter(
      (s) => s.phase !== 'ready' && s.phase !== 'failed',
    );
    if (!learning.length) return;
    const interval = setInterval(() => {
      learning.forEach((s) => refreshLearn(s.profile_id));
    }, 1500);
    return () => clearInterval(interval);
  }, [learn, refreshLearn]);

  const selected = useMemo(
    () => sites.find((s) => s.id === selectedId) ?? null,
    [sites, selectedId],
  );

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    await register({
      url: url.trim(),
      label: label.trim() || undefined,
      category,
      apply_preset_id: presetId || undefined,
    });
    setUrl('');
    setLabel('');
    setPresetId('');
  }

  async function handlePreset(id: string) {
    const p = presets.find((x) => x.id === id);
    if (!p) return;
    await register({ url: p.url, label: p.label, category: p.category, apply_preset_id: id });
  }

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* List + add form */}
      <div className="w-[360px] border-r border-white/5 flex flex-col">
        <div className="p-4 border-b border-white/5">
          <div className="flex items-center gap-2 mb-3">
            <Network size={18} className="text-sky-300" />
            <h2 className="font-semibold">Web-AI Mesh</h2>
            <button
              onClick={() => refresh()}
              className="ml-auto text-ink-300 hover:text-white"
              title="Refresh"
            >
              <RefreshCw size={14} />
            </button>
          </div>
          <form onSubmit={handleRegister} className="space-y-2">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://chat.openai.com/"
              className="w-full px-3 py-2 rounded-lg bg-black/30 border border-white/10 text-sm outline-none focus:border-sky-400/50"
            />
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Label (optional)"
              className="w-full px-3 py-2 rounded-lg bg-black/30 border border-white/10 text-sm outline-none focus:border-sky-400/50"
            />
            <div className="flex gap-2">
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as 'ai' | 'social')}
                className="flex-1 px-2 py-2 rounded-lg bg-black/30 border border-white/10 text-sm"
              >
                <option value="ai">AI</option>
                <option value="social">Social</option>
              </select>
              <select
                value={presetId}
                onChange={(e) => setPresetId(e.target.value)}
                className="flex-1 px-2 py-2 rounded-lg bg-black/30 border border-white/10 text-sm"
              >
                <option value="">No preset</option>
                {presets.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
            </div>
            <button
              type="submit"
              disabled={pending || !url.trim()}
              className="w-full px-3 py-2 rounded-lg bg-sky-500/20 text-sky-200 hover:bg-sky-500/30 disabled:opacity-40 text-sm font-medium"
            >
              Register site
            </button>
          </form>
          {presets.length > 0 && (
            <div className="mt-3">
              <div className="text-[10px] uppercase tracking-wider text-ink-300 mb-1">Quick add</div>
              <div className="flex flex-wrap gap-1">
                {presets.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handlePreset(p.id)}
                    className="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-[11px] text-ink-200"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {sites.length === 0 ? (
            <div className="text-center text-ink-300 text-sm p-6">
              No sites yet. Register one above to start teaching the Council.
            </div>
          ) : (
            sites.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedId(s.id)}
                className={clsx(
                  'w-full text-left px-3 py-2 rounded-lg mb-1 flex items-center gap-2 transition-colors',
                  selectedId === s.id ? 'bg-white/10' : 'hover:bg-white/5',
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{s.label}</div>
                  <div className="text-[11px] text-ink-300 truncate">{s.host}</div>
                </div>
                <span className={clsx('px-1.5 py-0.5 rounded text-[10px]', CATEGORY_PILL[s.category])}>
                  {s.category}
                </span>
                <span className={clsx('px-1.5 py-0.5 rounded text-[10px]', HEALTH_PILL[s.health.status])}>
                  {s.health.status}
                </span>
                <ChevronRight size={14} className="text-ink-300" />
              </button>
            ))
          )}
        </div>
      </div>

      {/* Detail pane */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!selected ? (
          <div className="flex-1 grid place-items-center text-ink-300 text-sm">
            Pick a site to inspect, learn, or ask.
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-white/5 flex items-center gap-3">
              <div className="flex-1">
                <div className="font-semibold">{selected.label}</div>
                <a
                  href={selected.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[12px] text-ink-300 hover:text-sky-300"
                >
                  {selected.url}
                </a>
              </div>
              <button
                onClick={() => learnSite(selected.id)}
                disabled={pending}
                className="px-3 py-2 rounded-lg bg-violet-500/20 text-violet-200 hover:bg-violet-500/30 disabled:opacity-40 text-sm flex items-center gap-2"
              >
                <Sparkles size={14} /> Learn
              </button>
              <button
                onClick={() => del(selected.id).then(() => setSelectedId(null))}
                className="px-2 py-2 rounded-lg bg-rose-500/10 text-rose-300 hover:bg-rose-500/20"
                title="Delete profile"
              >
                <Trash2 size={14} />
              </button>
            </div>

            <div className="p-4 grid grid-cols-2 gap-3 border-b border-white/5 text-sm">
              <div>
                <div className="text-ink-300 text-[11px] uppercase">Health</div>
                <span className={clsx('px-2 py-0.5 rounded text-xs', HEALTH_PILL[selected.health.status])}>
                  {selected.health.status}
                </span>
                {selected.health.last_error && (
                  <div className="text-[11px] text-rose-300 mt-1 line-clamp-2">{selected.health.last_error}</div>
                )}
              </div>
              <div>
                <div className="text-ink-300 text-[11px] uppercase">Confidence</div>
                <div className="font-mono">{(selected.confidence * 100).toFixed(0)}%</div>
              </div>
              <div>
                <div className="text-ink-300 text-[11px] uppercase">Ready</div>
                <div>{selected.is_ready ? 'yes' : 'no'}</div>
              </div>
              <div>
                <div className="text-ink-300 text-[11px] uppercase">Include in Council</div>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selected.include_in_council}
                    onChange={(e) => patch(selected.id, { include_in_council: e.target.checked })}
                  />
                  <span className="text-xs text-ink-200">Oracle votes</span>
                </label>
              </div>
            </div>

            {learn[selected.id] && (
              <div className="p-4 border-b border-white/5 text-sm">
                <div className="text-ink-300 text-[11px] uppercase mb-1">Last learn run</div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded bg-white/10 text-xs">
                    {PHASE_TEXT[learn[selected.id].phase] || learn[selected.id].phase}
                  </span>
                  <span className="text-[11px] text-ink-300">
                    confidence {(learn[selected.id].confidence * 100).toFixed(0)}%
                  </span>
                </div>
                {learn[selected.id].notes.length > 0 && (
                  <ul className="mt-2 text-[12px] text-ink-200 list-disc list-inside space-y-0.5">
                    {learn[selected.id].notes.slice(-6).map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                )}
                {learn[selected.id].error && (
                  <div className="mt-1 text-[11px] text-rose-300">{learn[selected.id].error}</div>
                )}
              </div>
            )}

            {selected.category === 'ai' && (
              <div className="p-4 flex-1 overflow-y-auto space-y-3">
                <div className="text-ink-300 text-[11px] uppercase">Ask the site directly</div>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={4}
                  placeholder="Question to send through the browser…"
                  className="w-full px-3 py-2 rounded-lg bg-black/30 border border-white/10 text-sm outline-none focus:border-sky-400/50 resize-y"
                />
                <button
                  disabled={pending || !prompt.trim() || !selected.is_ready}
                  onClick={() => askWebAi(selected.id, prompt.trim())}
                  className="px-3 py-2 rounded-lg bg-sky-500/20 text-sky-200 hover:bg-sky-500/30 disabled:opacity-40 text-sm font-medium flex items-center gap-2"
                >
                  <Send size={14} /> Send
                </button>
                {!selected.is_ready && (
                  <div className="text-[11px] text-amber-300">
                    Site not yet ready — run Learn first (and complete any login).
                  </div>
                )}
                {ask[selected.id] && (
                  <div className="mt-2 p-3 rounded-lg bg-white/5 text-sm whitespace-pre-wrap">
                    <div className="text-[11px] text-ink-300 mb-1">
                      {ask[selected.id].ok ? 'Reply' : 'Error'} ·
                      {' '}{ask[selected.id].elapsed_ms}ms
                      {ask[selected.id].selector_repaired && ' · selectors repaired'}
                    </div>
                    {ask[selected.id].ok ? ask[selected.id].text : ask[selected.id].error}
                  </div>
                )}
              </div>
            )}

            {selected.category === 'social' && (
              <div className="p-4 flex-1 overflow-y-auto text-sm text-ink-200 space-y-2">
                <p>
                  Social posting is HITL-gated. After Learn succeeds, use the existing
                  Autonomy queue or the <code className="text-sky-300">web_ai</code> tool to
                  publish — the Approvals dialog will let you confirm each post.
                </p>
                <p className="text-[11px] text-ink-300">
                  Confidence and selectors are visible above; if they look wrong, run Learn again
                  after navigating Chrome to a fresh state.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
