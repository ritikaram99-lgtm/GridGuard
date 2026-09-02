import React, { useState } from 'react';
import { useWhatIfSimulator } from '../hooks/useWhatIfSimulator';
import { ForecastHorizonChart } from '../charts/ForecastHorizonChart';
import { RiskBadge } from '../components/RiskBadge';
import { StressScoreGauge } from '../components/StressScoreGauge';
import { CollapsibleSection } from '../components/CollapsibleSection';
import { formatTto } from '../utils/formatters';
import { 
  RotateCcw, 
  ArrowRight, 
  Sliders, 
  LineChart, 
  Sparkles,
  Thermometer,
  Zap,
  Sun
} from 'lucide-react';

interface WhatIfSimulatorProps {
  feederId?: string;
  onNavigateToPrevention: () => void;
}

export const WhatIfSimulator: React.FC<WhatIfSimulatorProps> = ({
  feederId = 'F07',
  onNavigateToPrevention,
}) => {
  const { params, result, isSimulating, updateParam, resetToBaseline, applyPreset } =
    useWhatIfSimulator(feederId);

  // Progressive disclosure states (all collapsed by default)
  const [openSection, setOpenSection] = useState<'forecast' | 'recommendation' | null>(null);

  const toggleSection = (section: 'forecast' | 'recommendation') => {
    setOpenSection(prev => (prev === section ? null : section));
  };

  return (
    <div className="space-y-8 sm:space-y-10">
      {/* 1. TOP EDITORIAL HERO STATEMENT */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-2 text-[11px] font-bold uppercase tracking-widest-sm text-teal-800">
            <span>WHAT-IF SIMULATION / EXPERIMENT WORKSPACE</span>
          </div>

          <button
            onClick={resetToBaseline}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 text-xs font-semibold transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
            <span>Reset Baseline</span>
          </button>
        </div>

        <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold text-slate-900 tracking-tight font-display max-w-2xl sm:max-w-3xl leading-[1.15] sm:leading-[1.1]">
          What changes the grid's future?
        </h1>
        <p className="text-sm sm:text-base text-slate-600 max-w-2xl font-normal leading-relaxed pt-1">
          Simulate how weather volatility, aggressive EV adoption, and solar cloud cover impact Feeder {feederId} capacity margins in real time.
        </p>
      </div>

      {/* 2. SCENARIO PRESETS (Horizontally scrollable on mobile, wrapping on desktop) */}
      <div className="flex items-center gap-2 overflow-x-auto no-scrollbar pb-1 flex-nowrap max-w-full">
        <span className="text-xs uppercase font-bold text-slate-400 tracking-wider mr-1 flex-shrink-0">
          Presets:
        </span>
        <button
          onClick={() => applyPreset({ ambientTempC: 36, evDemandPct: 145, solarGenerationPct: 40 })}
          className={`px-3.5 py-2 rounded-xl text-xs font-bold border transition-colors cursor-pointer flex-shrink-0 min-h-[40px] ${
            params.ambientTempC === 36 && params.evDemandPct === 145 && params.solarGenerationPct === 40
              ? 'bg-[#073B3A] border-[#073B3A] text-white shadow-xs'
              : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
          }`}
        >
          Summer Peak + EV Surge
        </button>

        <button
          onClick={() => applyPreset({ ambientTempC: 28, evDemandPct: 100, solarGenerationPct: 10 })}
          className={`px-3.5 py-2 rounded-xl text-xs font-bold border transition-colors cursor-pointer flex-shrink-0 min-h-[40px] ${
            params.solarGenerationPct === 10
              ? 'bg-amber-500 border-amber-500 text-white shadow-xs'
              : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
          }`}
        >
          Heavy Cloud Cover (10% Solar)
        </button>

        <button
          onClick={() => applyPreset({ ambientTempC: 22, evDemandPct: 100, solarGenerationPct: 85 })}
          className={`px-3.5 py-2 rounded-xl text-xs font-bold border transition-colors cursor-pointer flex-shrink-0 min-h-[40px] ${
            params.ambientTempC === 22 && params.solarGenerationPct === 85
              ? 'bg-emerald-600 border-emerald-600 text-white shadow-xs'
              : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
          }`}
        >
          Mild Spring Baseline (Nominal)
        </button>
      </div>

      {/* 3. EXPERIMENT WORKSPACE (Two Clean Columns - NO Tiny Cards) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* Left Column: Clean Slider Control Area */}
        <div className="lg:col-span-6 bg-white border border-slate-200/90 rounded-2xl p-5 sm:p-7 shadow-xs flex flex-col justify-between space-y-6">
          <div>
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <span className="text-xs uppercase font-bold text-teal-800 tracking-wider">
                Operating Variables
              </span>
              {isSimulating && (
                <span className="text-xs text-teal-700 font-semibold animate-pulse">
                  Recalculating...
                </span>
              )}
            </div>

            <div className="space-y-6 mt-6">
              {/* Slider 1: Ambient Temperature */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Thermometer className="w-4 h-4 text-orange-500" />
                    <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                      Ambient Temperature
                    </span>
                  </div>
                  <span className="text-lg font-extrabold text-slate-900 font-display">
                    {params.ambientTempC} °C
                  </span>
                </div>
                <div className="py-2">
                  <input
                    type="range"
                    min="18"
                    max="45"
                    step="1"
                    value={params.ambientTempC}
                    onChange={(e) => updateParam('ambientTempC', Number(e.target.value))}
                    className="w-full h-3 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-[#073B3A]"
                  />
                </div>
                <div className="flex justify-between text-[11px] text-slate-400 font-medium">
                  <span>18°C (Cool)</span>
                  <span>36°C (Summer Baseline)</span>
                  <span>45°C (Extreme Heat)</span>
                </div>
              </div>

              {/* Slider 2: EV Demand Volume */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Zap className="w-4 h-4 text-teal-600" />
                    <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                      EV Charging Volume
                    </span>
                  </div>
                  <span className="text-lg font-extrabold text-slate-900 font-display">
                    {params.evDemandPct} %
                  </span>
                </div>
                <div className="py-2">
                  <input
                    type="range"
                    min="50"
                    max="200"
                    step="5"
                    value={params.evDemandPct}
                    onChange={(e) => updateParam('evDemandPct', Number(e.target.value))}
                    className="w-full h-3 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-[#073B3A]"
                  />
                </div>
                <div className="flex justify-between text-[11px] text-slate-400 font-medium">
                  <span>50% (Off-Peak)</span>
                  <span>100% (Standard)</span>
                  <span>145% (Depot Peak)</span>
                  <span>200%</span>
                </div>
              </div>

              {/* Slider 3: Distributed Solar Generation */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Sun className="w-4 h-4 text-amber-500" />
                    <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                      Rooftop Solar Output
                    </span>
                  </div>
                  <span className="text-lg font-extrabold text-slate-900 font-display">
                    {params.solarGenerationPct} %
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={params.solarGenerationPct}
                  onChange={(e) => updateParam('solarGenerationPct', Number(e.target.value))}
                  className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-[#073B3A]"
                />
                <div className="flex justify-between text-[11px] text-slate-400 font-medium">
                  <span>0% (Overcast)</span>
                  <span>40% (Afternoon Sun)</span>
                  <span>100% (Clear Peak)</span>
                </div>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100 text-xs text-slate-500">
            Parameters recompute machine learning sensitivity models dynamically across all time horizons.
          </div>
        </div>

        {/* Right Column: Simulated Outcome */}
        <div className="lg:col-span-6 bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-7 shadow-xs flex flex-col justify-between space-y-6">
          <div>
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <span className="text-xs uppercase font-bold text-slate-400 tracking-wider">
                Simulated Outcome
              </span>
              <span className="text-xs font-bold text-slate-700">
                Continuous Rating: 100 MW
              </span>
            </div>

            {result && (
              <>
                <div className="grid grid-cols-2 gap-6 mt-6">
                  <div>
                    <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                      Simulated Peak Load
                    </span>
                    <div className={`text-3xl sm:text-4xl font-extrabold font-display mt-1 ${result.peakForecastMw > 100 ? 'text-red-600' : 'text-slate-900'}`}>
                      {result.peakForecastMw} <span className="text-sm font-semibold text-slate-400">MW</span>
                    </div>
                    <span className="text-xs text-slate-500 font-medium mt-0.5 block">
                      {result.peakForecastMw > 100 ? `+${(result.peakForecastMw - 100).toFixed(1)} MW Overload` : 'Safe under rating'}
                    </span>
                  </div>

                  <div>
                    <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                      Stress Score
                    </span>
                    <div className={`text-3xl sm:text-4xl font-extrabold font-display mt-1 ${result.stressScore >= 85 ? 'text-red-600' : 'text-slate-900'}`}>
                      {result.stressScore} <span className="text-sm font-semibold text-slate-400">/ 100</span>
                    </div>
                    <div className="mt-1">
                      <RiskBadge level={result.riskLevel} size="sm" />
                    </div>
                  </div>
                </div>

                <div className="mt-6 pt-5 border-t border-slate-100 grid grid-cols-2 gap-4 text-xs">
                  <div>
                    <span className="text-slate-400 text-[11px] uppercase font-bold tracking-wider block">Time to Overload</span>
                    <span className={`text-lg font-bold font-display mt-0.5 block ${result.timeToOverloadMin ? 'text-red-600' : 'text-emerald-700'}`}>
                      {formatTto(result.timeToOverloadMin)}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[11px] uppercase font-bold tracking-wider block">Recommended Strategy</span>
                    <span className="font-bold text-teal-800 text-xs mt-0.5 block">
                      {result.recommendedCombination}
                    </span>
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-xs">
            <span className="text-slate-500">
              Test interventions for these simulated conditions:
            </span>
            <button
              onClick={onNavigateToPrevention}
              className="flex items-center space-x-1 font-bold text-teal-800 hover:text-teal-900 cursor-pointer"
            >
              <span>Go to Prevention Center</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* 4. PROGRESSIVE DISCLOSURE COLLAPSIBLE SECTIONS */}
      <div className="space-y-1">
        <div className="text-xs uppercase font-bold text-slate-400 tracking-widest-sm mb-3">
          Detailed Sensitivity Projections (Click to Expand)
        </div>

        {/* 1. Forecast Impact */}
        <CollapsibleSection
          title="FORECAST IMPACT CURVE"
          subtitle="60-minute demand trajectory recalculated dynamically under simulated slider settings"
          isOpen={openSection === 'forecast'}
          onToggle={() => toggleSection('forecast')}
        >
          {result && (
            <div className="pt-2 bg-white border border-slate-200/90 rounded-2xl p-6 shadow-xs">
              <ForecastHorizonChart
                data={result.forecastPoints}
                capacityMw={result.capacityMw}
                highlightBreach={result.riskLevel === 'CRITICAL'}
              />
            </div>
          )}
        </CollapsibleSection>

        {/* 2. Recommended Intervention */}
        <CollapsibleSection
          title="RECOMMENDED INTERVENTION BREAKDOWN"
          subtitle="Optimal resource curtailment schedule calculated for this specific sensitivity state"
          isOpen={openSection === 'recommendation'}
          onToggle={() => toggleSection('recommendation')}
        >
          {result && (
            <div className="pt-1 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl space-y-1">
                <span className="text-xs uppercase font-bold text-slate-400 tracking-wider block">Minimum Required Reduction</span>
                <div className="text-2xl font-extrabold text-slate-900 font-display mt-0.5">
                  {result.minimumRequiredReductionMw} MW
                </div>
                <p className="text-xs sm:text-[13px] text-slate-600 pt-1 leading-relaxed">
                  Required strictly to cap demand at the 100 MW thermal limit under current parameters.
                </p>
              </div>

              <div className="p-4 bg-teal-50/40 border border-teal-200/80 rounded-xl space-y-1">
                <span className="text-xs uppercase font-bold text-teal-800 tracking-wider block">Recommended Safety Target</span>
                <div className="text-2xl font-extrabold text-teal-800 font-display mt-0.5">
                  {result.recommendedReductionMw} MW
                </div>
                <p className="text-xs sm:text-[13px] text-teal-800/90 pt-1 leading-relaxed">
                  Preferred intervention restoring continuous safety buffer under simulated loads.
                </p>
              </div>
            </div>
          )}
        </CollapsibleSection>
      </div>
    </div>
  );
};
