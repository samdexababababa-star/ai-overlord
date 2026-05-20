/* Virtual office — agents in their rooms, with live thought bubbles
 * driven by the `events` stream. */

import { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useStore } from '../store';
import clsx from 'clsx';

const ROOM_LAYOUT: Record<string, { x: number; y: number; w: number; h: number; label: string }> = {
  war_room:    { x: 60,  y: 80,  w: 260, h: 200, label: 'War Room — Planner' },
  library:     { x: 360, y: 80,  w: 260, h: 200, label: 'Library — Researcher' },
  lab:         { x: 660, y: 80,  w: 240, h: 200, label: 'Lab — Coder' },
  observatory: { x: 60,  y: 320, w: 260, h: 180, label: 'Observatory — Vision' },
  court:       { x: 360, y: 320, w: 260, h: 180, label: 'Court — Critic' },
  workshop:    { x: 660, y: 320, w: 240, h: 180, label: 'Workshop — Executor' },
  atrium:      { x: 220, y: 540, w: 540, h: 140, label: 'Atrium — Conductor' },
};

type LatestByActor = Record<string, { content: string; meta?: Record<string, unknown>; ts: number }>;

export function AgentOffice() {
  const roles = useStore((s) => s.roles);
  const events = useStore((s) => s.events);

  const latest: LatestByActor = useMemo(() => {
    const out: LatestByActor = {};
    for (const ev of events) {
      if (!ev.actor || ev.actor === 'system') continue;
      const ts = ev.ts || Date.now() / 1000;
      const prev = out[ev.actor];
      if (!prev || ts >= prev.ts) {
        out[ev.actor] = { content: ev.content || '', meta: ev.meta, ts };
      }
    }
    return out;
  }, [events]);

  const activeNow: string | undefined = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i];
      if (ev.kind === 'agent.start' && ev.actor !== 'system') return ev.actor;
      if (ev.kind === 'agent.finish' && ev.actor !== 'system') return undefined;
    }
    return undefined;
  }, [events]);

  return (
    <div className="relative flex-1 overflow-hidden">
      {/* Floor backdrop */}
      <div className="absolute inset-0">
        <div className="orb bg-[#7cd1ff]/60 w-[420px] h-[420px] -top-20 -left-24" />
        <div className="orb bg-[#b58cff]/60 w-[420px] h-[420px] top-1/3 right-0" />
        <div className="orb bg-[#ff8ad6]/40 w-[420px] h-[420px] bottom-0 left-1/3" />
      </div>

      <div className="relative w-full h-full">
        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 1000 720" preserveAspectRatio="xMidYMid meet">
          {/* Optional connecting lines between rooms */}
          {Object.entries(ROOM_LAYOUT).map(([id, r]) => (
            <line
              key={id}
              x1={r.x + r.w / 2}
              y1={r.y + r.h / 2}
              x2={ROOM_LAYOUT.atrium.x + ROOM_LAYOUT.atrium.w / 2}
              y2={ROOM_LAYOUT.atrium.y + ROOM_LAYOUT.atrium.h / 2}
              stroke="rgba(255,255,255,0.08)"
              strokeDasharray="4 4"
            />
          ))}
        </svg>
        <div
          className="absolute inset-0"
          style={{ transform: 'translate(0,0)' }}
        >
          {roles.map((r) => {
            const layout = ROOM_LAYOUT[r.room] ?? { x: 100, y: 100, w: 220, h: 160, label: r.title };
            const isActive = activeNow === r.id;
            const msg = latest[r.id];
            return (
              <Room
                key={r.id}
                x={layout.x}
                y={layout.y}
                w={layout.w}
                h={layout.h}
                label={layout.label}
                color={r.color}
                name={r.name}
                role={r.title}
                active={isActive}
                latest={msg?.content}
                model={(msg?.meta as Record<string, string> | undefined)?.model}
              />
            );
          })}
        </div>
      </div>

      {/* Event ticker */}
      <div className="absolute bottom-3 left-3 right-3 glass rounded-xl px-3 py-2 max-h-24 overflow-y-auto scrollbar-thin text-[11px] font-mono">
        {events.slice(-8).reverse().map((ev) => (
          <div key={ev.id || `${ev.kind}-${ev.ts}`} className="flex gap-2 text-ink-200">
            <span className="text-ink-300 w-14 shrink-0">{ev.kind.split('.').pop()}</span>
            <span className="text-emerald-300 w-20 shrink-0 truncate">{ev.actor}</span>
            <span className="truncate text-ink-100">{ev.content?.slice(0, 200)}</span>
          </div>
        ))}
        {events.length === 0 && (
          <div className="text-ink-300 italic">no events yet — try a council objective</div>
        )}
      </div>
    </div>
  );
}

function Room(props: {
  x: number; y: number; w: number; h: number; label: string;
  color: string; name: string; role: string;
  active: boolean; latest?: string; model?: string;
}) {
  return (
    <div
      className={clsx(
        'absolute rounded-2xl glass transition-all',
        props.active ? 'shadow-glow border-white/30' : '',
      )}
      style={{
        left: `${(props.x / 1000) * 100}%`,
        top: `${(props.y / 720) * 100}%`,
        width: `${(props.w / 1000) * 100}%`,
        height: `${(props.h / 720) * 100}%`,
      }}
    >
      <div className="px-3 py-2 flex items-center justify-between border-b border-glass-ring">
        <span className="text-[10px] uppercase tracking-widest text-ink-300">{props.label}</span>
        {props.active && (
          <span className="text-[9px] uppercase text-emerald-300 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-300 animate-pulse" />
            live
          </span>
        )}
      </div>
      <div className="p-3 flex items-start gap-3 h-[calc(100%-2rem)]">
        <motion.div
          animate={props.active ? { y: [0, -3, 0] } : { y: 0 }}
          transition={{ repeat: props.active ? Infinity : 0, duration: 1.6, ease: 'easeInOut' }}
          className="relative w-12 h-12 shrink-0"
        >
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background: `radial-gradient(circle at 30% 30%, ${props.color}, ${props.color}55 70%)`,
              boxShadow: props.active ? `0 0 20px ${props.color}` : 'none',
            }}
          />
          <div className="absolute inset-1 rounded-full bg-ink-900/60 grid place-items-center text-[10px] font-display">
            {props.name[0]}
          </div>
        </motion.div>
        <div className="flex-1 overflow-hidden">
          <div className="text-sm font-display text-ink-50">{props.name}</div>
          <div className="text-[10px] uppercase tracking-widest text-ink-300 mb-1">
            {props.role}
            {props.model && <span className="ml-2 normal-case tracking-normal text-ink-200/70">· {props.model}</span>}
          </div>
          <AnimatePresence mode="popLayout">
            {props.latest && (
              <motion.div
                key={props.latest.slice(0, 60)}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="text-[11px] text-ink-100 leading-snug line-clamp-4"
              >
                {props.latest}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
