import React, { useState, useEffect } from 'react';
import { Feeder, ForecastPoint, ShapContributor } from '../types';
import { gridService } from '../api/gridService';
import { ForecastHorizonChart } from '../charts/ForecastHorizonChart';
import { ShapContributorsBarChart } from '../charts/ShapContributorsBarChart';
import { RiskBadge } from '../components/RiskBadge';
import { CollapsibleSection } from '../components/CollapsibleSection';
import { formatMw, formatTto } from '../utils/formatters';
import { 
  ArrowRight, 
  ShieldAlert, 
  CheckCircle2, 
  AlertCircle,
  HelpCircle, 
  Gauge, 
  Layers,
  Info
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
  onSelectFeeder,
  onNavigateToPrevention,
  isMitigated,
}) => {
  const [forecast, setForecast] = useState<ForecastPoint[]>([]);
  const [shapContributors, setShapContributors] = useState<ShapContributor[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Progressive disclosure states (all collapsed by default)
  const [openSection, setOpenSection] = useState<'why_matters' | 'telemetry' | 'technical' | null>(null);

  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      try {
        const [fcData, explainData] = await Promise.all([
          gridService.getForecast(feeder.id),
          gridService.getExplainability(feeder.id),
        ]);

        if (isMitigated && feeder.id === 'F07') {
          setForecast(
            fcData.map(pt => ({
              ...pt,
              mitigatedLoadMw: pt.timeStep === 'Current' ? 97 : pt.timeStep === '+15 min' ? 96 : pt.timeStep === '+30 min' ? 95 : 94,
            }))
          );
        } else {
          setForecast(fcData);
        }

        setShapContributors(explainData.contributors);
      } catch (err) {
        console.error('Error loading feeder intelligence:', err);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [feeder.id, isMitigated]);

  const toggleSection = (section: 'why_matters' | 'telemetry' | 'technical') => {
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

          {/* Quick Feeder Switcher */}
          <div className="flex items-center space-x-1 overflow-x-auto no-scrollbar pb-1 flex-nowrap max-w-full">
            <span className="text-xs text-slate-400 font-semibold mr-1 flex-shrink-0">Switch:</span>
            {['F07', 'F03', 'F09', 'F04', 'F01'].map((fid) => (
              <button
                key={fid}
                onClick={() => onSelectFeeder(fid)}
                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-colors cursor-pointer flex-shrink-0 ${
                  feeder.id === fid
                    ? 'bg-[#073B3A] text-white shadow-xs'
                    : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {fid}
              </button>
            ))}
          </div>
        </div>

        {/* Large Confident Statement */}
        <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold text-slate-900 tracking-tight font-display leading-[1.15] sm:leading-[1.1] max-w-3xl">
          {isMitigated && feeder.id === 'F07' ? (
            <span className="text-emerald-800">Overload mitigated. Operating at 94 MW.</span>
          ) : feeder.timeToOverloadMin ? (
            <span>Overload risk in <span className="text-red-600">{formatTto(feeder.timeToOverloadMin)}</span>.</span>
          ) : (
            <span className="text-emerald-800">Operating nominal. Within safe capacity limits.</span>
          )}
        </h1>

        <p className="text-sm sm:text-base text-slate-500 font-normal">
          {feeder.name} • Substation {feeder.substationName} • {feeder.voltageKv} kV Circuit
        </p>
      </div>

      {/* 2. LARGE TYPOGRAPHY METRICS WITH THIN DIVIDERS (2-Col Mobile, 5-Col Desktop) */}
      <div className="py-6 border-y border-slate-200/80 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 sm:gap-6">
        <div>
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Current Load
          </span>
          <div className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-slate-900 font-display mt-1">
            {feeder.currentLoadMw} <span className="text-sm font-semibold text-slate-400">MW</span>
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            Actual T0 telemetry
          </span>
        </div>

        <div className="border-l border-slate-200/80 pl-4 sm:pl-6">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Capacity
          </span>
          <div className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-slate-900 font-display mt-1">
            {feeder.capacityMw} <span className="text-sm font-semibold text-slate-400">MW</span>
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            Continuous rating
          </span>
        </div>

        <div className="border-t border-slate-200/80 sm:border-t-0 pt-4 sm:pt-0 sm:border-l sm:border-slate-200/80 sm:pl-6">
          <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
            Predicted Peak
          </span>
          <div className={`text-2xl sm:text-3xl lg:text-4xl font-extrabold font-display mt-1 ${feeder.peakForecastMw > feeder.capacityMw ? 'text-red-600' : 'text-slate-900'}`}>
            {feeder.peakForecastMw} <span className={`text-sm font-semibold ${feeder.peakForecastMw > feeder.capacityMw ? 'text-red-400' : 'text-slate-400'}`}>MW</span>
          </div>
          <span className={`text-xs font-medium mt-0.5 block ${feeder.peakForecastMw > feeder.capacityMw ? 'text-red-600' : 'text-slate-500'}`}>
            {feeder.peakForecastMw > feeder.capacityMw
              ? `+${(feeder.peakForecastMw - feeder.capacityMw).toFixed(1)} MW over rating`
              : 'Within thermal rating'}
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
          <div className={`text-2xl sm:text-3xl lg:text-4xl font-extrabold font-display mt-1 ${feeder.timeToOverloadMin ? 'text-red-600' : 'text-emerald-700'}`}>
            {isMitigated && feeder.id === 'F07' ? 'SAFE' : formatTto(feeder.timeToOverloadMin)}
          </div>
          <span className="text-xs text-slate-500 font-medium mt-0.5 block">
            {isMitigated && feeder.id === 'F07' ? 'Mitigation active' : feeder.timeToOverloadMin ? 'Action countdown' : 'No overload risk'}
          </span>
        </div>
      </div>

      {/* 3. CENTERPIECE FORECAST VISUAL */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-7 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div>
            <h2 className="text-base font-bold text-slate-900 font-display">
              60-Minute Predictive Demand Curve
            </h2>
            <p className="text-xs text-slate-500">
              Discrete steps: Current, +15m, +30m, +45m, +60m vs {feeder.capacityMw} MW thermal limit
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
              <span>Mitigated Curve Active</span>
            </span>
          )}
        </div>

        {isLoading ? (
          <div className="h-64 flex items-center justify-center text-slate-400 text-xs font-medium">
            Loading feeder forecast telemetry...
          </div>
        ) : (
          <ForecastHorizonChart
            data={forecast}
            capacityMw={feeder.capacityMw}
            showMitigated={isMitigated}
            highlightBreach={!isMitigated && feeder.riskLevel === 'CRITICAL'}
          />
        )}
      </div>

      {/* 4. WHY FEEDER IS AT RISK */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-7 shadow-xs space-y-4">
        <div className="border-b border-slate-100 pb-3">
          <div className="text-[11px] uppercase font-bold text-teal-800 tracking-wider">
            Model Explainability
          </div>
          <h2 className="text-base sm:text-lg font-bold text-slate-900 font-display mt-0.5">
            Why Feeder {feeder.id} is {feeder.riskLevel === 'CRITICAL' || feeder.riskLevel === 'HIGH' ? 'at Risk' : 'Nominal'}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Ranked root-cause SHAP attribution drivers computed from live SCADA and telemetry features
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
          Deep Technical Telemetry (Click to Expand)
        </div>

        {/* 1. Why this matters */}
        <CollapsibleSection
          title="WHY THIS MATTERS"
          subtitle="Impact of thermal line overload on distribution transformer lifespan and customer continuity"
          isOpen={openSection === 'why_matters'}
          onToggle={() => toggleSection('why_matters')}
        >
          <div className="p-5 bg-slate-50 border border-slate-200/70 rounded-xl text-sm sm:text-[15px] text-slate-700 leading-relaxed space-y-3">
            <p>
              Operating above 100 MW initiates cumulative thermal annealing of aluminum conductor steel-reinforced (ACSR) lines, accelerating line sag by 300% and risking ground fault contact.
            </p>
            <p>
              If unmitigated, Substation Alpha’s SEL-751 protective overcurrent relay will trigger an automatic lockout at +48 minutes, cutting service to 14,200 commercial and residential meters.
            </p>
          </div>
        </CollapsibleSection>

        {/* 2. Feeder Telemetry */}
        <CollapsibleSection
          title="FEEDER TELEMETRY & SENSORS"
          subtitle="Real-time electrical parameters, phase balance, and conductor thermal estimates"
          isOpen={openSection === 'telemetry'}
          onToggle={() => toggleSection('telemetry')}
        >
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-1">
            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl">
              <span className="text-slate-400 text-xs uppercase font-bold tracking-wider block">Bus Voltage</span>
              <span className="text-2xl font-bold text-slate-900 font-display mt-1 block">{feeder.voltageKv} kV</span>
              <span className="text-xs text-slate-500 mt-0.5 block">Nominal 11.00 kV (-1.6%)</span>
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl">
              <span className="text-slate-400 text-xs uppercase font-bold tracking-wider block">Reactive Power</span>
              <span className="text-2xl font-bold text-slate-900 font-display mt-1 block">14.2 MVAR</span>
              <span className="text-xs text-slate-500 mt-0.5 block">Inductive industrial load</span>
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl">
              <span className="text-slate-400 text-xs uppercase font-bold tracking-wider block">Power Factor</span>
              <span className="text-2xl font-bold text-slate-900 font-display mt-1 block">0.94 Lag</span>
              <span className="text-xs text-slate-500 mt-0.5 block">Within IEEE 519 target</span>
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl">
              <span className="text-slate-400 text-xs uppercase font-bold tracking-wider block">Conductor Temp</span>
              <span className="text-2xl font-bold text-amber-600 font-display mt-1 block">78 °C</span>
              <span className="text-xs text-slate-500 mt-0.5 block">Trip setpoint: 90 °C</span>
            </div>
          </div>
        </CollapsibleSection>

        {/* 3. Technical & Substation Details */}
        <CollapsibleSection
          title="TECHNICAL & SUBSTATION DETAILS"
          subtitle="Substation Alpha asset ratings, protection relay curves, and OpenADR links"
          isOpen={openSection === 'technical'}
          onToggle={() => toggleSection('technical')}
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl space-y-2">
              <span className="text-sm sm:text-[15px] font-bold text-slate-900 block font-display">Substation Alpha Transformers</span>
              <div className="text-slate-600 text-xs sm:text-[13px] space-y-1">
                <div>• Unit T-1: 110/11 kV (120 MVA rated)</div>
                <div>• On-Load Tap Changer: Step +4</div>
                <div>• Station Total Output: 242 MW</div>
              </div>
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl space-y-2">
              <span className="text-sm sm:text-[15px] font-bold text-slate-900 block font-display">Protection Relay Configurations</span>
              <div className="text-slate-600 text-xs sm:text-[13px] space-y-1">
                <div>• Relay Model: SEL-751 Feeder Relay</div>
                <div>• Pickup Threshold: 5,200 A (105 MW)</div>
                <div>• Curve: ANSI Moderately Inverse 51</div>
              </div>
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl space-y-2">
              <span className="text-sm sm:text-[15px] font-bold text-slate-900 block font-display">Communication Links</span>
              <div className="text-slate-600 text-xs sm:text-[13px] space-y-1">
                <div>• OpenADR 2.0b: Online & Verified</div>
                <div>• Substation RTU: Modbus TCP latency 28ms</div>
                <div>• BESS Unit 2 Gateway: Ready for command</div>
              </div>
            </div>
          </div>
        </CollapsibleSection>
      </div>
    </div>
  );
};
