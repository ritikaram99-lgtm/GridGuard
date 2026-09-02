import React, { useState, useEffect } from 'react';
import { Feeder, ForecastPoint } from '../types';
import { gridService } from '../api/gridService';
import { RiskBadge } from '../components/RiskBadge';
import { StressScoreGauge } from '../components/StressScoreGauge';
import { CollapsibleSection } from '../components/CollapsibleSection';
import { GridMap } from '../map/GridMap';
import { ForecastHorizonChart } from '../charts/ForecastHorizonChart';
import { MOCK_RECENT_EVENTS } from '../data/eventsMock';
import { formatMw } from '../utils/formatters';
import { 
  AlertCircle, 
  CheckCircle2, 
  ArrowRight, 
  ChevronRight, 
  AlertTriangle, 
  Info,
} from 'lucide-react';

type CollapsibleTab = 'ranking' | 'forecast' | 'events';

interface CommandCenterProps {
  feeders: Feeder[];
  selectedFeederId: string;
  onSelectFeeder: (id: string) => void;
  onNavigateToIntelligence: (feederId: string) => void;
  onNavigateToPrevention: () => void;
  isMitigated: boolean;
}

export const CommandCenter: React.FC<CommandCenterProps> = ({
  feeders,
  selectedFeederId,
  onSelectFeeder,
  onNavigateToIntelligence,
  onNavigateToPrevention,
  isMitigated,
}) => {
  const [activeSection, setActiveSection] = useState<CollapsibleTab | null>(null);
  const [forecastData, setForecastData] = useState<ForecastPoint[]>([]);

  // Feeder F07 specific telemetry
  const f07 = feeders.find(f => f.id === 'F07') || feeders[0];

  // Prioritize critical feeders first
  const sortedFeeders = [...feeders].sort((a, b) => {
    if (a.id === 'F07') return -1;
    if (b.id === 'F07') return 1;
    return b.stressScore - a.stressScore;
  });

  const criticalCount = feeders.filter(f => f.riskLevel === 'CRITICAL').length;

  useEffect(() => {
    const loadForecast = async () => {
      const data = await gridService.getForecast('F07');
      setForecastData(data);
    };
    loadForecast();
  }, []);

  const toggleSection = (section: CollapsibleTab) => {
    setActiveSection((prev: CollapsibleTab | null) => (prev === section ? null : section));
  };

  return (
    <div className="space-y-8 sm:space-y-10">
      {/* 1. TOP EDITORIAL HERO STATEMENT */}
      <div className="space-y-2">
        <div className="flex items-center space-x-2 text-[11px] font-bold uppercase tracking-widest-sm text-teal-800">
          <span className="w-2 h-2 rounded-full bg-teal-600"></span>
          <span>Grid Operations / Live Telemetry</span>
        </div>
        <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold text-slate-900 tracking-tight font-display max-w-2xl sm:max-w-3xl leading-[1.15] sm:leading-[1.1]">
          Predicting grid stress before an overload occurs.
        </h1>
        <p className="text-sm sm:text-base text-slate-600 max-w-2xl font-normal leading-relaxed pt-1">
          GridGuard continuously forecasts feeder stress and identifies thermal overload risk before it becomes an outage.
        </p>
      </div>

      {/* 2. ASYMMETRICAL EDITORIAL HERO: F07 ALERT + GRID TOPOLOGY */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* Left: Large Editorial F07 Alert */}
        <div className="lg:col-span-5 bg-white border border-slate-200/90 rounded-2xl p-5 sm:p-7 shadow-xs flex flex-col justify-between space-y-6">
          {!isMitigated && f07.riskLevel === 'CRITICAL' ? (
            <>
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-3xl sm:text-4xl font-extrabold text-slate-900 font-display">
                    F07
                  </span>
                  <span className="px-2.5 py-1 rounded-full bg-red-50 border border-red-200 text-red-700 text-xs font-bold uppercase tracking-wider">
                    Overload Risk
                  </span>
                </div>
                <div className="text-xs text-slate-500 font-medium mt-0.5">
                  Metro Depot & Commercial • Substation Alpha
                </div>

                {/* Major Metrics with Generous Typography */}
                <div className="mt-6 pt-5 border-t border-slate-100 grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                      Current Load
                    </span>
                    <div className="text-2xl sm:text-3xl font-extrabold text-slate-900 font-display mt-0.5">
                      {f07.currentLoadMw} <span className="text-sm font-semibold text-slate-400">/ {f07.capacityMw} MW</span>
                    </div>
                  </div>

                  <div>
                    <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                      Predicted Peak
                    </span>
                    <div className="text-2xl sm:text-3xl font-extrabold text-red-600 font-display mt-0.5">
                      {f07.peakForecastMw} <span className="text-sm font-semibold text-red-400">MW</span>
                    </div>
                  </div>
                </div>

                <div className="mt-5 p-3.5 rounded-xl bg-red-50/60 border border-red-200/80 flex items-start space-x-3">
                  <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
                  <div className="text-xs text-red-800 leading-relaxed">
                    Expected to exceed {f07.capacityMw} MW continuous thermal rating in <strong className="font-bold text-red-950">{f07.timeToOverloadMin ?? 38} minutes</strong>. Immediate load curtailment required.
                  </div>
                </div>
              </div>

              {/* Action Buttons - Stack on mobile, side-by-side on tablet/desktop */}
              <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                <button
                  onClick={onNavigateToPrevention}
                  className="w-full sm:flex-1 px-4 py-3 rounded-xl bg-[#073B3A] hover:bg-[#0B5D56] text-white text-xs font-bold transition-all shadow-sm flex items-center justify-center space-x-1.5 cursor-pointer min-h-[44px]"
                >
                  <span>Prevent Overload</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => onNavigateToIntelligence('F07')}
                  className="w-full sm:w-auto px-4 py-3 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors cursor-pointer min-h-[44px] text-center"
                >
                  Investigate F07
                </button>
              </div>
            </>
          ) : (
            <div className="h-full flex flex-col justify-between py-2">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-3xl sm:text-4xl font-extrabold text-slate-900 font-display">
                    F07
                  </span>
                  <span className="px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold uppercase tracking-wider flex items-center space-x-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Mitigated</span>
                  </span>
                </div>
                <div className="text-xs text-slate-500 font-medium mt-0.5">
                  Metro Depot & Commercial • Substation Alpha
                </div>

                <div className="mt-6 pt-5 border-t border-slate-100">
                  <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                    Operating State After Dispatch
                  </span>
                  <div className="text-3xl font-extrabold text-emerald-700 font-display mt-0.5">
                    94.0 MW <span className="text-sm font-semibold text-emerald-600">(Safe)</span>
                  </div>
                  <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                    Overload averted. Coordinated EV fleet throttling (-5 MW) and Substation BESS discharge (-9 MW) operating at 6% continuous margin.
                  </p>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100">
                <button
                  onClick={() => onNavigateToIntelligence('F07')}
                  className="w-full px-4 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition-colors text-center cursor-pointer min-h-[44px]"
                >
                  Inspect Feeder Telemetry →
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right: Infrastructure Grid Topology Map */}
        <div className="lg:col-span-7 bg-white border border-slate-200/90 rounded-2xl p-3 sm:p-4 shadow-xs flex flex-col justify-between min-h-[340px] sm:min-h-[380px]">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3 px-1">
            <div>
              <h2 className="text-xs uppercase font-bold text-slate-400 tracking-wider">
                Distribution Network Topology
              </h2>
              <span className="text-xs font-semibold text-slate-900">
                10 Feeders • 4 Primary Substations
              </span>
            </div>
            <div className="flex items-center space-x-2 text-xs font-medium text-slate-600">
              <span className="w-2 h-2 rounded-full bg-red-600"></span>
              <span>F07 Overload Hotspot</span>
            </div>
          </div>

          <div className="flex-1 w-full min-h-[300px] sm:min-h-[340px] rounded-xl overflow-hidden">
            <GridMap
              feeders={feeders}
              selectedFeederId={selectedFeederId}
              onSelectFeeder={onSelectFeeder}
              onNavigateToIntelligence={onNavigateToIntelligence}
              isMitigated={isMitigated}
            />
          </div>
        </div>
      </div>

      {/* 3. FOUR KEY OPERATIONAL METRICS (Open 2x2 on Mobile, 4-Column on Desktop) */}
      <div className="py-6 border-y border-slate-200/80 grid grid-cols-2 lg:grid-cols-4 gap-6 sm:gap-8">
        <div>
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Grid Health Index
          </span>
          <div className="text-3xl sm:text-4xl font-extrabold text-slate-900 font-display mt-1">
            {isMitigated ? '99.8%' : '99.2%'}
          </div>
          <span className="text-xs text-emerald-700 font-medium mt-0.5 block">
            Within reliability limits
          </span>
        </div>

        <div className="border-l border-slate-200/80 pl-6 lg:pl-8">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Active Feeders
          </span>
          <div className="text-3xl sm:text-4xl font-extrabold text-slate-900 font-display mt-1">
            {feeders.length}
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            All 4 substations synced
          </span>
        </div>

        <div className="border-t border-slate-200/80 lg:border-t-0 pt-4 lg:pt-0 lg:border-l lg:border-slate-200/80 lg:pl-8">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Feeders At Risk
          </span>
          <div className={`text-3xl sm:text-4xl font-extrabold font-display mt-1 ${!isMitigated && criticalCount > 0 ? 'text-red-600' : 'text-slate-900'}`}>
            {isMitigated ? '0' : criticalCount} <span className="text-sm font-semibold text-slate-400">Critical</span>
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            {isMitigated ? 'All lines nominal' : 'Feeder F07 requires dispatch'}
          </span>
        </div>

        <div className="border-t border-slate-200/80 lg:border-t-0 pt-4 lg:pt-0 border-l border-slate-200/80 pl-6 lg:pl-8">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Peak Forecast
          </span>
          <div className="text-3xl sm:text-4xl font-extrabold text-slate-900 font-display mt-1">
            {isMitigated ? '94' : '108'} <span className="text-sm font-semibold text-slate-400">MW</span>
          </div>
          <span className={`text-xs font-medium mt-0.5 block ${isMitigated ? 'text-emerald-700' : 'text-red-600'}`}>
            {isMitigated ? 'Safe • 6.0 MW margin' : '+8.0 MW over 100 MW limit'}
          </span>
        </div>
      </div>

      {/* 4. PROGRESSIVE DISCLOSURE COLLAPSIBLE ROWS */}
      <div className="space-y-1">
        <div className="text-xs uppercase font-bold text-slate-400 tracking-widest-sm mb-3">
          Detailed Grid Telemetry (Click to Expand)
        </div>

        {/* 1. Feeder Risk Ranking */}
        <CollapsibleSection
          title="FEEDER RISK RANKING"
          subtitle="All 10 monitored feeders prioritized by predictive thermal stress"
          badge={
            <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700">
              10 FEEDERS
            </span>
          }
          isOpen={activeSection === 'ranking'}
          onToggle={() => toggleSection('ranking')}
          headerRight={
            <button
              onClick={(e) => {
                e.stopPropagation();
                onNavigateToIntelligence('F07');
              }}
              className="text-xs font-bold text-teal-800 hover:text-teal-900 hover:underline cursor-pointer"
            >
              View F07 Details →
            </button>
          }
        >
          {/* Desktop & Tablet Table (md+) */}
          <div className="hidden md:block overflow-x-auto pt-2">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500 text-sm font-semibold uppercase tracking-wider">
                  <th className="pb-3.5">Feeder</th>
                  <th className="pb-3.5">Status</th>
                  <th className="pb-3.5">Load</th>
                  <th className="pb-3.5">Capacity</th>
                  <th className="pb-3.5">Stress Score</th>
                  <th className="pb-3.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sortedFeeders.map((f) => {
                  const isF07 = f.id === 'F07';
                  const isSelected = f.id === selectedFeederId;
                  return (
                    <tr
                      key={f.id}
                      onClick={() => onSelectFeeder(f.id)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-teal-50/50' : 'hover:bg-slate-50/80'
                      }`}
                    >
                      <td className="py-3.5">
                        <div className="flex items-center space-x-2.5">
                          <span className="text-[15px] sm:text-base font-bold text-slate-900 font-display">
                            {f.id}
                          </span>
                          <span className="text-sm text-slate-500 font-normal truncate max-w-[160px]">
                            {f.name}
                          </span>
                          {isF07 && <span className="w-2 h-2 rounded-full bg-red-600" />}
                        </div>
                      </td>
                      <td className="py-3.5">
                        <RiskBadge level={f.riskLevel} size="sm" />
                      </td>
                      <td className="py-3.5 text-[15px] font-bold text-slate-900">
                        {formatMw(f.currentLoadMw)}
                      </td>
                      <td className="py-3.5 text-[15px] text-slate-600 font-medium">
                        {f.capacityMw} MW
                      </td>
                      <td className="py-3.5">
                        <StressScoreGauge score={f.stressScore} size="sm" showLabel={false} />
                      </td>
                      <td className="py-3.5 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onNavigateToIntelligence(f.id);
                          }}
                          className="text-sm font-bold text-teal-800 hover:text-teal-900 inline-flex items-center cursor-pointer"
                        >
                          <span>Analyze</span>
                          <ChevronRight className="w-4 h-4 ml-0.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile Stacked Feeder Rows (< md) */}
          <div className="md:hidden space-y-3 pt-2">
            {sortedFeeders.map((f) => {
              const isF07 = f.id === 'F07';
              const isSelected = f.id === selectedFeederId;
              return (
                <div
                  key={f.id}
                  onClick={() => onSelectFeeder(f.id)}
                  className={`p-4 rounded-xl border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-teal-50/50 border-teal-300'
                      : 'bg-white border-slate-200/90 hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="text-base font-extrabold text-slate-900 font-display">
                        {f.id}
                      </span>
                      <span className="text-xs text-slate-500 font-medium truncate max-w-[170px]">
                        {f.name}
                      </span>
                      {isF07 && <span className="w-2 h-2 rounded-full bg-red-600 flex-shrink-0" />}
                    </div>
                    <RiskBadge level={f.riskLevel} size="sm" />
                  </div>

                  <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-slate-100 text-xs">
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                        Load / Capacity
                      </span>
                      <span className="text-sm font-bold text-slate-900 font-display mt-0.5 block">
                        {formatMw(f.currentLoadMw)} / {f.capacityMw} MW
                      </span>
                    </div>

                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                        Stress Score
                      </span>
                      <div className="mt-0.5 flex items-center space-x-1.5">
                        <span className="text-sm font-bold text-slate-900 font-display">
                          {f.stressScore} / 100
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 pt-2.5 border-t border-slate-100">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onNavigateToIntelligence(f.id);
                      }}
                      className="w-full py-2.5 px-3 rounded-lg bg-slate-50 hover:bg-slate-100 text-teal-800 text-xs font-bold transition-colors flex items-center justify-center space-x-1 min-h-[44px] cursor-pointer"
                    >
                      <span>Analyze Feeder {f.id}</span>
                      <ChevronRight className="w-4 h-4 ml-0.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </CollapsibleSection>

        {/* 2. System Load Forecast */}
        <CollapsibleSection
          title="SYSTEM LOAD FORECAST"
          subtitle="60-minute demand trajectory for Feeder F07 with capacity breach horizon"
          badge={
            <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
              Breach expected in 38 min
            </span>
          }
          isOpen={activeSection === 'forecast'}
          onToggle={() => toggleSection('forecast')}
        >
          <div className="pt-2">
            <ForecastHorizonChart
              data={forecastData}
              capacityMw={100}
              showMitigated={isMitigated}
              highlightBreach={!isMitigated}
            />
          </div>
        </CollapsibleSection>

        {/* 3. Recent Events */}
        <CollapsibleSection
          title="RECENT EVENTS"
          subtitle="Real-time chronological SCADA event notifications"
          badge={
            <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600">
              {MOCK_RECENT_EVENTS.length} LOGGED
            </span>
          }
          isOpen={activeSection === 'events'}
          onToggle={() => toggleSection('events')}
        >
          <div className="pt-2 divide-y divide-slate-100">
            {MOCK_RECENT_EVENTS.map(evt => {
              const getEventIcon = () => {
                switch (evt.type) {
                  case 'critical':
                    return <AlertCircle className="w-4.5 h-4.5 text-red-600" />;
                  case 'warning':
                    return <AlertTriangle className="w-4.5 h-4.5 text-amber-600" />;
                  case 'success':
                    return <CheckCircle2 className="w-4.5 h-4.5 text-emerald-600" />;
                  case 'info':
                  default:
                    return <Info className="w-4.5 h-4.5 text-teal-700" />;
                }
              };

              return (
                <div key={evt.id} className="py-3.5 flex flex-col sm:flex-row sm:items-start justify-between gap-2 sm:gap-4">
                  <div className="flex items-start space-x-3.5">
                    <span className="mt-0.5 flex-shrink-0">{getEventIcon()}</span>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm sm:text-[15px] font-bold text-slate-900">{evt.title}</span>
                        {evt.feederId && (
                          <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-semibold">
                            {evt.feederId}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-600 mt-1 leading-relaxed">{evt.description}</p>
                    </div>
                  </div>
                  <span className="text-xs font-mono text-slate-400 flex-shrink-0 self-start sm:self-auto pl-8 sm:pl-0 pt-0.5">
                    {evt.timestamp}
                  </span>
                </div>
              );
            })}
          </div>
        </CollapsibleSection>
      </div>
    </div>
  );
};
