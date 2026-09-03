import React, { useState } from 'react';
import { Header } from '../components/Header';
import { CopilotDrawer } from '../components/CopilotDrawer';
import { ScenarioId, GlobalGridStatus } from '../types';

export type ScreenTab = 'command_center' | 'feeder_intelligence' | 'prevention_center' | 'what_if_simulator';

interface DashboardLayoutProps {
  activeScreen: ScreenTab;
  onScreenChange: (tab: ScreenTab) => void;
  activeScenarioId: ScenarioId;
  onScenarioChange: (id: ScenarioId) => void;
  isMitigated: boolean;
  gridStatus: GlobalGridStatus;
  selectedFeederId: string;
  children: React.ReactNode;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({
  activeScreen,
  onScreenChange,
  activeScenarioId,
  onScenarioChange,
  isMitigated,
  gridStatus,
  selectedFeederId,
  children,
}) => {
  const [isCopilotOpen, setIsCopilotOpen] = useState<boolean>(false);

  return (
    <div className="min-h-screen bg-energy-atmosphere text-[#102A2A] flex flex-col font-sans relative antialiased">
      <Header
        activeScreen={activeScreen}
        onScreenChange={onScreenChange}
        activeScenarioId={activeScenarioId}
        onScenarioChange={onScenarioChange}
        isMitigated={isMitigated}
        gridStatus={gridStatus}
        selectedFeederId={selectedFeederId}
        onOpenCopilot={() => setIsCopilotOpen(true)}
      />

      {/* Main Editorial Canvas with Generous Spacing */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 lg:py-10">
        {children}
      </main>

      {/* Subtle Energy Footer & Product Loop */}
      <footer className="border-t border-slate-200/60 py-4 px-4 sm:px-6 text-xs text-slate-400">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2.5 sm:gap-3 text-center sm:text-left">
          <div className="flex flex-wrap items-center justify-center sm:justify-start gap-1.5 font-mono text-[10px] sm:text-[11px] text-slate-500">
            <span className="w-1.5 h-1.5 rounded-full bg-teal-600 inline-block"></span>
            <span>GRIDGUARD OPERATIONS ENGINE</span>
            <span className="text-slate-300 hidden sm:inline">|</span>
            <span className="tracking-wider">SCADA TELEMETRY SYNCHRONIZED</span>
          </div>

          {/* Core Loop Indicator */}
          <div className="flex flex-wrap items-center justify-center gap-1 sm:gap-1.5 text-[10px] sm:text-[11px] font-semibold text-slate-400">
            <span className={activeScreen === 'command_center' ? 'text-teal-700 font-bold' : ''}>FORECAST</span>
            <span>→</span>
            <span className={activeScreen === 'feeder_intelligence' ? 'text-teal-700 font-bold' : ''}>EXPLAIN</span>
            <span>→</span>
            <span className={activeScreen === 'prevention_center' ? 'text-teal-700 font-bold' : ''}>DECIDE</span>
            <span>→</span>
            <span className={activeScreen === 'what_if_simulator' ? 'text-teal-700 font-bold' : ''}>SIMULATE</span>
            <span>→</span>
            <span className={isMitigated ? 'text-emerald-700 font-bold' : ''}>PREVENT</span>
          </div>
        </div>
      </footer>

      {/* Secondary Copilot Slide-Over Drawer */}
      <CopilotDrawer
        isOpen={isCopilotOpen}
        onClose={() => setIsCopilotOpen(false)}
        activeFeederId={selectedFeederId}
      />
    </div>
  );
};
