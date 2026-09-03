import React, { useState, useEffect } from 'react';
import { Feeder, ForecastPoint, isMlFeeder } from '../types';
import { gridService } from '../api/gridService';
import { RiskBadge } from '../components/RiskBadge';
import { StressScoreGauge } from '../components/StressScoreGauge';
import { CollapsibleSection } from '../components/CollapsibleSection';
import { GridMap } from '../map/GridMap';
import { ForecastHorizonChart } from '../charts/ForecastHorizonChart';
import { MOCK_RECENT_EVENTS } from '../data/eventsMock';
import { formatMw, formatTto } from '../utils/formatters';
import {
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  ChevronRight,
  AlertTriangle,
  Info,
  ShieldCheck,
} from 'lucide-react';

type CollapsibleTab = 'ranking' | 'forecast' | 'events';

interface CommandCenterProps {
  feeders: Feeder[];
  selectedFeederId: string;
  onSelectFeeder: (id: string) => void;
  onNavigateToIntelligence: (feederId: string) => void;
  onNavigateToPrevention: () => void;
  mitigatedFeederId: string | null;
}

// -----------------------------------------------------------------------
// Featured grid event selection.
//
// NOTE ON SCOPE: the backend does not currently expose any endpoint with
// real event/alert timestamps (risk alerts ARE persisted server-side --
// see backend/app/models/alert.py / db_service.record_alert -- but no route
// returns those rows; /api/db/summary only returns aggregate counts). So
// this cannot determine a true "most recently occurred" event in a
// timestamp sense. Instead it derives the most operationally relevant
// feeder from the CURRENT real risk snapshot (backend ML Stress Engine
// output for every feeder), which is the closest honest approximation
// available today. "Recently mitigated" is only ever shown for a feeder
// this browser session itself actually dispatched against (a real,
// verified action) -- never inferred or fabricated.
// -----------------------------------------------------------------------
type FeaturedEvent =
  | { kind: 'AT_RISK'; feeder: Feeder }
  | { kind: 'MITIGATED'; feeder: Feeder }
  | { kind: 'STABLE' };

function selectFeaturedEvent(feeders: Feeder[], mitigatedFeederId: string | null): FeaturedEvent {
  // Restricted to the 10 real ML feeders: legacy non-ML feeders (e.g. F12)
  // sit on an incomparable scale (F12's forecast is raw NATIONAL demand, not
  // a feeder-level allocation -- see backend/app/services/forecast_service.py),
  // so mixing them into "what needs attention" would misrepresent the ML
  // Stress Engine's real signal.
  const mlFeeders = feeders.filter(f => isMlFeeder(f.id));

  const critical = mlFeeders
    .filter(f => f.riskLevel === 'CRITICAL' || f.riskLevel === 'HIGH')
    .sort((a, b) => b.stressScore - a.stressScore);
  if (critical.length > 0) {
    return { kind: 'AT_RISK', feeder: critical[0] };
  }

  if (mitigatedFeederId) {
    const mitigated = mlFeeders.find(f => f.id === mitigatedFeederId);
    if (mitigated) return { kind: 'MITIGATED', feeder: mitigated };
  }

  const moderate = mlFeeders.filter(f => f.riskLevel === 'MODERATE').sort((a, b) => b.stressScore - a.stressScore);
  if (moderate.length > 0) {
    return { kind: 'AT_RISK', feeder: moderate[0] };
  }

  return { kind: 'STABLE' };
}

export const CommandCenter: React.FC<CommandCenterProps> = ({
  feeders,
  selectedFeederId,
  onSelectFeeder,
  onNavigateToIntelligence,
  onNavigateToPrevention,
  mitigatedFeederId,
}) => {
  const [activeSection, setActiveSection] = useState<CollapsibleTab | null>(null);
  const [forecastData, setForecastData] = useState<ForecastPoint[]>([]);

  const event = selectFeaturedEvent(feeders, mitigatedFeederId);
  const featuredFeeder = event.kind !== 'STABLE' ? event.feeder : undefined;

  const sortedFeeders = [...feeders].sort((a, b) => b.stressScore - a.stressScore);
  const mlFeeders = feeders.filter(f => isMlFeeder(f.id));
  const criticalCount = mlFeeders.filter(f => f.riskLevel === 'CRITICAL' || f.riskLevel === 'HIGH').length;
  // Restricted to ML feeders -- see selectFeaturedEvent's comment on why
  // legacy feeders (national-scale forecast) can't be compared on this axis.
  const highestForecastFeeder = mlFeeders.length
    ? [...mlFeeders].sort((a, b) => b.peakForecastMw - a.peakForecastMw)[0]
    : undefined;

  const featuredFeederId = featuredFeeder?.id;
  useEffect(() => {
    if (!featuredFeederId) {
      setForecastData([]);
      return;
    }
    let cancelled = false;
    gridService.getForecast(featuredFeederId).then(result => {
      if (!cancelled) setForecastData(result.points);
    }).catch(() => {
      if (!cancelled) setForecastData([]);
    });
    return () => { cancelled = true; };
  }, [featuredFeederId]);

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
          GridGuard continuously forecasts feeder stress and identifies thermal overload risk across all {feeders.length} monitored feeders.
        </p>
      </div>

      {/* 2. FEATURED GRID EVENT + TOPOLOGY */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* Left: Data-driven featured event card */}
        <div className="lg:col-span-5 bg-white border border-slate-200/90 rounded-2xl p-5 sm:p-7 shadow-xs flex flex-col justify-between space-y-6">
          {event.kind === 'AT_RISK' && featuredFeeder ? (
            <>
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-3xl sm:text-4xl font-extrabold text-slate-900 font-display">
                    {featuredFeeder.id}
                  </span>
                  <span className="px-2.5 py-1 rounded-full bg-red-50 border border-red-200 text-red-700 text-xs font-bold uppercase tracking-wider">
                    {featuredFeeder.riskLevel} Risk
                  </span>
                </div>
                <div className="text-xs text-slate-500 font-medium mt-0.5">
                  {featuredFeeder.name}
                </div>

                <div className="mt-6 pt-5 border-t border-slate-100 grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                      Current Load
                    </span>
                    <div className="text-2xl sm:text-3xl font-extrabold text-slate-900 font-display mt-0.5">
                      {formatMw(featuredFeeder.currentLoadMw)} <span className="text-sm font-semibold text-slate-400">/ {featuredFeeder.capacityMw.toFixed(1)} MW</span>
                    </div>
                  </div>

                  <div>
                    <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                      Predicted Peak
                    </span>
                    <div className="text-2xl sm:text-3xl font-extrabold text-red-600 font-display mt-0.5">
                      {formatMw(featuredFeeder.peakForecastMw)} <span className="text-sm font-semibold text-red-400">MW</span>
                    </div>
                  </div>
                </div>

                <div className="mt-5 p-3.5 rounded-xl bg-red-50/60 border border-red-200/80 flex items-start space-x-3">
                  <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
                  <div className="text-xs text-red-800 leading-relaxed">
                    Stress score {featuredFeeder.stressScore}/100 ({featuredFeeder.riskLevel}).{' '}
                    {featuredFeeder.timeToOverloadHours != null ? (
                      <>Estimated time to overload: <strong className="font-bold text-red-950">~{featuredFeeder.timeToOverloadHours.toFixed(1)} hours</strong> (hour-resolution estimate).</>
                    ) : featuredFeeder.timeToOverloadMin != null ? (
                      <>Estimated time to overload: <strong className="font-bold text-red-950">{formatTto(featuredFeeder.timeToOverloadMin)}</strong>.</>
                    ) : (
                      'No overload crossing predicted within the current forecast horizon.'
                    )}
                  </div>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                <button
                  onClick={() => { onSelectFeeder(featuredFeeder.id); onNavigateToPrevention(); }}
                  className="w-full sm:flex-1 px-4 py-3 rounded-xl bg-[#073B3A] hover:bg-[#0B5D56] text-white text-xs font-bold transition-all shadow-sm flex items-center justify-center space-x-1.5 cursor-pointer min-h-[44px]"
                >
                  <span>View Recommendation</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => { onSelectFeeder(featuredFeeder.id); onNavigateToIntelligence(featuredFeeder.id); }}
                  className="w-full sm:w-auto px-4 py-3 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors cursor-pointer min-h-[44px] text-center"
                >
                  View Feeder
                </button>
              </div>
            </>
          ) : event.kind === 'MITIGATED' && featuredFeeder ? (
            <div className="h-full flex flex-col justify-between py-2">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-3xl sm:text-4xl font-extrabold text-slate-900 font-display">
                    {featuredFeeder.id}
                  </span>
                  <span className="px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold uppercase tracking-wider flex items-center space-x-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Dispatched</span>
                  </span>
                </div>
                <div className="text-xs text-slate-500 font-medium mt-0.5">
                  {featuredFeeder.name}
                </div>

                <div className="mt-6 pt-5 border-t border-slate-100">
                  <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                    Current Status (This Session)
                  </span>
                  <div className="text-3xl font-extrabold text-emerald-700 font-display mt-0.5">
                    {featuredFeeder.riskLevel} <span className="text-sm font-semibold text-emerald-600">({featuredFeeder.stressScore}/100)</span>
                  </div>
                  <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                    A mitigation action was dispatched for this feeder in the current session. No persisted
                    before/after dispatch record exists yet, so no specific MW reduction is claimed here --
                    the live risk state above is the real current value.
                  </p>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100">
                <button
                  onClick={() => { onSelectFeeder(featuredFeeder.id); onNavigateToIntelligence(featuredFeeder.id); }}
                  className="w-full px-4 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition-colors text-center cursor-pointer min-h-[44px]"
                >
                  Inspect Feeder Telemetry →
                </button>
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col justify-between py-2">
              <div>
                <div className="flex items-center space-x-2">
                  <ShieldCheck className="w-8 h-8 text-emerald-600" />
                  <span className="text-2xl sm:text-3xl font-extrabold text-slate-900 font-display">
                    Grid Stable
                  </span>
                </div>
                <p className="text-xs text-slate-500 font-medium mt-2 leading-relaxed">
                  No feeder is currently classified HIGH or CRITICAL risk by the ML Stress Engine across all {feeders.length} monitored feeders.
                </p>
              </div>
              <div className="pt-4 border-t border-slate-100 text-xs text-slate-500">
                Select any feeder below to inspect its current forecast and risk detail.
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
                {feeders.length} Feeders
              </span>
            </div>
            {featuredFeeder && (
              <div className="flex items-center space-x-2 text-xs font-medium text-slate-600">
                <span className={`w-2 h-2 rounded-full ${event.kind === 'AT_RISK' ? 'bg-red-600' : 'bg-emerald-600'}`}></span>
                <span>{featuredFeeder.id} {event.kind === 'AT_RISK' ? 'Elevated Risk' : 'Dispatched'}</span>
              </div>
            )}
          </div>

          <div className="flex-1 w-full min-h-[300px] sm:min-h-[340px] rounded-xl overflow-hidden">
            <GridMap
              feeders={feeders}
              selectedFeederId={selectedFeederId}
              onSelectFeeder={onSelectFeeder}
              onNavigateToIntelligence={onNavigateToIntelligence}
              isMitigated={selectedFeederId === mitigatedFeederId}
            />
          </div>
        </div>
      </div>

      {/* 3. FOUR KEY OPERATIONAL METRICS */}
      <div className="py-6 border-y border-slate-200/80 grid grid-cols-2 lg:grid-cols-4 gap-6 sm:gap-8">
        <div>
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Feeders Monitored
          </span>
          <div className="text-3xl sm:text-4xl font-extrabold text-slate-900 font-display mt-1">
            {feeders.length}
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            F01-F10 ML feeders{feeders.some(f => f.id === 'F12') ? ' + legacy F12' : ''}
          </span>
        </div>

        <div className="border-l border-slate-200/80 pl-6 lg:pl-8">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Feeders At Risk
          </span>
          <div className={`text-3xl sm:text-4xl font-extrabold font-display mt-1 ${criticalCount > 0 ? 'text-red-600' : 'text-slate-900'}`}>
            {criticalCount} <span className="text-sm font-semibold text-slate-400">Critical/High</span>
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            {criticalCount > 0 ? 'Review flagged feeders below' : 'All lines nominal'}
          </span>
        </div>

        <div className="border-t border-slate-200/80 lg:border-t-0 pt-4 lg:pt-0 lg:border-l lg:border-slate-200/80 lg:pl-8">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Highest Forecast Peak
          </span>
          <div className="text-3xl sm:text-4xl font-extrabold text-slate-900 font-display mt-1">
            {highestForecastFeeder ? formatMw(highestForecastFeeder.peakForecastMw) : '--'}
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            {highestForecastFeeder ? `Feeder ${highestForecastFeeder.id}` : 'No data'}
          </span>
        </div>

        <div className="border-t border-slate-200/80 lg:border-t-0 pt-4 lg:pt-0 border-l border-slate-200/80 pl-6 lg:pl-8">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Grid Status
          </span>
          <div className={`text-3xl sm:text-4xl font-extrabold font-display mt-1 ${criticalCount > 0 ? 'text-red-600' : 'text-emerald-700'}`}>
            {criticalCount > 0 ? 'Attention' : 'Stable'}
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            Based on current ML Stress Engine output
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
          subtitle={`All ${feeders.length} monitored feeders prioritized by predictive thermal stress`}
          badge={
            <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700">
              {feeders.length} FEEDERS
            </span>
          }
          isOpen={activeSection === 'ranking'}
          onToggle={() => toggleSection('ranking')}
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
                          {!isMlFeeder(f.id) && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-semibold" title="Legacy feeder -- not part of the F01-F10 ML feeder universe; forecast is on a different scale">
                              legacy
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3.5">
                        <RiskBadge level={f.riskLevel} size="sm" />
                      </td>
                      <td className="py-3.5 text-[15px] font-bold text-slate-900">
                        {formatMw(f.currentLoadMw)}
                      </td>
                      <td className="py-3.5 text-[15px] text-slate-600 font-medium">
                        {f.capacityMw.toFixed(1)} MW
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
                    </div>
                    <RiskBadge level={f.riskLevel} size="sm" />
                  </div>

                  <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-slate-100 text-xs">
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                        Load / Capacity
                      </span>
                      <span className="text-sm font-bold text-slate-900 font-display mt-0.5 block">
                        {formatMw(f.currentLoadMw)} / {f.capacityMw.toFixed(1)} MW
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
          title="FEATURED FEEDER LOAD FORECAST"
          subtitle={featuredFeeder ? `24-hour ML demand trajectory for feeder ${featuredFeeder.id}` : 'No featured feeder currently'}
          isOpen={activeSection === 'forecast'}
          onToggle={() => toggleSection('forecast')}
        >
          <div className="pt-2">
            {featuredFeeder ? (
              <ForecastHorizonChart
                data={forecastData}
                capacityMw={featuredFeeder.capacityMw}
                highlightBreach={featuredFeeder.riskLevel === 'CRITICAL' || featuredFeeder.riskLevel === 'HIGH'}
                timeToOverloadHours={featuredFeeder.timeToOverloadHours}
              />
            ) : (
              <div className="text-xs text-slate-400 py-6 text-center">No feeder currently featured.</div>
            )}
          </div>
        </CollapsibleSection>

        {/* 3. Recent Events */}
        <CollapsibleSection
          title="RECENT EVENTS"
          subtitle="Illustrative demo event log (not sourced from a live backend alert feed -- see Remaining Issues)"
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
