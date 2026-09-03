import React, { useState } from 'react';
import { useGridState } from './hooks/useGridState';
import { DashboardLayout, ScreenTab } from './layouts/DashboardLayout';
import { CommandCenter } from './pages/CommandCenter';
import { FeederIntelligence } from './pages/FeederIntelligence';
import { PreventionCenter } from './pages/PreventionCenter';
import { WhatIfSimulator } from './pages/WhatIfSimulator';
import { AlertTriangle, RotateCcw } from 'lucide-react';

export function App() {
  const [activeScreen, setActiveScreen] = useState<ScreenTab>('command_center');

  const {
    activeScenarioId,
    changeScenario,
    selectedFeederId,
    setSelectedFeederId,
    feeders,
    activeFeeder,
    isLoading,
    error,
    isMitigated,
    mitigatedFeederId,
    applyMitigation,
    resetMitigation,
    reloadFeeders,
  } = useGridState();

  // Data-driven "is there an active overload risk right now" signal for the
  // header -- not tied to any specific hardcoded feeder id.
  const hasActiveOverloadRisk = feeders.some(
    f => f.id !== mitigatedFeederId && (f.riskLevel === 'CRITICAL' || f.riskLevel === 'HIGH')
  );

  const handleNavigateToIntelligence = (feederId: string) => {
    setSelectedFeederId(feederId);
    setActiveScreen('feeder_intelligence');
  };

  const handleNavigateToPrevention = () => {
    setActiveScreen('prevention_center');
  };

  return (
    <DashboardLayout
      activeScreen={activeScreen}
      onScreenChange={setActiveScreen}
      activeScenarioId={activeScenarioId}
      onScenarioChange={changeScenario}
      isMitigated={isMitigated}
      hasActiveOverloadRisk={hasActiveOverloadRisk}
      selectedFeederId={selectedFeederId}
    >
      {isLoading ? (
        <div className="h-72 flex flex-col items-center justify-center space-y-3 text-slate-500">
          <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
          <span className="text-xs font-medium">Loading telemetry streams...</span>
        </div>
      ) : error ? (
        <div className="h-80 flex flex-col items-center justify-center text-center px-4 space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-red-50 border border-red-200 text-red-600 flex items-center justify-center shadow-xs">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h2 className="text-lg font-bold text-slate-900 font-display">Telemetry stream offline</h2>
            <p className="text-xs text-slate-500 max-w-sm leading-relaxed">
              Unable to retrieve the latest grid data. Verify SCADA telemetry connection.
            </p>
          </div>
          <button
            onClick={reloadFeeders}
            className="px-4 py-2.5 rounded-xl bg-[#073B3A] hover:bg-[#0B5D56] text-white text-xs font-bold transition-all shadow-sm flex items-center space-x-1.5 cursor-pointer min-h-[44px]"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Retry Connection</span>
          </button>
        </div>
      ) : (
        <>
          {activeScreen === 'command_center' && (
            <CommandCenter
              feeders={feeders}
              selectedFeederId={selectedFeederId}
              onSelectFeeder={setSelectedFeederId}
              onNavigateToIntelligence={handleNavigateToIntelligence}
              onNavigateToPrevention={handleNavigateToPrevention}
              mitigatedFeederId={mitigatedFeederId}
            />
          )}

          {activeScreen === 'feeder_intelligence' && (
            <FeederIntelligence
              feeder={activeFeeder}
              allFeeders={feeders}
              onSelectFeeder={setSelectedFeederId}
              onNavigateToPrevention={handleNavigateToPrevention}
              isMitigated={isMitigated && activeFeeder?.id === mitigatedFeederId}
            />
          )}

          {activeScreen === 'prevention_center' && (
            <PreventionCenter
              feederId={selectedFeederId}
              isMitigated={isMitigated && selectedFeederId === mitigatedFeederId}
              onApplyMitigation={() => applyMitigation(selectedFeederId)}
              onResetMitigation={resetMitigation}
            />
          )}

          {activeScreen === 'what_if_simulator' && (
            <WhatIfSimulator
              feederId={selectedFeederId}
              onNavigateToPrevention={handleNavigateToPrevention}
            />
          )}
        </>
      )}
    </DashboardLayout>
  );
}

export default App;
