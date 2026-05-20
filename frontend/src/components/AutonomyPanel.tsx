import { useEffect, useState, useCallback } from 'react';
import { apiJSON, apiFetch } from '../api';

type Goal = {
  id: string;
  title: string;
  description: string;
  priority: string;
  status: string;
  progress: number;
  result: string;
  error: string;
  retry_count: number;
  created_at: number;
  tags: string[];
};

type LoopStats = {
  running: boolean;
  total_cycles: number;
  goals_completed: number;
  goals_failed: number;
  total_cost_usd: number;
  uptime_seconds: number;
  last_error: string;
};

type PendingAction = {
  id: string;
  action_type: string;
  description: string;
  risk_level: string;
  created_at: number;
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-300',
  high: 'bg-orange-500/20 text-orange-300',
  medium: 'bg-blue-500/20 text-blue-300',
  low: 'bg-green-500/20 text-green-300',
  background: 'bg-gray-500/20 text-gray-300',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-500/20 text-yellow-300',
  running: 'bg-blue-500/20 text-blue-300',
  completed: 'bg-green-500/20 text-green-300',
  failed: 'bg-red-500/20 text-red-300',
  cancelled: 'bg-gray-500/20 text-gray-300',
  blocked: 'bg-purple-500/20 text-purple-300',
};

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function AutonomyPanel() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loopStats, setLoopStats] = useState<LoopStats | null>(null);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newPriority, setNewPriority] = useState('medium');

  const refresh = useCallback(async () => {
    try {
      const [goalsData, statsData, hitlData] = await Promise.all([
        apiJSON<{ goals: Goal[] }>('/autonomy/goals'),
        apiJSON<{ goals: Record<string, number>; loop: LoopStats }>('/autonomy/stats'),
        apiJSON<{ actions: PendingAction[] }>('/autonomy/hitl/pending'),
      ]);
      setGoals(goalsData.goals);
      setLoopStats(statsData.loop);
      setPending(hitlData.actions);
    } catch {
      // pass
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const createGoal = async () => {
    if (!newTitle.trim()) return;
    await apiFetch('/autonomy/goals', {
      method: 'POST',
      body: JSON.stringify({
        title: newTitle.trim(),
        description: newDescription.trim(),
        priority: newPriority,
      }),
    });
    setNewTitle('');
    setNewDescription('');
    refresh();
  };

  const toggleLoop = async () => {
    const endpoint = loopStats?.running ? '/autonomy/loop/stop' : '/autonomy/loop/start';
    await apiFetch(endpoint, { method: 'POST' });
    refresh();
  };

  const approveAction = async (id: string) => {
    await apiFetch(`/autonomy/hitl/approve/${id}`, { method: 'POST' });
    refresh();
  };

  const rejectAction = async (id: string) => {
    await apiFetch(`/autonomy/hitl/reject/${id}`, { method: 'POST' });
    refresh();
  };

  const deleteGoal = async (id: string) => {
    await apiFetch(`/autonomy/goals/${id}`, { method: 'DELETE' });
    refresh();
  };

  return (
    <div className="p-6 space-y-4 overflow-y-auto scrollbar-thin max-h-full">
      {/* Loop status */}
      <section className="glass rounded-2xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-display">Autonomy Loop</h3>
          <button
            onClick={toggleLoop}
            className={`px-4 py-1.5 text-[11px] rounded-xl ${
              loopStats?.running
                ? 'bg-red-500/20 text-red-300 hover:bg-red-500/30'
                : 'bg-green-500/20 text-green-300 hover:bg-green-500/30'
            }`}
          >
            {loopStats?.running ? 'Stop' : 'Start'}
          </button>
        </div>

        {loopStats && (
          <div className="grid grid-cols-4 gap-2">
            <div className="glass-inset rounded-lg px-3 py-2 text-center">
              <div className="text-[10px] text-ink-300">Status</div>
              <div className={`text-sm font-mono ${loopStats.running ? 'text-green-400' : 'text-ink-300'}`}>
                {loopStats.running ? 'Running' : 'Stopped'}
              </div>
            </div>
            <div className="glass-inset rounded-lg px-3 py-2 text-center">
              <div className="text-[10px] text-ink-300">Uptime</div>
              <div className="text-sm font-mono text-ink-100">{formatUptime(loopStats.uptime_seconds)}</div>
            </div>
            <div className="glass-inset rounded-lg px-3 py-2 text-center">
              <div className="text-[10px] text-ink-300">Completed</div>
              <div className="text-sm font-mono text-green-400">{loopStats.goals_completed}</div>
            </div>
            <div className="glass-inset rounded-lg px-3 py-2 text-center">
              <div className="text-[10px] text-ink-300">Failed</div>
              <div className="text-sm font-mono text-red-400">{loopStats.goals_failed}</div>
            </div>
          </div>
        )}
        {loopStats?.last_error && (
          <p className="text-[10px] text-red-400 mt-2">Last error: {loopStats.last_error.slice(0, 200)}</p>
        )}
      </section>

      {/* Pending HITL actions */}
      {pending.length > 0 && (
        <section className="glass rounded-2xl p-5 border border-amber-500/30">
          <h3 className="text-sm font-display mb-2 text-amber-300">Actions Pending Approval ({pending.length})</h3>
          <div className="space-y-2">
            {pending.map((a) => (
              <div key={a.id} className="glass-inset rounded-lg p-3 flex items-center justify-between">
                <div>
                  <span className={`text-[9px] uppercase px-1.5 py-0.5 rounded mr-2 ${
                    a.risk_level === 'critical' ? 'bg-red-500/20 text-red-300' :
                    a.risk_level === 'high' ? 'bg-orange-500/20 text-orange-300' :
                    'bg-yellow-500/20 text-yellow-300'
                  }`}>{a.risk_level}</span>
                  <span className="text-[11px] text-ink-100">{a.description.slice(0, 100)}</span>
                  <span className="text-[10px] text-ink-300 ml-2">[{a.action_type}]</span>
                </div>
                <div className="flex gap-1.5 shrink-0">
                  <button onClick={() => approveAction(a.id)} className="px-2.5 py-1 text-[10px] rounded-lg bg-green-500/20 text-green-300 hover:bg-green-500/30">Approve</button>
                  <button onClick={() => rejectAction(a.id)} className="px-2.5 py-1 text-[10px] rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30">Reject</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* New goal */}
      <section className="glass rounded-2xl p-5">
        <h3 className="text-sm font-display mb-3">Add Goal</h3>
        <div className="space-y-2">
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Goal title…"
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-[12px] text-ink-50 placeholder:text-ink-300 focus:outline-none focus:border-[#7cd1ff]/40"
          />
          <textarea
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            placeholder="Description (optional)…"
            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-[12px] text-ink-50 placeholder:text-ink-300 resize-none focus:outline-none focus:border-[#7cd1ff]/40"
            rows={2}
          />
          <div className="flex gap-2 items-center">
            <div className="flex gap-1.5">
              {['critical', 'high', 'medium', 'low', 'background'].map((p) => (
                <button
                  key={p}
                  onClick={() => setNewPriority(p)}
                  className={`px-2 py-1 text-[9px] rounded-lg ${
                    newPriority === p ? PRIORITY_COLORS[p] : 'glass-inset'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
            <button
              onClick={createGoal}
              disabled={!newTitle.trim()}
              className="ml-auto px-4 py-1.5 text-[11px] rounded-xl glass-strong hover:bg-white/10 disabled:opacity-40"
            >
              Add
            </button>
          </div>
        </div>
      </section>

      {/* Goal list */}
      <section className="glass rounded-2xl p-5">
        <h3 className="text-sm font-display mb-3">Goals ({goals.length})</h3>
        {goals.length === 0 && (
          <p className="text-[12px] text-ink-300">No goals yet. Add one above.</p>
        )}
        <div className="space-y-2">
          {goals.map((g) => (
            <div key={g.id} className="glass-inset rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className={`text-[9px] uppercase px-1.5 py-0.5 rounded ${PRIORITY_COLORS[g.priority] || ''}`}>{g.priority}</span>
                  <span className={`text-[9px] uppercase px-1.5 py-0.5 rounded ${STATUS_COLORS[g.status] || ''}`}>{g.status}</span>
                  <span className="text-[12px] text-ink-100 font-medium">{g.title}</span>
                </div>
                <button
                  onClick={() => deleteGoal(g.id)}
                  className="text-[10px] text-ink-300 hover:text-red-400 px-1"
                >
                  ×
                </button>
              </div>
              {g.description && <p className="text-[10px] text-ink-200 mb-1">{g.description.slice(0, 200)}</p>}
              {g.progress > 0 && g.progress < 1 && (
                <div className="w-full h-1 bg-white/10 rounded-full mt-1">
                  <div className="h-full bg-[#7cd1ff]/60 rounded-full" style={{ width: `${g.progress * 100}%` }} />
                </div>
              )}
              {g.error && <p className="text-[10px] text-red-400 mt-1">{g.error.slice(0, 200)}</p>}
              {g.result && g.status === 'completed' && (
                <p className="text-[10px] text-green-400 mt-1">{g.result.slice(0, 200)}</p>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
