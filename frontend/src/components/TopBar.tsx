import { useStore } from '../store';
import { motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';

const titles: Record<string, { title: string; subtitle: string }> = {
  chat: { title: 'Conversation', subtitle: 'Ask anything — or hand the council an objective' },
  office: { title: 'Virtual Office', subtitle: 'Live view of the agents at work' },
  reasoning: { title: 'Reasoning Engine', subtitle: 'Tree of Thoughts · Reflexion · Debate · Constitutional AI' },
  autonomy: { title: 'Autonomy', subtitle: 'Goal management, background execution, HITL approvals' },
  webai: { title: 'Web-AI Mesh', subtitle: 'Teach the council to drive external AI sites + social via Chrome' },
  memory: { title: 'Memory', subtitle: 'Episodic log + semantic recall' },
  tools: { title: 'Tools', subtitle: 'What the agents can reach' },
  settings: { title: 'Settings', subtitle: 'API keys, providers, app preferences' },
};

export function TopBar() {
  const view = useStore((s) => s.view);
  const health = useStore((s) => s.health);
  const meta = titles[view] ?? { title: view, subtitle: '' };
  return (
    <header className="drag flex items-center justify-between h-14 px-6 border-b border-glass-ring">
      <div className="flex items-center gap-3">
        <div className="text-xs text-ink-300 font-mono tracking-wider">AI OVERLORD</div>
        <ChevronRight size={12} className="text-ink-300" />
        <motion.div
          key={view}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-baseline gap-3"
        >
          <h1 className="text-sm font-medium tracking-tight">{meta.title}</h1>
          <span className="text-[11px] text-ink-300">{meta.subtitle}</span>
        </motion.div>
      </div>
      <div className="flex items-center gap-2 no-drag">
        {(health?.providers || []).map((p) => (
          <span
            key={p}
            className="px-2 py-0.5 text-[10px] uppercase rounded-md bg-white/5 border border-glass-ring tracking-widest text-ink-200"
          >
            {p}
          </span>
        ))}
        {!health?.has_keys && (
          <span className="px-2 py-0.5 text-[10px] rounded-md bg-amber-500/20 text-amber-200 border border-amber-400/30">
            no keys configured
          </span>
        )}
      </div>
    </header>
  );
}
