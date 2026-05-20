import { useState } from 'react';
import { apiJSON } from '../api';

type Strategy = {
  id: string;
  label: string;
  description: string;
};

type SolveResult = {
  answer: string;
  strategy_used: string;
  complexity: {
    estimated_difficulty: number;
    requires_decomposition: boolean;
    requires_debate: boolean;
    safety_sensitive: boolean;
    requires_precision: boolean;
    recommended_strategy: string;
    reasoning: string;
  };
  tot_result?: {
    best_chain: string[];
    total_nodes_explored: number;
    max_depth_reached: number;
  } | null;
  reflexion_result?: {
    trials: { trial_number: number; score: number; passed: boolean; reflection: string }[];
    converged: boolean;
  } | null;
  debate_result?: {
    rounds: { round_num: number; arguments: { debater_id: number; argument: string }[] }[];
    converged: boolean;
    judge_reasoning: string;
  } | null;
  constitutional_result?: {
    rounds: { round_num: number; violations: { principle: string; violated: boolean }[] }[];
    all_principles_satisfied: boolean;
  } | null;
};

export function ReasoningPanel() {
  const [task, setTask] = useState('');
  const [strategy, setStrategy] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SolveResult | null>(null);
  const [error, setError] = useState('');

  const strategies: Strategy[] = [
    { id: '', label: 'Auto', description: 'Let the system choose' },
    { id: 'direct', label: 'Direct', description: 'Single-shot answer' },
    { id: 'tree_of_thoughts', label: 'Tree of Thoughts', description: 'Multi-branch exploration' },
    { id: 'reflexion', label: 'Reflexion', description: 'Iterative self-critique' },
    { id: 'debate', label: 'Debate', description: 'Multi-agent argumentation' },
    { id: 'constitutional', label: 'Constitutional', description: 'Principle-based critique' },
    { id: 'full_pipeline', label: 'Full Pipeline', description: 'All strategies combined' },
  ];

  const solve = async () => {
    if (!task.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const r = await apiJSON<SolveResult>('/reasoning/solve', {
        method: 'POST',
        body: JSON.stringify({
          task: task.trim(),
          strategy: strategy || undefined,
        }),
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-4 overflow-y-auto scrollbar-thin max-h-full">
      <section className="glass rounded-2xl p-5">
        <h3 className="text-sm font-display mb-3">Reasoning Engine</h3>
        <p className="text-[11px] text-ink-200 mb-3">
          Advanced deliberative reasoning based on Tree of Thoughts, Reflexion, Multi-Agent Debate, and Constitutional AI research.
        </p>

        {/* Strategy selector */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {strategies.map((s) => (
            <button
              key={s.id}
              onClick={() => setStrategy(s.id)}
              className={`px-2.5 py-1 text-[10px] rounded-lg transition-colors ${
                strategy === s.id
                  ? 'bg-[#b58cff]/30 text-[#b58cff] border border-[#b58cff]/30'
                  : 'glass-inset hover:bg-white/10'
              }`}
              title={s.description}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* Task input */}
        <div className="flex gap-2">
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Enter a complex problem to analyze..."
            className="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-[12px] text-ink-50 placeholder:text-ink-300 resize-none focus:outline-none focus:border-[#b58cff]/40"
            rows={3}
          />
          <button
            onClick={solve}
            disabled={loading || !task.trim()}
            className="px-4 py-2 text-xs rounded-xl glass-strong hover:bg-white/10 disabled:opacity-40 self-end"
          >
            {loading ? 'Thinking…' : 'Solve'}
          </button>
        </div>

        {error && <p className="text-red-400 text-[11px] mt-2">{error}</p>}
      </section>

      {/* Results */}
      {result && (
        <>
          {/* Complexity Analysis */}
          <section className="glass rounded-2xl p-5">
            <h4 className="text-[12px] font-display mb-2">Complexity Analysis</h4>
            <div className="flex gap-3 flex-wrap">
              <div className="glass-inset rounded-lg px-3 py-2">
                <div className="text-[10px] text-ink-300">Difficulty</div>
                <div className="text-sm font-mono text-ink-50">{(result.complexity.estimated_difficulty * 100).toFixed(0)}%</div>
              </div>
              <div className="glass-inset rounded-lg px-3 py-2">
                <div className="text-[10px] text-ink-300">Strategy</div>
                <div className="text-sm font-mono text-[#b58cff]">{result.strategy_used.replace(/_/g, ' ')}</div>
              </div>
              <div className="glass-inset rounded-lg px-3 py-2 flex gap-2">
                {result.complexity.requires_decomposition && <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300">Decomp</span>}
                {result.complexity.requires_debate && <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300">Debate</span>}
                {result.complexity.safety_sensitive && <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">Safety</span>}
                {result.complexity.requires_precision && <span className="text-[9px] px-1.5 py-0.5 rounded bg-green-500/20 text-green-300">Precision</span>}
              </div>
            </div>
          </section>

          {/* ToT visualization */}
          {result.tot_result && (
            <section className="glass rounded-2xl p-5">
              <h4 className="text-[12px] font-display mb-2">Tree of Thoughts</h4>
              <div className="flex gap-3 mb-2">
                <span className="text-[10px] text-ink-300">Nodes explored: {result.tot_result.total_nodes_explored}</span>
                <span className="text-[10px] text-ink-300">Max depth: {result.tot_result.max_depth_reached}</span>
              </div>
              <div className="space-y-1">
                {result.tot_result.best_chain.map((step, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-[10px] text-[#7cd1ff] font-mono shrink-0">
                      {i === 0 ? 'ROOT' : `L${i}`}
                    </span>
                    <span className="text-[11px] text-ink-100">{step.slice(0, 200)}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Reflexion visualization */}
          {result.reflexion_result && (
            <section className="glass rounded-2xl p-5">
              <h4 className="text-[12px] font-display mb-2">
                Reflexion
                <span className={`ml-2 text-[9px] px-1.5 py-0.5 rounded ${result.reflexion_result.converged ? 'bg-green-500/20 text-green-300' : 'bg-amber-500/20 text-amber-300'}`}>
                  {result.reflexion_result.converged ? 'Converged' : 'Max trials'}
                </span>
              </h4>
              <div className="space-y-2">
                {result.reflexion_result.trials.map((t) => (
                  <div key={t.trial_number} className="glass-inset rounded-lg p-3">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-[10px] text-ink-300">Trial {t.trial_number}</span>
                      <span className={`text-[10px] font-mono ${t.passed ? 'text-green-400' : 'text-amber-400'}`}>
                        Score: {t.score.toFixed(2)}
                      </span>
                    </div>
                    {t.reflection && (
                      <p className="text-[10px] text-ink-200 italic">{t.reflection.slice(0, 200)}</p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Debate visualization */}
          {result.debate_result && (
            <section className="glass rounded-2xl p-5">
              <h4 className="text-[12px] font-display mb-2">
                Multi-Agent Debate
                <span className={`ml-2 text-[9px] px-1.5 py-0.5 rounded ${result.debate_result.converged ? 'bg-green-500/20 text-green-300' : 'bg-blue-500/20 text-blue-300'}`}>
                  {result.debate_result.converged ? 'Consensus' : 'Judge decided'}
                </span>
              </h4>
              {result.debate_result.rounds.map((round) => (
                <div key={round.round_num} className="mb-2">
                  <div className="text-[10px] text-ink-300 mb-1">Round {round.round_num}</div>
                  <div className="grid grid-cols-1 gap-1">
                    {round.arguments.map((arg, i) => (
                      <div key={i} className="glass-inset rounded-lg p-2">
                        <span className="text-[9px] text-[#b58cff] font-mono">D{arg.debater_id + 1}</span>
                        <p className="text-[10px] text-ink-200 mt-0.5">{arg.argument.slice(0, 150)}…</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          )}

          {/* Constitutional visualization */}
          {result.constitutional_result && (
            <section className="glass rounded-2xl p-5">
              <h4 className="text-[12px] font-display mb-2">
                Constitutional Critique
                <span className={`ml-2 text-[9px] px-1.5 py-0.5 rounded ${result.constitutional_result.all_principles_satisfied ? 'bg-green-500/20 text-green-300' : 'bg-amber-500/20 text-amber-300'}`}>
                  {result.constitutional_result.all_principles_satisfied ? 'All passed' : 'Revised'}
                </span>
              </h4>
              {result.constitutional_result.rounds.map((round) => (
                <div key={round.round_num} className="mb-2">
                  <div className="text-[10px] text-ink-300 mb-1">Round {round.round_num}</div>
                  <div className="space-y-0.5">
                    {round.violations.map((v, i) => (
                      <div key={i} className="flex items-center gap-2 text-[10px]">
                        <span className={v.violated ? 'text-red-400' : 'text-green-400'}>
                          {v.violated ? '✗' : '✓'}
                        </span>
                        <span className="text-ink-200">{v.principle.slice(0, 80)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          )}

          {/* Final answer */}
          <section className="glass-strong rounded-2xl p-5">
            <h4 className="text-[12px] font-display mb-2 shimmer-text">Final Answer</h4>
            <div className="text-[12px] text-ink-100 whitespace-pre-wrap leading-relaxed">
              {result.answer}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
