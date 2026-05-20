import { useEffect, useState } from 'react';
import { apiJSON } from '../api';

type Episode = {
  id: number;
  ts: number;
  kind: string;
  actor: string;
  content: string;
};

export function MemoryPanel() {
  const [items, setItems] = useState<Episode[]>([]);
  const [q, setQ] = useState('');
  useEffect(() => {
    apiJSON<{ items: Episode[] }>('/memory/episodic?limit=200').then((d) => setItems(d.items));
  }, []);
  async function doSearch() {
    if (!q.trim()) {
      const d = await apiJSON<{ items: Episode[] }>('/memory/episodic?limit=200');
      setItems(d.items);
      return;
    }
    const d = await apiJSON<{ items: Episode[] }>(`/memory/episodic/search?q=${encodeURIComponent(q)}`);
    setItems(d.items);
  }
  return (
    <div className="flex flex-col h-full">
      <div className="px-8 py-4 flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && doSearch()}
          placeholder="Search the agent's memory…"
          className="glass-inset rounded-lg px-3 py-2 text-sm flex-1 outline-none"
        />
        <button onClick={doSearch} className="px-3 py-2 text-xs glass-strong rounded-lg hover:bg-white/10">
          Search
        </button>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin px-8 pb-8 space-y-2">
        {items.map((it) => (
          <div key={it.id} className="glass rounded-xl px-4 py-3 text-[12px]">
            <div className="flex items-center gap-2 mb-1 text-ink-300 font-mono text-[10px] uppercase">
              <span>{new Date(it.ts * 1000).toLocaleString()}</span>
              <span>· {it.kind}</span>
              <span>· {it.actor}</span>
            </div>
            <div className="whitespace-pre-wrap leading-relaxed text-ink-50 line-clamp-4">{it.content}</div>
          </div>
        ))}
        {items.length === 0 && <div className="text-ink-300 italic text-sm">Empty.</div>}
      </div>
    </div>
  );
}
