import { useStore } from '../store';

export function SettingsPanel() {
  const configured = useStore((s) => s.configuredKeys);
  const models = useStore((s) => s.models);
  const setShow = useStore((s) => s.setShowOnboarding);

  const totalKeys = Object.values(configured).reduce((n, arr) => n + arr.length, 0);

  return (
    <div className="p-8 space-y-6 overflow-y-auto scrollbar-thin">
      <section className="glass rounded-2xl p-5">
        <h3 className="text-sm font-display mb-2">API keys</h3>
        <p className="text-[12px] text-ink-200 mb-3">
          {totalKeys} key(s) configured across {Object.keys(configured).length} provider(s). Multiple keys per provider rotate automatically on quota errors.
        </p>
        <button
          onClick={() => setShow(true)}
          className="px-4 py-2 text-xs rounded-xl glass-strong hover:bg-white/10"
        >
          Manage providers & keys
        </button>
      </section>

      <section className="glass rounded-2xl p-5">
        <h3 className="text-sm font-display mb-3">Models available ({models.length})</h3>
        <div className="grid grid-cols-2 gap-2">
          {models.map((m) => (
            <div key={`${m.provider}-${m.id}`} className="glass-inset rounded-lg px-3 py-2 text-[11px]">
              <div className="font-mono text-ink-100">{m.label}</div>
              <div className="text-ink-300 text-[10px]">{m.provider} · {m.capabilities.join(', ')} · ctx {m.context_window.toLocaleString()}</div>
            </div>
          ))}
          {models.length === 0 && (
            <div className="text-ink-300 text-xs col-span-2">No models — add a provider key first.</div>
          )}
        </div>
      </section>

      <section className="glass rounded-2xl p-5">
        <h3 className="text-sm font-display mb-2">About</h3>
        <p className="text-[12px] text-ink-200">
          AI Overlord — autonomous multi-provider council. Open source. Use responsibly.
        </p>
      </section>
    </div>
  );
}
