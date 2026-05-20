import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Sparkles, Network } from 'lucide-react';
import clsx from 'clsx';
import { useStore } from '../store';

export function ChatPanel() {
  const turns = useStore((s) => s.turns);
  const pending = useStore((s) => s.pending);
  const ask = useStore((s) => s.ask);
  const runObjective = useStore((s) => s.runObjective);
  const hasKeys = useStore((s) => s.health?.has_keys);
  const setShowOnboarding = useStore((s) => s.setShowOnboarding);

  const [input, setInput] = useState('');
  const [mode, setMode] = useState<'ask' | 'council'>('ask');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, pending]);

  async function submit() {
    const text = input.trim();
    if (!text || pending) return;
    setInput('');
    if (mode === 'council') await runObjective(text);
    else await ask(text);
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin px-8 py-6 space-y-4">
        {turns.length === 0 && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md">
              <h2 className="text-3xl font-display shimmer-text mb-4">Hello.</h2>
              <p className="text-ink-200 text-sm leading-relaxed">
                Ask a quick question, or hand the council a goal. The team will plan, critique, and synthesize.
              </p>
              {!hasKeys && (
                <button
                  onClick={() => setShowOnboarding(true)}
                  className="mt-6 px-4 py-2 rounded-xl glass-strong text-sm hover:bg-white/10 transition"
                >
                  Set up your providers →
                </button>
              )}
            </div>
          </div>
        )}
        <AnimatePresence initial={false}>
          {turns.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={clsx('flex', t.role === 'user' ? 'justify-end' : 'justify-start')}
            >
              <div
                className={clsx(
                  'max-w-[78%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap leading-relaxed',
                  t.role === 'user'
                    ? 'glass-strong text-ink-50'
                    : 'glass text-ink-50',
                )}
              >
                {t.content}
                {t.meta?.verdict ? (
                  <div className="mt-3 pt-3 border-t border-glass-ring text-[10px] uppercase tracking-widest text-ink-300">
                    council verdict: {String(t.meta.verdict)}
                  </div>
                ) : null}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {pending && (
          <div className="flex justify-start">
            <div className="glass rounded-2xl px-4 py-3 text-sm flex items-center gap-2 text-ink-200">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-white/70 animate-pulse" />
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-white/50 animate-pulse [animation-delay:120ms]" />
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-white/30 animate-pulse [animation-delay:240ms]" />
              <span className="ml-2 text-xs">{mode === 'council' ? 'council deliberating' : 'thinking'}</span>
            </div>
          </div>
        )}
      </div>
      <div className="border-t border-glass-ring px-6 py-4">
        <div className="glass-strong rounded-2xl px-3 py-2 flex items-center gap-2">
          <div className="flex items-center bg-white/5 rounded-xl p-0.5">
            <button
              onClick={() => setMode('ask')}
              className={clsx(
                'flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-lg transition',
                mode === 'ask' ? 'bg-white/10 text-white' : 'text-ink-300',
              )}
            >
              <Sparkles size={12} /> ask
            </button>
            <button
              onClick={() => setMode('council')}
              className={clsx(
                'flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-lg transition',
                mode === 'council' ? 'bg-white/10 text-white' : 'text-ink-300',
              )}
            >
              <Network size={12} /> council
            </button>
          </div>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={
              mode === 'ask'
                ? 'Ask the overlord…'
                : 'Give the council an objective…'
            }
            className="flex-1 bg-transparent outline-none placeholder:text-ink-300 text-sm px-2"
          />
          <button
            onClick={submit}
            disabled={pending || !input.trim()}
            className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#7cd1ff] to-[#b58cff] text-ink-900 grid place-items-center disabled:opacity-40 transition"
          >
            <Send size={16} strokeWidth={2.2} />
          </button>
        </div>
      </div>
    </div>
  );
}
