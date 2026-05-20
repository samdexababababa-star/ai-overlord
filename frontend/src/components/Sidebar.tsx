import { motion } from 'framer-motion';
import {
  Brain, Building2, MessagesSquare, Wrench, Settings2, Activity,
  Sparkles, Target,
} from 'lucide-react';
import clsx from 'clsx';
import { useStore } from '../store';

const items = [
  { id: 'chat', label: 'Chat', icon: MessagesSquare },
  { id: 'office', label: 'Office', icon: Building2 },
  { id: 'reasoning', label: 'Reasoning', icon: Sparkles },
  { id: 'autonomy', label: 'Autonomy', icon: Target },
  { id: 'memory', label: 'Memory', icon: Brain },
  { id: 'tools', label: 'Tools', icon: Wrench },
  { id: 'settings', label: 'Settings', icon: Settings2 },
] as const;

export function Sidebar() {
  const view = useStore((s) => s.view);
  const setView = useStore((s) => s.setView);
  const eventsConnected = useStore((s) => s.eventsConnected);
  const health = useStore((s) => s.health);

  return (
    <aside className="glass-strong w-[68px] h-full flex flex-col items-center py-6 gap-3 rounded-r-3xl">
      <div className="relative w-10 h-10 mb-2">
        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-[#7cd1ff] via-[#b58cff] to-[#ff8ad6] opacity-90 animate-pulse-soft" />
        <div className="absolute inset-1 rounded-full bg-ink-900 grid place-items-center">
          <span className="text-[10px] font-mono tracking-tighter">AI</span>
        </div>
      </div>
      {items.map((it) => {
        const Icon = it.icon;
        const active = view === it.id;
        return (
          <button
            key={it.id}
            onClick={() => setView(it.id)}
            className={clsx(
              'relative w-12 h-12 rounded-2xl flex items-center justify-center transition-all no-drag',
              active ? 'glass-strong text-white' : 'text-ink-200 hover:text-white hover:bg-white/5',
            )}
            title={it.label}
          >
            <Icon size={20} strokeWidth={1.6} />
            {active && (
              <motion.span
                layoutId="active-pill"
                className="absolute -left-1 top-1/2 -translate-y-1/2 h-6 w-[3px] rounded-full bg-gradient-to-b from-[#7cd1ff] to-[#b58cff]"
              />
            )}
          </button>
        );
      })}
      <div className="mt-auto flex flex-col items-center gap-2">
        <div
          className={clsx(
            'flex items-center justify-center w-9 h-9 rounded-full text-[10px] font-mono',
            eventsConnected ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300',
          )}
          title={eventsConnected ? 'event bus connected' : 'reconnecting…'}
        >
          <Activity size={16} />
        </div>
        <div className="text-[9px] text-ink-300 font-mono">
          {(health?.providers || []).length}/7
        </div>
      </div>
    </aside>
  );
}
