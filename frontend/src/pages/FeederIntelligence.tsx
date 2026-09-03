import React, { useState, useEffect } from 'react';
import { Feeder, ForecastPoint, ForecastMeta, ShapContributor } from '../types';
import { gridService } from '../api/gridService';
import { ForecastHorizonChart } from '../charts/ForecastHorizonChart';
import { ShapContributorsBarChart } from '../charts/ShapContributorsBarChart';
import { CollapsibleSection } from '../components/CollapsibleSection';
import { formatMw, formatTto } from '../utils/formatters';
import {
  ArrowRight,
  ShieldAlert,
  CheckCircle2,
  Layers,
} from 'lucide-react';

interface FeederIntelligenceProps {
  feeder: Feeder;
  allFeeders: Feeder[];
  onSelectFeeder: (id: string) => void;
  onNavigateToPrevention: () => void;
  isMitigated: boolean;
}

export const FeederIntelligence: React.FC<FeederIntelligenceProps> = ({
  feeder,
  allFeeders,
  onSelectFeeder,
  onNavigateToPrevention,
  isMitigated,
}) => {
  const [forecast, setForecast] = useState<ForecastPoint[]>([]);
  const [forecastMeta, setForecastMeta] = useState<ForecastMeta>({});
  const [shapContributors, setShapContributors] = useState<ShapContributor[]>([]);
  const [riskSource, setRiskSource] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Progressive disclosure states (all collapsed by default)
  const [openSection, setOpenSection] = useState<'why_matters' | 'telemetry' | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadData() {
      setIsLoading(true);
      try {
        const [fcResult, explainData] = await Promise.all([
          gridService.getForecast(feeder.id),
          gridService.getExplainability(feeder.id),
        ]);
        if (cancelled) return;
        setForecast(fcResult.points);
        setForecastMeta(fcResult.meta);
        setShapContributors(explainData.contributors);
        setRiskSource(explainData.source);
      } catch (err) {
        console.error('Error loading feeder intelligence:', err);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    loadData();
    return () => { cancelled = true; };
  }, [feeder.id]);

  const toggleSection = (section: 'why_matters' | 'telemetry') => {
    setOpenSection(prev => (prev === section ? null : section));
  };

  return (
    <div className="space-y-8 sm:space-y-10">
      {/* 1. TOP EDITORIAL TITLE & HERO STATEMENT */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-2 text-[11px] font-bold uppercase tracking-widest-sm text-teal-800">
            <span>{feeder.id}</span>
            <span className="text-slate-300">•</span>
            <span>Feeder Intelligence & Diagnostics</span>
          </div>

          {/* Feeder Switcher -- built from the real feeder list, not a hardcoded set */}
          <div className="flex items-center space-x-1 overflow-x-auto no-scrollbar pb-1 flex-nowrap max-w-full">
            <span className="text-xs text-slate-400 font-semibold mr-1 flex-shrink-0">Switch:</span>
            {allFeeders.map((f) => (
              <button
                key={f.id}
                onClick={() => onSelectFeeder(f.id)}
                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-colors cursor-pointer flex-shrink-0 ${
                  feeder.id === f.id
                    ? 'bg-[#073B3A] text-white shadow-xs'
                    : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {f.id}
              </button>
            ))}
          </div>
        </div>

        {/* Large Confident Statement */}
        <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold text-slate-900 tracking-tight font-display leading-[1.15] sm:leading-[1.1] max-w-3xl">
          {isMitigated ? (
            <span className="text-emerald-800">Mitigation dispatched for this feeder.</span>
          ) : feeder.timeToOverloadHours != null ? (
            <span>Overload risk in <span className="text-red-600">~{feeder.timeToOverloadHours.toFixed(1)} hours</span>.</span>
          ) : feeder.timeToOverloadMin != null ? (
            <span>Overload risk in <span className="text-red-600">{formatTto(feeder.timeToOverloadMin)}</span>.</span>
          ) : (
            <span className="text-emerald-800">Operating nominal. Within safe capacity limits.</span>
          )}
        </h1>

        <p className="text-sm sm:text-base text-slate-500 font-normal">
          {feeder.name} • {feeder.voltagePu.toFixed(2)} pu
        </p>
      </div>

      {/* 2. LARGE TYPOGRAPHY METRICS WITH THIN DIVIDERS */}
      <div className="py-6 border-y border-slate-200/80 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 sm:gap-6">
        <div>
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Current Load
          </span>
          <div className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-slate-900 font-display mt-1">
            {formatMw(feeder.currentLoadMw)}
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            Latest ML allocation
          </span>
        </div>

        <div className="border-l border-slate-200/80 pl-4 sm:pl-6">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Capacity
          </span>
          <div className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-slate-900 font-display mt-1">
            {feeder.capacityMw.toFixed(1)} <span className="text-sm font-semibold text-slate-400">MW</span>
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            ML-derived
          </span>
        </div>

        <div className="border-t border-slate-200/80 sm:border-t-0 pt-4 sm:pt-0 sm:border-l sm:border-slate-200/80 sm:pl-6">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Predicted Peak
          </span>
          <div className={`text-2xl sm:text-3xl lg:text-4xl font-extrabold font-display mt-1 ${feeder.peakForecastMw > feeder.capacityMw ? 'text-red-600' : 'text-slate-900'}`}>
            {formatMw(feeder.peakForecastMw)}
          </div>
          <span className={`text-xs font-medium mt-0.5 block ${feeder.peakForecastMw > feeder.capacityMw ? 'text-red-600' : 'text-slate-500'}`}>
            {feeder.peakForecastMw > feeder.capacityMw
              ? `+${(feeder.peakForecastMw - feeder.capacityMw).toFixed(1)} MW over capacity`
              : 'Within capacity'}
          </span>
        </div>

        <div className="border-t border-slate-200/80 sm:border-t-0 pt-4 sm:pt-0 border-l border-slate-200/80 pl-4 sm:pl-6 lg:border-l">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Stress Score
          </span>
          <div className={`text-2xl sm:text-3xl lg:text-4xl font-extrabold font-display mt-1 ${feeder.stressScore >= 80 ? 'text-red-600' : 'text-slate-900'}`}>
            {feeder.stressScore} <span className="text-sm font-semibold text-slate-400">/ 100</span>
          </div>
          <span className={`text-xs font-medium mt-0.5 block ${feeder.riskLevel === 'CRITICAL' ? 'text-red-600' : feeder.riskLevel === 'HIGH' ? 'text-amber-600' : 'text-slate-500'}`}>
            Tier: {feeder.riskLevel.charAt(0) + feeder.riskLevel.slice(1).toLowerCase()}
          </span>
        </div>

        <div className="border-t border-slate-200/80 sm:border-t-0 pt-4 sm:pt-0 border-l border-slate-200/80 pl-4 sm:pl-6 col-span-2 sm:col-span-1 lg:border-l">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Time to Overload
          </span>
          <div className={`text-2xl sm:text-3xl lg:text-4xl font-extrabold font-display mt-1 ${feeder.timeToOverloadHours != null || feeder.timeToOverloadMin != null ? 'text-red-600' : 'text-emerald-700'}`}>
            {feeder.timeToOverloadHours != null
              ? `~${feeder.timeToOverloadHours.toFixed(1)}h`
              : formatTto(feeder.timeToOverloadMin)}
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            {feeder.timeToOverloadHours != null ? 'Hour-resolution estimate' : feeder.timeToOverloadMin != null ? 'Action countdown' : 'No overload risk'}
          </span>
        </div>
      </div>

      {/* 3. CENTERPIECE FORECAST VISUAL */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-7 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div>
            <h2 className="text-base font-bold text-slate-900 font-display">
              Predictive Demand Curve
            </h2>
            <p className="text-xs text-slate-500">
              {forecastMeta.source === 'ml'
                ? `24-hour ML forecast vs ${feeder.capacityMw.toFixed(1)} MW capacity`
                : `Legacy 15/30/45/60-minute forecast vs ${feeder.capacityMw.toFixed(1)} MW capacity`}
            </p>
          </div>

          {!isMitigated ? (
            <button
              onClick={onNavigateToPrevention}
              className="px-4 py-2 rounded-xl bg-[#073B3A] hover:bg-[#0B5D56] text-white text-xs font-bold transition-all shadow-sm flex items-center space-x-1.5 cursor-pointer"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Evaluate Interventions</span>
              <ArrowRight className="w-3.5 h-3.5 ml-0.5" />
            </button>
          ) : (
            <span className="px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center space-x-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span>Mitigation Dispatched</span>
            </span>
          )}
        </div>

        {isLoading ? (
          <div className="h-64 flex items-center justify-center text-slate-400 text-xs font-medium">
            Loading feeder forecast telemetry...
          </div>
        ) : (
          <>
            <ForecastHorizonChart
              data={forecast}
              capacityMw={feeder.capacityMw}
              showMitigated={isMitigated}
              highlightBreach={!isMitigated && (feeder.riskLevel === 'CRITICAL' || feeder.riskLevel === 'HIGH')}
              timeToOverloadHours={feeder.timeToOverloadHours}
            />
            {forecastMeta.source === 'ml' && (
              <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-xs text-slate-500 pt-3 border-t border-slate-100">
                <span><strong className="text-slate-700 font-semibold">Method:</strong> {forecastMeta.forecastMethod ?? 'n/a'}</span>
                <span><strong className="text-slate-700 font-semibold">Regime:</strong> {forecastMeta.regimeStatus ?? 'n/a'}</span>
                <span><strong className="text-slate-700 font-semibold">Scope:</strong> {forecastMeta.scope ?? 'n/a'}</span>
                <span><strong className="text-slate-700 font-semibold">Origin:</strong> {forecastMeta.originTimestamp ?? 'n/a'}</span>
              </div>
            )}
          </>
        )}
      </div>

      {/* 4. WHY FEEDER IS AT RISK */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-7 shadow-xs space-y-4">
        <div className="border-b border-slate-100 pb-3">
          <div className="text-[11px] uppercase font-bold text-teal-800 tracking-wider">
            Risk Attribution
          </div>
          <h2 className="text-base sm:text-lg font-bold text-slate-900 font-display mt-0.5">
            Why Feeder {feeder.id} is {feeder.riskLevel === 'CRITICAL' || feeder.riskLevel === 'HIGH' ? 'at Risk' : 'Nominal'}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {riskSource === 'ml_stress_engine'
              ? 'Weighted point contributions from the real ML Grid Stress Engine'
              : riskSource === 'legacy_formula'
              ? 'Weighted contributions from the legacy risk formula'
              : 'Risk contributor breakdown'}
          </p>
        </div>

        <ShapContributorsBarChart
          contributors={shapContributors}
          feederId={feeder.id}
        />
      </div>

      {/* 5. PROGRESSIVE DISCLOSURE COLLAPSIBLE SECTIONS */}
      <div className="space-y-1">
        <div className="text-xs uppercase font-bold text-slate-400 tracking-widest-sm mb-3">
          Additional Detail (Click to Expand)
        </div>

        {/* 1. Why this matters */}
        <CollapsibleSection
          title="WHY THIS MATTERS"
          subtitle="What sustained overload risk means for feeder-level thermal reliability"
          isOpen={openSection === 'why_matters'}
          onToggle={() => toggleSection('why_matters')}
        >
          <div className="p-5 bg-slate-50 border border-slate-200/70 rounded-xl text-sm sm:text-[15px] text-slate-700 leading-relaxed space-y-3">
            <p>
              Feeder {feeder.id} ({feeder.name}) is one of the 10 synthetic Delhi-area ML feeders (F01-F10) allocated
              from the real national demand forecast. Its capacity, load, and voltage are simulated -- not real
              utility measurements.
            </p>
            <p>
              Sustained operation above the feeder's rated capacity would, on a real distribution feeder, risk
              accelerated thermal wear and possible protective relay lockout. No specific relay model, meter count,
              or asset rating is claimed here because that physical asset data isn't available.
            </p>
          </div>
        </CollapsibleSection>

        {/* 2. Feeder Telemetry -- only real backend fields, no fabricated sensors */}
        <CollapsibleSection
          title="FEEDER DATA"
          subtitle="Real values from the current ML response"
          isOpen={openSection === 'telemetry'}
          onToggle={() => toggleSection('telemetry')}
        >
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-1">
            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl">
              <span className="text-slate-400 text-xs uppercase font-bold tracking-wider block">Voltage</span>
              <span className="text-2xl font-bold text-slate-900 font-display mt-1 block">{feeder.voltagePu.toFixed(3)} pu</span>
              <span className="text-xs text-slate-500 mt-0.5 block">Per-unit value, not a kV class</span>
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl">
              <span className="text-slate-400 text-xs uppercase font-bold tracking-wider block">Risk Source</span>
              <span className="text-lg font-bold text-slate-900 font-display mt-1 block">
                {riskSource === 'ml_stress_engine' ? 'ML Stress Engine' : riskSource === 'legacy_formula' ? 'Legacy Formula' : 'n/a'}
              </span>
              <span className="text-xs text-slate-500 mt-0.5 block">Risk evaluation source</span>
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl">
              <span className="text-slate-400 text-xs uppercase font-bold tracking-wider block">Forecast Scope</span>
              <span className="text-lg font-bold text-slate-900 font-display mt-1 block">{forecastMeta.scope ?? 'n/a'}</span>
              <span className="text-xs text-slate-500 mt-0.5 block">'feeder' = own allocation</span>
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl">
              <span className="text-slate-400 text-xs uppercase font-bold tracking-wider flex items-center gap-1"><Layers className="w-3 h-3" /> Regime</span>
              <span className="text-lg font-bold text-slate-900 font-display mt-1 block">{forecastMeta.regimeStatus ?? 'n/a'}</span>
              <span className="text-xs text-slate-500 mt-0.5 block">{forecastMeta.regimeScore != null ? `score ${forecastMeta.regimeScore.toFixed(2)}` : 'ML regime detector'}</span>
            </div>
          </div>
        </CollapsibleSection>
      </div>
    </div>
  );
};
