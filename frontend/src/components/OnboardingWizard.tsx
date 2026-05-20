/* Step-by-step onboarding to obtain & validate API keys for each provider. */

import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, ExternalLink, Loader2, X, Plus, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import { useStore } from '../store';

const ORDER = ['mistral', 'nvidia', 'google', 'groq'] as const;
type ProviderId = (typeof ORDER)[number];

export function OnboardingWizard() {
  const show = useStore((s) => s.showOnboarding);
  const setShow = useStore((s) => s.setShowOnboarding);
  const providers = useStore((s) => s.providers);
  const configured = useStore((s) => s.configuredKeys);
  const addKey = useStore((s) => s.addKey);
  const validateKey = useStore((s) => s.validateKey);
  const removeKey = useStore((s) => s.removeKey);

  const [step, setStep] = useState<number>(0);
  const provider: ProviderId = ORDER[step];
  const info = providers[provider];

  const [keyInput, setKeyInput] = useState('');
  const [label, setLabel] = useState('');
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setKeyInput('');
    setLabel('');
    setError(null);
    // Suggest a label like "mistral-1"
    const existing = configured[provider]?.length || 0;
    setLabel(`${provider}-${existing + 1}`);
  }, [provider, configured]);

  const total = ORDER.length;
  const list = configured[provider] || [];

  const canFinish = useMemo(
    () => Object.values(configured).some((arr) => arr.length > 0),
    [configured],
  );

  async function tryValidateAndSave() {
    if (!keyInput.trim()) return;
    setValidating(true);
    setError(null);
    try {
      const ok = await validateKey(provider, keyInput.trim());
      if (!ok) {
        setError('Key did not validate. Double-check it (or skip if you want to add it later).');
        setValidating(false);
        return;
      }
      await addKey(provider, label || `${provider}-${Date.now()}`, keyInput.trim());
      setKeyInput('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setValidating(false);
    }
  }

  function openExternal(url: string) {
    if (window.overlord?.openExternal) {
      window.overlord.openExternal(url);
    } else {
      window.open(url, '_blank');
    }
  }

  if (!show) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-8 bg-black/40 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-strong rounded-3xl w-full max-w-3xl max-h-[88vh] overflow-hidden flex flex-col"
      >
        <header className="px-6 py-4 flex items-center justify-between border-b border-glass-ring">
          <div>
            <h2 className="text-base font-display">Welcome — let's connect your providers</h2>
            <p className="text-[11px] text-ink-300">
              Each provider gives the council a different superpower. You need at least one.
            </p>
          </div>
          <button
            onClick={() => setShow(false)}
            className="w-8 h-8 grid place-items-center rounded-lg hover:bg-white/5"
          >
            <X size={16} />
          </button>
        </header>

        {/* Stepper */}
        <div className="px-6 py-3 flex items-center gap-2">
          {ORDER.map((p, i) => {
            const hasKeys = (configured[p]?.length || 0) > 0;
            const active = i === step;
            return (
              <button
                key={p}
                onClick={() => setStep(i)}
                className={clsx(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px] uppercase tracking-wider transition',
                  active
                    ? 'bg-white/10 text-white'
                    : 'text-ink-300 hover:bg-white/5',
                )}
              >
                <span
                  className={clsx(
                    'w-4 h-4 rounded-full grid place-items-center text-[8px]',
                    hasKeys
                      ? 'bg-emerald-500/30 text-emerald-200'
                      : 'bg-white/10 text-ink-300',
                  )}
                >
                  {hasKeys ? <Check size={10} /> : i + 1}
                </span>
                {providers[p]?.label || p}
              </button>
            );
          })}
          <div className="ml-auto text-[11px] text-ink-300">
            step {step + 1} / {total}
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={provider}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -12 }}
            className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4 space-y-5"
          >
            {!info ? (
              <div className="text-ink-300 text-sm">Loading provider info…</div>
            ) : (
              <>
                <section>
                  <h3 className="text-sm font-medium mb-2">{info.label}</h3>
                  <p className="text-[12px] text-ink-200">{info.tier_note}</p>
                  <div className="mt-3 flex gap-2 flex-wrap">
                    <button
                      onClick={() => openExternal(info.console)}
                      className="px-3 py-1.5 text-[11px] rounded-lg glass hover:bg-white/10 inline-flex items-center gap-1"
                    >
                      Open key console <ExternalLink size={12} />
                    </button>
                    <button
                      onClick={() => openExternal(info.signup)}
                      className="px-3 py-1.5 text-[11px] rounded-lg glass hover:bg-white/10 inline-flex items-center gap-1"
                    >
                      Sign up <ExternalLink size={12} />
                    </button>
                  </div>
                </section>

                <section className="glass-inset rounded-2xl p-4">
                  <h4 className="text-[11px] uppercase tracking-widest text-ink-300 mb-2">
                    How to obtain a key
                  </h4>
                  <ol className="text-[12px] text-ink-100 space-y-1 list-decimal list-inside">
                    {info.steps.map((s, i) => <li key={i}>{s}</li>)}
                  </ol>
                </section>

                <section>
                  <h4 className="text-[11px] uppercase tracking-widest text-ink-300 mb-2">
                    Configured keys ({list.length})
                  </h4>
                  {list.length === 0 ? (
                    <div className="text-[12px] text-ink-300">No keys yet for this provider.</div>
                  ) : (
                    <div className="space-y-1.5">
                      {list.map((k) => (
                        <div
                          key={k.label}
                          className="flex items-center justify-between text-[12px] glass-inset rounded-lg px-3 py-1.5"
                        >
                          <span className="font-mono">
                            <span className="text-ink-300">{k.label}</span>
                            <span className="ml-3 text-ink-100">{k.masked}</span>
                          </span>
                          <button
                            onClick={() => removeKey(provider, k.label)}
                            className="p-1 rounded text-ink-300 hover:text-rose-400"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 grid grid-cols-[1fr_2fr_auto] gap-2 items-center">
                    <input
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                      placeholder="label"
                      className="glass-inset rounded-lg px-2 py-1.5 text-[12px] outline-none"
                    />
                    <input
                      value={keyInput}
                      onChange={(e) => setKeyInput(e.target.value)}
                      placeholder={`Paste a new ${info.label} API key…`}
                      className="glass-inset rounded-lg px-2 py-1.5 text-[12px] font-mono outline-none"
                      onKeyDown={(e) => e.key === 'Enter' && tryValidateAndSave()}
                    />
                    <button
                      onClick={tryValidateAndSave}
                      disabled={!keyInput.trim() || validating}
                      className="px-3 py-1.5 text-[11px] rounded-lg bg-gradient-to-br from-[#7cd1ff] to-[#b58cff] text-ink-900 inline-flex items-center gap-1 disabled:opacity-40"
                    >
                      {validating ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                      Validate & save
                    </button>
                  </div>
                  {error && <div className="text-[11px] text-rose-300 mt-2">{error}</div>}
                </section>

                <section>
                  <h4 className="text-[11px] uppercase tracking-widest text-ink-300 mb-2">
                    Models unlocked
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {info.models.map((m) => (
                      <span
                        key={m.id}
                        className="text-[10px] px-2 py-0.5 rounded-md glass-inset font-mono text-ink-200"
                        title={m.capabilities.join(', ')}
                      >
                        {m.label}
                      </span>
                    ))}
                  </div>
                </section>
              </>
            )}
          </motion.div>
        </AnimatePresence>

        <footer className="px-6 py-4 border-t border-glass-ring flex items-center justify-between">
          <button
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="text-[12px] text-ink-300 hover:text-white disabled:opacity-30"
          >
            ← Previous
          </button>
          <div className="flex gap-2">
            {step < total - 1 ? (
              <button
                onClick={() => setStep((s) => s + 1)}
                className="px-3 py-1.5 text-[12px] rounded-lg glass-strong hover:bg-white/10"
              >
                Next →
              </button>
            ) : (
              <button
                onClick={() => setShow(false)}
                disabled={!canFinish}
                className="px-4 py-1.5 text-[12px] rounded-lg bg-gradient-to-br from-[#7cd1ff] to-[#b58cff] text-ink-900 disabled:opacity-40"
              >
                {canFinish ? 'Done — enter the overlord' : 'Add at least one key first'}
              </button>
            )}
          </div>
        </footer>
      </motion.div>
    </div>
  );
}
