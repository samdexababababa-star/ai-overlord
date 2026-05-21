import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { ChatPanel } from './components/ChatPanel';
import { AgentOffice } from './components/AgentOffice';
import { OnboardingWizard } from './components/OnboardingWizard';
import { SettingsPanel } from './components/SettingsPanel';
import { ToolsPanel } from './components/ToolsPanel';
import { MemoryPanel } from './components/MemoryPanel';
import { ReasoningPanel } from './components/ReasoningPanel';
import { AutonomyPanel } from './components/AutonomyPanel';
import { WebAIPanel } from './components/WebAIPanel';
import { useStore } from './store';

function ViewSwitch() {
  const view = useStore((s) => s.view);
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={view}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.18 }}
        className="flex-1 overflow-hidden flex flex-col"
      >
        {view === 'chat' && <ChatPanel />}
        {view === 'office' && <AgentOffice />}
        {view === 'memory' && <MemoryPanel />}
        {view === 'tools' && <ToolsPanel />}
        {view === 'reasoning' && <ReasoningPanel />}
        {view === 'autonomy' && <AutonomyPanel />}
        {view === 'webai' && <WebAIPanel />}
        {view === 'settings' && <SettingsPanel />}
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  const init = useStore((s) => s.init);
  useEffect(() => { init(); }, [init]);

  return (
    <div className="flex h-screen w-screen text-ink-50 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <TopBar />
        <ViewSwitch />
      </div>
      <OnboardingWizard />
    </div>
  );
}
