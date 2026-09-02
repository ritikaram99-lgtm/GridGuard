import React, { useState, useEffect } from 'react';
import { PreventionPlan, FlexibleResource } from '../types';
import { gridService } from '../api/gridService';
import { ResourceCard } from '../components/ResourceCard';
import { CounterfactualChart } from '../charts/CounterfactualChart';
import { CollapsibleSection } from '../components/CollapsibleSection';
import { 
  ShieldCheck, 
  CheckCircle2, 
  RotateCcw, 
  Send, 
  ArrowRight, 
  LineChart, 
  Sliders, 
  Info,
  Zap,
  ArrowDown,
  AlertCircle
} from 'lucide-react';

interface PreventionCenterProps {
  feederId?: string;
  isMitigated: boolean;
  onApplyMitigation: () => void;
  onResetMitigation: () => void;
}

export const PreventionCenter: React.FC<PreventionCenterProps> = ({
  feederId = 'F07',
  isMitigated,
  onApplyMitigation,
  onResetMitigation,
}) => {
  const [plan, setPlan] = useState<PreventionPlan | null>(null);
  const [resources, setResources] = useState<FlexibleResource[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [showDispatchModal, setShowDispatchModal] = useState<boolean>(false);

  // Progressive disclosure states (all collapsed by default)
  const [openSection, setOpenSection] = useState<'details' | 'resources' | 'counterfactual' | null>(null);

  useEffect(() => {
    async function loadPlan() {
      setIsLoading(true);
      try {
        const data = await gridService.getPreventionPlan(feederId);
        setPlan(data);
        setResources(data.resources);
      } catch (err) {
        console.error('Failed to load prevention plan:', err);
      } finally {
        setIsLoading(false);
      }
    }
    loadPlan();
  }, [feederId]);

  const handleToggleResource = (id: string) => {
    setResources(prev =>
      prev.map(r => {
        if (r.id === id) {
          const nextState = !r.isEnabled;
          return {
            ...r,
            isEnabled: nextState,
            selectedReductionMw: nextState ? (r.type === 'EV' ? 5.0 : r.type === 'BATTERY' ? 9.0 : 8.0) : 0,
          };
        }
        return r;
      })
    );
  };

  const applyRecommendedCombination = () => {
    setResources(prev =>
      prev.map(r => {
        if (r.type === 'EV') {
          return { ...r, isEnabled: true, selectedReductionMw: 5.0 };
        }
        if (r.type === 'BATTERY') {
          return { ...r, isEnabled: true, selectedReductionMw: 9.0 };
        }
        if (r.type === 'INDUSTRIAL') {
          return { ...r, isEnabled: false, selectedReductionMw: 0.0 };
        }
        return r;
      })
    );
  };

  const toggleSection = (section: 'details' | 'resources' | 'counterfactual') => {
    setOpenSection(prev => (prev === section ? null : section));
  };

  if (isLoading || !plan) {
    return (
      <div className="h-72 flex items-center justify-center text-slate-400 text-xs font-medium">
        Evaluating flexible resource options and counterfactuals...
      </div>
    );
  }

  // Dynamic calculations from active resources
  const totalReductionMw = resources
    .filter(r => r.isEnabled)
    .reduce((sum, r) => sum + r.selectedReductionMw, 0);

  const evReduction = resources.find(r => r.type === 'EV' && r.isEnabled)?.selectedReductionMw || 0;
  const battReduction = resources.find(r => r.type === 'BATTERY' && r.isEnabled)?.selectedReductionMw || 0;
  const indReduction = resources.find(r => r.type === 'INDUSTRIAL' && r.isEnabled)?.selectedReductionMw || 0;

  const totalCostDemo = resources
    .filter(r => r.isEnabled)
    .reduce((sum, r) => sum + r.estimatedCostDemo, 0);

  const predictedPeakMw = plan.predictedPeakMw; // 108 MW
  const capacityMw = plan.capacityMw;           // 100 MW
  const expectedPeakMw = Math.round((predictedPeakMw - totalReductionMw) * 10) / 10;
  const isSafe = expectedPeakMw <= capacityMw;

  // Dynamic counterfactual points
  const dynamicForecast = plan.counterfactualPoints.map(pt => {
    let mitigatedVal = pt.forecastLoadMw;
    if (pt.timeStep !== 'Current') {
      mitigatedVal = Math.round((pt.forecastLoadMw - totalReductionMw) * 10) / 10;
    }
    return {
      ...pt,
      mitigatedLoadMw: mitigatedVal,
    };
  });

  const handleConfirmDispatch = () => {
    onApplyMitigation();
    setShowDispatchModal(false);
  };

  return (
    <div className="space-y-8 sm:space-y-10">
      {/* 1. TOP EDITORIAL HERO STATEMENT */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-2 text-[11px] font-bold uppercase tracking-widest-sm text-teal-800">
            <span>PREVENTION ENGINE / LIVE DISPATCH</span>
          </div>

          {isMitigated && (
            <div className="flex items-center space-x-2">
              <span className="px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center space-x-1.5 shadow-2xs">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>Intervention Dispatched to Grid</span>
              </span>
              <button
                onClick={onResetMitigation}
                className="p-1 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-500 transition-colors cursor-pointer"
                title="Reset simulation"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>

        <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-slate-900 tracking-tight font-display max-w-3xl leading-[1.1]">
          Prevent the overload before it happens.
        </h1>
        <p className="text-sm sm:text-base text-slate-600 max-w-2xl font-normal leading-relaxed pt-1">
          GridGuard automated decision support recommends the lowest-disruption flexible resource combination to protect Feeder F07.
        </p>
      </div>

      {/* 2. THE SIGNATURE WOW HERO VISUAL: 108 MW -> 94 MW (OVERLOAD AVOIDED) */}
      <div className="bg-white border-2 border-teal-800/20 rounded-2xl p-6 sm:p-8 shadow-sm space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
          <div>
            <span className="text-[11px] uppercase font-bold text-teal-800 tracking-wider block">
              Automated Dispatch Recommendation
            </span>
            <div className="text-lg sm:text-xl font-extrabold text-slate-900 font-display mt-0.5">
              EV Smart Charging Shift + Battery Storage Discharge
            </div>
          </div>
          <div className="flex items-center space-x-4 text-xs">
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold">EV Shift</span>
              <span className="font-extrabold text-slate-900 text-sm">
                {evReduction > 0 ? `-${evReduction.toFixed(1)} MW` : '0.0 MW'}
              </span>
            </div>
            <span className="text-slate-300 font-normal">+</span>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Battery</span>
              <span className="font-extrabold text-slate-900 text-sm">
                {battReduction > 0 ? `-${battReduction.toFixed(1)} MW` : '0.0 MW'}
              </span>
            </div>
            {indReduction > 0 && (
              <>
                <span className="text-slate-300 font-normal">+</span>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-bold">Industrial</span>
                  <span className="font-extrabold text-slate-900 text-sm">
                    -{indReduction.toFixed(1)} MW
                  </span>
                </div>
              </>
            )}
            <span className="text-slate-300 font-normal">=</span>
            <div>
              <span className="text-teal-800 block text-[10px] uppercase font-bold">Intervention</span>
              <span className="font-extrabold text-teal-800 text-sm">
                -{totalReductionMw.toFixed(1)} MW
              </span>
            </div>
          </div>
        </div>

        {/* Visual Flow: Dynamic Peak -> Curtailment -> Resulting Peak */}
        <div className="bg-[#F4FAF7] border border-slate-200/90 rounded-xl p-5 sm:p-6 flex flex-col lg:flex-row items-center justify-between gap-5 sm:gap-6">
          {/* Desktop & Tablet Row (sm+) */}
          <div className="hidden sm:flex items-center space-x-4 sm:space-x-8">
            <div>
              <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                Uncontrolled Peak
              </span>
              <div className="text-3xl sm:text-4xl font-extrabold text-red-600 font-display mt-1">
                {predictedPeakMw} <span className="text-sm font-semibold text-red-400">MW</span>
              </div>
            </div>

            <ArrowRight className="w-5 h-5 text-slate-400 flex-shrink-0" />

            <div>
              <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                GridGuard Curtailment
              </span>
              <div className="text-3xl sm:text-4xl font-extrabold text-teal-800 font-display mt-1">
                -{totalReductionMw.toFixed(1)} <span className="text-sm font-semibold text-teal-600">MW</span>
              </div>
            </div>

            <ArrowRight className="w-5 h-5 text-slate-400 flex-shrink-0" />

            <div>
              <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                {isSafe ? 'Safe Operating Peak' : 'Projected Operating Peak'}
              </span>
              <div className={`text-3xl sm:text-4xl font-extrabold font-display mt-1 ${isSafe ? 'text-emerald-700' : 'text-red-600'}`}>
                {expectedPeakMw.toFixed(1)} <span className={`text-sm font-semibold ${isSafe ? 'text-emerald-600' : 'text-red-400'}`}>MW</span>
              </div>
            </div>
          </div>

          {/* Mobile Stack (< sm) */}
          <div className="sm:hidden w-full space-y-3.5 text-center">
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                Uncontrolled Peak
              </span>
              <div className="text-3xl font-extrabold text-red-600 font-display mt-0.5">
                {predictedPeakMw} <span className="text-sm font-semibold text-red-400">MW</span>
              </div>
            </div>

            <div className="flex items-center justify-center space-x-1.5 text-xs text-teal-800 font-bold bg-teal-50 py-2 px-3 rounded-lg border border-teal-200">
              <span>↓ Active Curtailment: -{totalReductionMw.toFixed(1)} MW</span>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block">
                {isSafe ? 'Safe Operating Peak' : 'Projected Operating Peak'}
              </span>
              <div className={`text-3xl font-extrabold font-display mt-0.5 ${isSafe ? 'text-emerald-700' : 'text-red-600'}`}>
                {expectedPeakMw.toFixed(1)} <span className={`text-sm font-semibold ${isSafe ? 'text-emerald-600' : 'text-red-400'}`}>MW</span>
              </div>
            </div>
          </div>

          <div className={`w-full sm:w-auto px-4 py-2.5 rounded-xl border font-extrabold text-xs sm:text-sm flex items-center justify-center space-x-2 shadow-2xs flex-shrink-0 ${
            isSafe
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}>
            {isSafe ? (
              <>
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>OVERLOAD AVOIDED (+{(capacityMw - expectedPeakMw).toFixed(1)} MW MARGIN)</span>
              </>
            ) : (
              <>
                <AlertCircle className="w-4 h-4 text-red-600" />
                <span>INSUFFICIENT CURTAILMENT (+{(expectedPeakMw - capacityMw).toFixed(1)} MW OVERLOAD)</span>
              </>
            )}
          </div>
        </div>

        {/* Primary vs Secondary Action Buttons - Full-width stacked on mobile */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 sm:gap-4 pt-2">
          <button
            onClick={() => toggleSection('counterfactual')}
            className="w-full sm:w-auto px-5 py-3 rounded-xl bg-[#073B3A] hover:bg-[#0B5D56] text-white text-xs font-bold transition-all shadow-sm flex items-center justify-center space-x-2 cursor-pointer min-h-[44px]"
          >
            <LineChart className="w-4 h-4" />
            <span>Simulate Intervention</span>
          </button>

          <button
            onClick={() => setShowDispatchModal(true)}
            disabled={!isSafe || isMitigated}
            className={`w-full sm:w-auto px-5 py-3 rounded-xl text-xs font-semibold transition-all border min-h-[44px] flex items-center justify-center ${
              isSafe && !isMitigated
                ? 'bg-white border-slate-300 text-slate-800 hover:bg-slate-50 cursor-pointer shadow-xs'
                : 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            <span>{isMitigated ? 'Intervention Active on Grid' : 'Dispatch Action to Grid →'}</span>
          </button>
        </div>
      </div>

      {/* 3. PROGRESSIVE DISCLOSURE COLLAPSIBLE SECTIONS */}
      <div className="space-y-1">
        <div className="text-xs uppercase font-bold text-slate-400 tracking-widest-sm mb-3">
          Supporting Intervention Proof & Resources (Click to Expand)
        </div>

        {/* 1. Intervention Details */}
        <CollapsibleSection
          title="INTERVENTION DETAILS"
          subtitle="Minimum required reduction (8 MW) vs recommended safety-margin target (14 MW to 94 MW)"
          isOpen={openSection === 'details'}
          onToggle={() => toggleSection('details')}
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl space-y-1">
              <span className="text-xs uppercase font-bold text-slate-400 tracking-wider block">Minimum Required</span>
              <div className="text-2xl font-extrabold text-slate-900 font-display mt-0.5">
                8.0 MW
              </div>
              <p className="text-xs sm:text-[13px] text-slate-600 leading-relaxed pt-1">
                Strict mathematical minimum required to bring 108 MW down to the 100 MW continuous threshold limit.
              </p>
            </div>

            <div className="p-4 bg-teal-50/40 border border-teal-200/80 rounded-xl space-y-1">
              <span className="text-xs uppercase font-bold text-teal-800 tracking-wider block">Recommended Reduction</span>
              <div className="text-2xl font-extrabold text-teal-800 font-display mt-0.5">
                14.0 MW
              </div>
              <p className="text-xs sm:text-[13px] text-teal-800/90 leading-relaxed pt-1">
                Preferred intervention providing a 6% safety margin against unexpected intra-hour temperature spikes.
              </p>
            </div>

            <div className="p-4 bg-emerald-50/40 border border-emerald-200/80 rounded-xl space-y-1">
              <span className="text-xs uppercase font-bold text-emerald-800 tracking-wider block">Safety Margin Headroom</span>
              <div className="text-2xl font-extrabold text-emerald-700 font-display mt-0.5">
                94.0 MW
              </div>
              <p className="text-xs sm:text-[13px] text-emerald-800/90 leading-relaxed pt-1">
                Net operating peak ensures continuous conductor reliability without tripping substation relays.
              </p>
            </div>
          </div>
        </CollapsibleSection>

        {/* 2. Available Flexible Resources */}
        <CollapsibleSection
          title="AVAILABLE FLEXIBLE RESOURCES"
          subtitle="EV Fleet, Battery Storage Unit 2, and Industrial Demand Response capabilities"
          badge={
            <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700">
              3 APPROVED ASSETS
            </span>
          }
          isOpen={openSection === 'resources'}
          onToggle={() => toggleSection('resources')}
          headerRight={
            <button
              onClick={(e) => {
                e.stopPropagation();
                applyRecommendedCombination();
              }}
              className="text-xs font-bold text-teal-800 hover:text-teal-900 hover:underline cursor-pointer"
            >
              Reset to Recommended
            </button>
          }
        >
          <div className="space-y-3 pt-1">
            <div className="space-y-2.5">
              {resources.map(res => (
                <ResourceCard
                  key={res.id}
                  resource={res}
                  onToggle={handleToggleResource}
                  isRecommended={res.type === 'EV' || res.type === 'BATTERY'}
                />
              ))}
            </div>

            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/70 text-xs sm:text-[13px] text-slate-600 leading-relaxed">
              <strong className="text-slate-800 font-semibold">Pricing Note:</strong> Displayed costs ($120 EV, $280 Battery, $1,200 Industrial) are synthetic demo relative indices and do not represent real utility-market clearing prices.
            </div>
          </div>
        </CollapsibleSection>

        {/* 3. Counterfactual Simulation (Core Proof) */}
        <CollapsibleSection
          title="COUNTERFACTUAL SIMULATION PROOF"
          subtitle="Comparison of WITHOUT ACTION (108 MW) vs WITH GRIDGUARD (94 MW)"
          badge={
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
              Proof Verified
            </span>
          }
          isOpen={openSection === 'counterfactual'}
          onToggle={() => toggleSection('counterfactual')}
        >
          <div className="pt-2 bg-white border border-slate-200/90 rounded-2xl p-6 shadow-xs">
            <CounterfactualChart
              data={dynamicForecast}
              capacityMw={capacityMw}
            />
          </div>
        </CollapsibleSection>
      </div>

      {/* Confirmation Dispatch Modal */}
      {showDispatchModal && (
        <div className="fixed inset-0 z-[3000] flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4 animate-in fade-in-50 duration-150">
          <div className="bg-white border border-slate-200 rounded-2xl p-6 max-w-md w-full shadow-xl space-y-4">
            <div className="flex items-center space-x-3 text-teal-900 border-b border-slate-100 pb-3">
              <ShieldCheck className="w-6 h-6 text-teal-700" />
              <div>
                <h3 className="text-base font-bold text-slate-900 font-display">Authorize Grid Dispatch</h3>
                <p className="text-xs text-slate-500">Automated SCADA & OpenADR command execution</p>
              </div>
            </div>

            <div className="text-xs text-slate-600 space-y-3">
              <p>
                Authorizing immediate dispatch of flexible curtailment resources onto <strong>Feeder F07</strong>:
              </p>
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2 text-xs">
                <div className="flex justify-between text-slate-700">
                  <span>EV Fleet Throttle:</span>
                  <span className="font-bold">{evReduction.toFixed(1)} MW</span>
                </div>
                <div className="flex justify-between text-slate-700">
                  <span>BESS Battery Discharge:</span>
                  <span className="font-bold">{battReduction.toFixed(1)} MW</span>
                </div>
                {indReduction > 0 && (
                  <div className="flex justify-between text-slate-700">
                    <span>Industrial Demand Response:</span>
                    <span className="font-bold">{indReduction.toFixed(1)} MW</span>
                  </div>
                )}
                <div className="border-t border-slate-200 pt-1.5 flex justify-between font-bold text-slate-900">
                  <span>Total Intervention Reduction:</span>
                  <span className="text-teal-800">{totalReductionMw.toFixed(1)} MW</span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Resulting Operating Peak:</span>
                  <span className={`font-bold ${isSafe ? 'text-emerald-700' : 'text-red-600'}`}>
                    {expectedPeakMw.toFixed(1)} MW ({isSafe ? 'SAFE' : 'OVERLOAD'})
                  </span>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 italic">
                Signals dispatched via OpenADR 2.0b VEN profiles and Substation Alpha Modbus RTU.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-end gap-2.5 sm:gap-3 pt-3 border-t border-slate-100">
              <button
                onClick={() => setShowDispatchModal(false)}
                className="w-full sm:w-auto px-4 py-2.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold cursor-pointer min-h-[44px] text-center"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDispatch}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-[#073B3A] hover:bg-[#0B5D56] text-white text-xs font-bold shadow-sm cursor-pointer min-h-[44px] text-center"
              >
                Execute Dispatch Now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
