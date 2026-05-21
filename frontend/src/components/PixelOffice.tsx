/* Pixel-art virtual office.
 *
 * Renders the 8-room office on a low-resolution canvas (480 x 320) and lets
 * the browser scale it up with `image-rendering: pixelated` so every pixel
 * stays crisp. Per-agent animation state is derived live from the global
 * `events` stream.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from '../store';
import {
  LOGICAL_W, LOGICAL_H,
  renderFrame, ROOMS,
  type AgentAnim, type FrameInput,
} from '../lib/pixelEngine';
import { eventToState } from '../lib/pixelSprites';

/** How long an agent stays in its current state before drifting back to idle. */
const STATE_TIMEOUT = {
  thinking: 6000,
  talking: 2000,
  working: 4000,
  happy: 3000,
  sad: 3000,
  idle: 0,
} as const;

export function PixelOffice() {
  const roles = useStore((s) => s.roles);
  const events = useStore((s) => s.events);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animRef = useRef<Record<string, AgentAnim>>({});
  const [, forceRender] = useState(0);

  // Build a quick lookup of role -> color/title once per change.
  const roleMap = useMemo(() => {
    const m: Record<string, { color: string; title: string }> = {};
    for (const r of roles) m[r.id] = { color: r.color, title: r.title };
    return m;
  }, [roles]);

  // Reduce events to per-agent animation state.
  useEffect(() => {
    const now = Date.now();
    for (const ev of events) {
      if (!ev.actor || ev.actor === 'system') continue;
      const newState = eventToState(ev.kind);
      if (!newState) continue;
      const prev = animRef.current[ev.actor];
      const bubble = ev.kind === 'agent.message' && ev.content ? ev.content : prev?.bubble;
      const model = (ev.meta as Record<string, unknown> | undefined)?.model as string | undefined;
      animRef.current[ev.actor] = {
        state: newState,
        setAt: now,
        bubble: bubble?.slice(0, 64),
        model: model ?? prev?.model,
      };
    }
  }, [events]);

  // RAF loop drives the renderer and forces a state-bumping repaint.
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext('2d');
    if (!ctx) return;

    // Crisp pixels.
    ctx.imageSmoothingEnabled = false;
    cv.width = LOGICAL_W;
    cv.height = LOGICAL_H;

    let raf = 0;
    let last = 0;
    const tick = (t: number) => {
      // Cap to ~30 fps (we don't need 60 for a pixel scene with 4-frame anim).
      if (t - last >= 33) {
        last = t;
        const now = Date.now();
        // Time-out stale animation states back to idle.
        for (const [actor, anim] of Object.entries(animRef.current)) {
          const limit = STATE_TIMEOUT[anim.state];
          if (limit && now - anim.setAt > limit) {
            animRef.current[actor] = { ...anim, state: 'idle', setAt: now };
          }
        }
        const input: FrameInput = { roles: roleMap, anim: animRef.current, now };
        renderFrame(ctx, input);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [roleMap]);

  // Hover-tooltip text (logical pixel coords).
  const [hover, setHover] = useState<string | null>(null);
  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const cv = canvasRef.current;
    if (!cv) return;
    const rect = cv.getBoundingClientRect();
    const sx = (e.clientX - rect.left) * (LOGICAL_W / rect.width);
    const sy = (e.clientY - rect.top) * (LOGICAL_H / rect.height);
    const room = ROOMS.find(
      (r) => sx >= r.x && sx <= r.x + r.w && sy >= r.y && sy <= r.y + r.h,
    );
    setHover(room ? `${room.label} — ${room.agentName} (${roleMap[room.agentId]?.title ?? ''})` : null);
    void forceRender;
  };

  return (
    <div className="relative flex-1 overflow-hidden p-4">
      <div className="absolute inset-0 pointer-events-none">
        <div className="orb bg-[#7cd1ff]/40 w-[420px] h-[420px] -top-20 -left-24" />
        <div className="orb bg-[#b58cff]/40 w-[420px] h-[420px] top-1/3 right-0" />
        <div className="orb bg-[#ff8ad6]/30 w-[420px] h-[420px] bottom-0 left-1/3" />
      </div>

      <div className="relative h-full w-full flex flex-col items-center justify-center gap-3">
        <canvas
          ref={canvasRef}
          onMouseMove={onMouseMove}
          onMouseLeave={() => setHover(null)}
          className="rounded-2xl border border-white/10 shadow-glow"
          style={{
            imageRendering: 'pixelated',
            width: 'min(960px, 95%)',
            height: 'auto',
            background: '#06070d',
          }}
        />

        {/* Tooltip */}
        <div className="h-5 text-xs font-mono text-ink-200">
          {hover ?? 'hover a room to see its agent'}
        </div>

        {/* Live event ticker */}
        <div className="glass rounded-xl px-3 py-2 max-h-28 w-[min(960px,95%)] overflow-y-auto scrollbar-thin text-[11px] font-mono">
          {events.slice(-6).reverse().map((ev) => (
            <div key={ev.id || `${ev.kind}-${ev.ts}`} className="flex gap-2 text-ink-200">
              <span className="text-ink-300 w-16 shrink-0">{ev.kind.split('.').pop()}</span>
              <span className="text-emerald-300 w-20 shrink-0 truncate">{ev.actor}</span>
              <span className="truncate text-ink-100">{ev.content?.slice(0, 180)}</span>
            </div>
          ))}
          {events.length === 0 && (
            <div className="text-ink-300 italic">no events yet — try a council objective from the Chat panel</div>
          )}
        </div>
      </div>
    </div>
  );
}
