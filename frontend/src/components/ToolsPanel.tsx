import { useEffect, useState } from 'react';
import { apiJSON } from '../api';

type Tool = {
  name: string;
  description: string;
  parameters: unknown;
  requires_confirmation: boolean;
};

export function ToolsPanel() {
  const [tools, setTools] = useState<Tool[]>([]);
  useEffect(() => {
    apiJSON<{ tools: Tool[] }>('/tools').then((d) => setTools(d.tools)).catch(() => {});
  }, []);
  return (
    <div className="p-8 grid grid-cols-2 gap-3 overflow-y-auto scrollbar-thin">
      {tools.map((t) => (
        <div key={t.name} className="glass rounded-2xl p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-sm text-ink-50">{t.name}</span>
            {t.requires_confirmation && (
              <span className="text-[9px] uppercase px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-200">
                requires confirm
              </span>
            )}
          </div>
          <p className="text-[12px] text-ink-200 leading-snug">{t.description}</p>
        </div>
      ))}
      {tools.length === 0 && <div className="text-ink-300 text-sm">No tools registered.</div>}
    </div>
  );
}
