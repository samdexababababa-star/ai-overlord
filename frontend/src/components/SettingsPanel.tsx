import { useEffect, useState } from 'react';
import { apiJSON } from '../api';
import { useStore } from '../store';

type Settings = {
  startup: {
    open_at_login: boolean;
    start_minimized: boolean;
    auto_start_backend: boolean;
    auto_start_autonomy: boolean;
  };
  hitl: {
    enabled: boolean;
    shell_commands: boolean;
    browser_actions: boolean;
    file_writes: boolean;
    financial_actions: boolean;
    account_creation: boolean;
    email_sending: boolean;
    api_calls: boolean;
    auto_approve_safe: boolean;
  };
  autonomy: {
    level: 'guided' | 'supervised' | 'autonomous';
    max_actions_per_minute: number;
    max_cost_per_day_usd: number;
    allow_background_tasks: boolean;
    auto_restart_on_failure: boolean;
    pause_on_error: boolean;
    require_approval_above_cost: number;
  };
  council: {
    default_strategy: string;
    enable_tree_of_thoughts: boolean;
    enable_reflexion: boolean;
    enable_debate: boolean;
    enable_constitutional: boolean;
    tot_max_depth: number;
    tot_branching_factor: number;
    reflexion_max_trials: number;
    reflexion_threshold: number;
    debate_num_debaters: number;
    debate_max_rounds: number;
    fast_mode_threshold: number;
  };
  memory: {
    enable_episodic: boolean;
    enable_semantic: boolean;
    enable_knowledge_graph: boolean;
    enable_procedural: boolean;
    consolidation_interval_hours: number;
    auto_extract_entities: boolean;
  };
  ui: {
    theme: 'dark' | 'light' | 'auto';
    show_agent_thoughts: boolean;
    show_reasoning_details: boolean;
    show_cost_tracker: boolean;
    compact_mode: boolean;
    animations_enabled: boolean;
    notification_sound: boolean;
  };
};

function Toggle({ label, checked, onChange, description }: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  description?: string;
}) {
  return (
    <label className="flex items-center justify-between py-1.5 cursor-pointer group">
      <div>
        <span className="text-[12px] text-ink-100 group-hover:text-ink-50">{label}</span>
        {description && <p className="text-[10px] text-ink-300 mt-0.5">{description}</p>}
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`w-10 h-5 rounded-full transition-colors ${checked ? 'bg-[#7cd1ff]/60' : 'bg-white/10'}`}
      >
        <span className={`block w-4 h-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : 'translate-x-0.5'}`} />
      </button>
    </label>
  );
}

function Section({ title, children, collapsed: initialCollapsed = false }: {
  title: string;
  children: React.ReactNode;
  collapsed?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(initialCollapsed);
  return (
    <section className="glass rounded-2xl overflow-hidden">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-5 py-3 hover:bg-white/5"
      >
        <h3 className="text-sm font-display">{title}</h3>
        <span className="text-ink-300 text-xs">{collapsed ? '▶' : '▼'}</span>
      </button>
      {!collapsed && <div className="px-5 pb-4 space-y-1">{children}</div>}
    </section>
  );
}

export function SettingsPanel() {
  const configured = useStore((s) => s.configuredKeys);
  const models = useStore((s) => s.models);
  const setShow = useStore((s) => s.setShowOnboarding);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  const [autoStart, setAutoStart] = useState<boolean | null>(null);
  const [platformInfo, setPlatformInfo] = useState<{ os: string; isPackaged: boolean } | null>(null);

  const totalKeys = Object.values(configured).reduce((n, arr) => n + arr.length, 0);

  useEffect(() => {
    apiJSON<Settings>('/settings').then(setSettings).catch(() => {});
    if (window.overlord?.platform) {
      window.overlord.platform().then((p) => setPlatformInfo({ os: p.os, isPackaged: p.isPackaged })).catch(() => {});
    }
    if (window.overlord?.autoStart) {
      window.overlord.autoStart.get().then(setAutoStart).catch(() => {});
    }
  }, []);

  const patch = async (path: string, value: unknown) => {
    if (!settings) return;
    setSaving(true);
    const parts = path.split('.');
    const update: Record<string, unknown> = {};
    let current = update;
    for (let i = 0; i < parts.length - 1; i++) {
      current[parts[i]] = {};
      current = current[parts[i]] as Record<string, unknown>;
    }
    current[parts[parts.length - 1]] = value;

    try {
      const updated = await apiJSON<Settings>('/settings', {
        method: 'PATCH',
        body: JSON.stringify(update),
      });
      setSettings(updated);
    } catch {
      // silently fail
    } finally {
      setSaving(false);
    }
  };

  const toggleAutoStart = async (enabled: boolean) => {
    if (!window.overlord?.autoStart) return;
    try {
      await window.overlord.autoStart.set(enabled);
      setAutoStart(enabled);
      if (settings) await patch('startup.open_at_login', enabled);
    } catch (e) {
      console.error('autoStart toggle failed', e);
    }
  };

  return (
    <div className="p-6 space-y-4 overflow-y-auto scrollbar-thin max-h-full">
      {saving && (
        <div className="fixed top-4 right-4 glass px-3 py-1.5 rounded-lg text-[11px] text-ink-200 z-50">
          Saving…
        </div>
      )}

      {/* API Keys */}
      <Section title={`API Keys (${totalKeys})`}>
        <p className="text-[12px] text-ink-200 mb-3">
          {totalKeys} key(s) across {Object.keys(configured).length} provider(s). Keys rotate on quota errors.
        </p>
        <button
          onClick={() => setShow(true)}
          className="px-4 py-2 text-xs rounded-xl glass-strong hover:bg-white/10"
        >
          Manage providers & keys
        </button>
      </Section>

      {/* Models */}
      <Section title={`Models (${models.length})`} collapsed>
        <div className="grid grid-cols-2 gap-2">
          {models.map((m) => (
            <div key={`${m.provider}-${m.id}`} className="glass-inset rounded-lg px-3 py-2 text-[11px]">
              <div className="font-mono text-ink-100">{m.label}</div>
              <div className="text-ink-300 text-[10px]">{m.provider} · {m.capabilities.join(', ')} · ctx {m.context_window.toLocaleString()}</div>
            </div>
          ))}
          {models.length === 0 && (
            <div className="text-ink-300 text-xs col-span-2">No models — add a provider key first.</div>
          )}
        </div>
      </Section>

      {/* Autonomy */}
      {settings && (
        <>
          <Section title="Autonomy">
            <div className="space-y-2">
              <div>
                <span className="text-[11px] text-ink-200 block mb-1">Autonomy Level</span>
                <div className="flex gap-2">
                  {(['guided', 'supervised', 'autonomous'] as const).map((level) => (
                    <button
                      key={level}
                      onClick={() => patch('autonomy.level', level)}
                      className={`px-3 py-1.5 text-[11px] rounded-lg transition-colors ${
                        settings.autonomy.level === level
                          ? 'bg-[#7cd1ff]/30 text-[#7cd1ff] border border-[#7cd1ff]/30'
                          : 'glass-inset hover:bg-white/10'
                      }`}
                    >
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                    </button>
                  ))}
                </div>
                <p className="text-[10px] text-ink-300 mt-1">
                  {settings.autonomy.level === 'guided' && 'All actions require approval.'}
                  {settings.autonomy.level === 'supervised' && 'Safe actions auto-approved; risky ones need confirmation.'}
                  {settings.autonomy.level === 'autonomous' && 'Full autonomy — all actions execute without approval.'}
                </p>
              </div>
              <Toggle
                label="Allow background tasks"
                checked={settings.autonomy.allow_background_tasks}
                onChange={(v) => patch('autonomy.allow_background_tasks', v)}
              />
              <Toggle
                label="Auto-restart on failure"
                checked={settings.autonomy.auto_restart_on_failure}
                onChange={(v) => patch('autonomy.auto_restart_on_failure', v)}
              />
              <Toggle
                label="Pause on error"
                checked={settings.autonomy.pause_on_error}
                onChange={(v) => patch('autonomy.pause_on_error', v)}
                description="Pause autonomy loop after repeated failures"
              />
              <div>
                <span className="text-[11px] text-ink-200 block mb-1">
                  Max cost/day: ${settings.autonomy.max_cost_per_day_usd.toFixed(2)}
                </span>
                <input
                  type="range"
                  min={0} max={50} step={0.5}
                  value={settings.autonomy.max_cost_per_day_usd}
                  onChange={(e) => patch('autonomy.max_cost_per_day_usd', Number(e.target.value))}
                  className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer"
                />
              </div>
            </div>
          </Section>

          {/* HITL Controls */}
          <Section title="Human-in-the-Loop" collapsed>
            <Toggle
              label="HITL enabled globally"
              checked={settings.hitl.enabled}
              onChange={(v) => patch('hitl.enabled', v)}
              description="Master switch for all confirmation prompts"
            />
            {settings.hitl.enabled && (
              <div className="ml-2 border-l border-white/10 pl-3 space-y-0.5">
                <Toggle label="Shell commands" checked={settings.hitl.shell_commands} onChange={(v) => patch('hitl.shell_commands', v)} />
                <Toggle label="Browser actions" checked={settings.hitl.browser_actions} onChange={(v) => patch('hitl.browser_actions', v)} />
                <Toggle label="File writes" checked={settings.hitl.file_writes} onChange={(v) => patch('hitl.file_writes', v)} />
                <Toggle label="Financial actions" checked={settings.hitl.financial_actions} onChange={(v) => patch('hitl.financial_actions', v)} />
                <Toggle label="Account creation" checked={settings.hitl.account_creation} onChange={(v) => patch('hitl.account_creation', v)} />
                <Toggle label="Email sending" checked={settings.hitl.email_sending} onChange={(v) => patch('hitl.email_sending', v)} />
                <Toggle label="API calls" checked={settings.hitl.api_calls} onChange={(v) => patch('hitl.api_calls', v)} />
                <Toggle label="Auto-approve safe" checked={settings.hitl.auto_approve_safe} onChange={(v) => patch('hitl.auto_approve_safe', v)} description="Automatically approve low-risk actions" />
              </div>
            )}
          </Section>

          {/* Council / Reasoning */}
          <Section title="Reasoning Engine" collapsed>
            <div className="space-y-1">
              <Toggle label="Tree of Thoughts" checked={settings.council.enable_tree_of_thoughts} onChange={(v) => patch('council.enable_tree_of_thoughts', v)} description="Explore multiple reasoning branches (Yao et al. 2023)" />
              <Toggle label="Reflexion" checked={settings.council.enable_reflexion} onChange={(v) => patch('council.enable_reflexion', v)} description="Iterative self-critique loop (Shinn et al. 2023)" />
              <Toggle label="Multi-Agent Debate" checked={settings.council.enable_debate} onChange={(v) => patch('council.enable_debate', v)} description="Multiple agents argue positions (Du et al. 2023)" />
              <Toggle label="Constitutional AI" checked={settings.council.enable_constitutional} onChange={(v) => patch('council.enable_constitutional', v)} description="Self-critique against principles (Bai et al. 2022)" />
              <div className="mt-2">
                <span className="text-[11px] text-ink-200 block mb-1">
                  Fast mode threshold: {settings.council.fast_mode_threshold}
                </span>
                <input
                  type="range"
                  min={0} max={1} step={0.05}
                  value={settings.council.fast_mode_threshold}
                  onChange={(e) => patch('council.fast_mode_threshold', Number(e.target.value))}
                  className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer"
                />
                <p className="text-[10px] text-ink-300">Below this complexity, skip deep reasoning</p>
              </div>
            </div>
          </Section>

          {/* Memory */}
          <Section title="Memory" collapsed>
            <Toggle label="Episodic memory" checked={settings.memory.enable_episodic} onChange={(v) => patch('memory.enable_episodic', v)} />
            <Toggle label="Semantic memory" checked={settings.memory.enable_semantic} onChange={(v) => patch('memory.enable_semantic', v)} />
            <Toggle label="Knowledge graph" checked={settings.memory.enable_knowledge_graph} onChange={(v) => patch('memory.enable_knowledge_graph', v)} />
            <Toggle label="Procedural memory" checked={settings.memory.enable_procedural} onChange={(v) => patch('memory.enable_procedural', v)} />
            <Toggle label="Auto-extract entities" checked={settings.memory.auto_extract_entities} onChange={(v) => patch('memory.auto_extract_entities', v)} description="Extract entities from conversations for the knowledge graph" />
            <div className="mt-2">
              <span className="text-[11px] text-ink-200 block mb-1">
                Consolidation interval: {settings.memory.consolidation_interval_hours}h
              </span>
              <input
                type="range"
                min={1} max={48} step={1}
                value={settings.memory.consolidation_interval_hours}
                onChange={(e) => patch('memory.consolidation_interval_hours', Number(e.target.value))}
                className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer"
              />
            </div>
          </Section>

          {/* UI Preferences */}
          <Section title="Interface" collapsed>
            <Toggle label="Show agent thoughts" checked={settings.ui.show_agent_thoughts} onChange={(v) => patch('ui.show_agent_thoughts', v)} />
            <Toggle label="Show reasoning details" checked={settings.ui.show_reasoning_details} onChange={(v) => patch('ui.show_reasoning_details', v)} />
            <Toggle label="Show cost tracker" checked={settings.ui.show_cost_tracker} onChange={(v) => patch('ui.show_cost_tracker', v)} />
            <Toggle label="Compact mode" checked={settings.ui.compact_mode} onChange={(v) => patch('ui.compact_mode', v)} />
            <Toggle label="Animations" checked={settings.ui.animations_enabled} onChange={(v) => patch('ui.animations_enabled', v)} />
            <Toggle label="Notification sound" checked={settings.ui.notification_sound} onChange={(v) => patch('ui.notification_sound', v)} />
          </Section>
        </>
      )}

      {/* System & Startup */}
      {settings && (
        <Section title="System & Startup">
          <div className="text-[11px] text-ink-300 mb-2">
            {platformInfo ? (
              <>Detected: <span className="font-mono text-ink-100">{platformInfo.os}</span> · {platformInfo.isPackaged ? 'packaged build' : 'development mode'}</>
            ) : (
              <>Running in browser (no Electron bridge)</>
            )}
          </div>
          <Toggle
            label={`Open at login (${platformInfo?.os === 'win32' ? 'Windows 11 Startup folder' : platformInfo?.os === 'darwin' ? 'macOS LaunchAgent' : 'Linux XDG autostart'})`}
            checked={!!autoStart}
            onChange={toggleAutoStart}
            description="Launch AI Overlord automatically when you sign in"
          />
          <Toggle
            label="Start minimized"
            checked={settings.startup.start_minimized}
            onChange={(v) => patch('startup.start_minimized', v)}
            description="Open hidden in the tray on startup"
          />
          <Toggle
            label="Auto-start backend with the app"
            checked={settings.startup.auto_start_backend}
            onChange={(v) => patch('startup.auto_start_backend', v)}
            description="Spawn the FastAPI backend when Electron launches"
          />
          <Toggle
            label="Auto-start autonomy loop"
            checked={settings.startup.auto_start_autonomy}
            onChange={(v) => patch('startup.auto_start_autonomy', v)}
            description="Resume 24/7 goal pursuit when the app launches"
          />
        </Section>
      )}

      {/* About */}
      <Section title="About" collapsed>
        <p className="text-[12px] text-ink-200">
          AI Overlord v0.2.0 — Autonomous multi-provider council with advanced reasoning.
        </p>
        <p className="text-[10px] text-ink-300 mt-1">
          Tree of Thoughts · Reflexion · Debate · Constitutional AI · Knowledge Graph
        </p>
      </Section>
    </div>
  );
}
