import React, { useState, useEffect } from 'react';
import { PreventionPlan, FlexibleResource, BackendSimulationResponse } from '../types';
import { gridService } from '../api/gridService';
import { ResourceCard } from '../components/ResourceCard';
import { CounterfactualChart } from '../charts/CounterfactualChart';
import { CollapsibleSection } from '../components/CollapsibleSection';
import {
  ShieldCheck,
  CheckCircle2,
  RotateCcw,
  ArrowRight,
  LineChart,
  Info,
  AlertCircle,
} from 'lucide-react';

interface PreventionCenterProps {
  feederId: string;
  isMitigated: boolean;
  onApplyMitigation: () => void;
  onResetMitigation: () => void;
}

export const PreventionCenter: React.FC<PreventionCenterProps> = ({
  feederId,
  isMitigated,
  onApplyMitigation,
  onResetMitigation,
}) => {
  const [plan, setPlan] = useState<PreventionPlan | null>(null);
  const [resources, setResources] = useState<FlexibleResource[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [showDispatchModal, setShowDispatchModal] = useState<boolean>(false);
  const [isDispatching, setIsDispatching] = useState<boolean>(false);
  const [simResult, setSimResult] = useState<BackendSimulationResponse | null>(null);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);

  // Progressive disclosure states (all collapsed by default)
  const [openSection, setOpenSection] = useState<'details' | 'resources' | 'candidates' | 'counterfactual' | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadPlan() {
      setIsLoading(true);
      setSimResult(null);
      try {
        const data = await gridService.getPreventionPlan(feederId);
        if (cancelled) return;
        setPlan(data);
        setResources(data.resources);
      } catch (err) {
        console.error('Failed to load prevention plan:', err);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    loadPlan();
    return () => { cancelled = true; };
  }, [feederId]);

  const handleToggleResource = (id: string) => {
    setResources(prev =>
      prev.map(r => (r.id === id ? { ...r, isEnabled: !r.isEnabled } : r))
    );
  };

  const toggleSection = (section: 'details' | 'resources' | 'candidates' | 'counterfactual') => {
    setOpenSection(prev => (prev === section ? null : section));
  };

  if (isLoading || !plan) {
    return (
      <div className="h-72 flex items-center justify-center text-slate-400 text-xs font-medium">
        Loading recommendation...
      </div>
    );
  }

  // All figures below are real backend values (plan.*, resources[].*) or
  // straightforward arithmetic over them -- no independently invented numbers.
  const enabled = resources.filter(r => r.isEnabled);
  const totalReductionMw = Math.round(enabled.reduce((sum, r) => sum + r.selectedReductionMw, 0) * 10) / 10;
  const totalCostDemo = Math.round(enabled.reduce((sum, r) => sum + r.estimatedCostDemo, 0) * 10) / 10;
  const expectedPeakMw = Math.round((plan.predictedPeakMw - totalReductionMw) * 10) / 10;
  const isSafe = expectedPeakMw <= plan.capacityMw || plan.status === 'PREVENTED' || plan.status === 'NO_ACTION_REQUIRED';
  const hasNoActionNeeded = plan.status === 'NO_ACTION_REQUIRED' || (plan.status === 'SAFE' && resources.length === 0) || plan.actionRequired === false;
  const insufficientFlexibility = plan.status === 'INSUFFICIENT_FLEXIBILITY' || (plan.status === 'OVERLOAD' && resources.length === 0);

  // Applies the currently-selected MW reduction across forecast points
  // to visualize counterfactual load mitigation on the horizon chart.
  const counterfactualPoints = plan.forecastPoints.map(pt => ({
    ...pt,
    mitigatedLoadMw: pt.forecastLoadMw != null
      ? Math.max(0, Math.round((pt.forecastLoadMw - totalReductionMw) * 10) / 10)
      : null,
  }));

  const handleConfirmDispatch = async () => {
    setIsDispatching(true);
    try {
      const actionsToDispatch = enabled.map(r => ({ action_type: r.actionType, reduction_mw: r.selectedReductionMw }));
      if (actionsToDispatch.length > 0) {
        await gridService.dispatchActions(feederId, actionsToDispatch);
      }
      onApplyMitigation();
      setShowDispatchModal(false);
    } catch (err) {
      console.error('Failed to dispatch actions:', err);
    } finally {
      setIsDispatching(false);
    }
  };

  const handleSimulate = async () => {
    toggleSection('counterfactual');
    setIsSimulating(true);
    try {
      const evReduction = enabled.filter(r => r.actionType === 'EV_SHIFT' || r.actionType === 'EV').reduce((s, r) => s + r.selectedReductionMw, 0);
      const battReduction = enabled.filter(r => r.actionType === 'BATTERY').reduce((s, r) => s + r.selectedReductionMw, 0);
      const indReduction = enabled.filter(r => r.actionType === 'INDUSTRIAL').reduce((s, r) => s + r.selectedReductionMw, 0);
      const result = await gridService.simulateIntervention(feederId, {
        ev_shift: evReduction,
        battery: battReduction,
        industrial: indReduction,
      });
      setSimResult(result);
    } catch (err) {
      console.error('Failed to simulate intervention:', err);
      setSimResult(null);
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <div className="space-y-8 sm:space-y-10">
      {/* 1. TOP EDITORIAL HERO STATEMENT */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center space-x-2 text-[11px] font-bold uppercase tracking-widest-sm text-teal-800">
            <span>OVERLOAD PREVENTION / TAKE ACTION</span>
            {plan.source === 'ml_action_engine' && (
              <span className="px-2 py-0.5 rounded bg-teal-50 text-teal-800 text-[10px] border border-teal-200">
                REAL ML ACTION ENGINE
              </span>
            )}
          </div>

          {isMitigated && (
            <div className="flex items-center space-x-2">
              <span className="px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center space-x-1.5 shadow-2xs">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>Intervention Dispatched</span>
              </span>
              <button
                onClick={onResetMitigation}
                className="p-1 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-500 transition-colors cursor-pointer"
                title="Reset"
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
          GridGuard recommends the most cost-effective and lowest-disruption actions to protect Feeder {plan.feederId}.
        </p>
      </div>

      {/* 2. SUGGESTED ACTION PLAN MAIN CARD */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-8 shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-5">
          <div>
            <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block mb-1">
              SUGGESTED ACTION PLAN
            </span>
            <h2 className="text-xl sm:text-2xl font-extrabold text-slate-900 font-display">
              {enabled.length > 0
                ? enabled.map(r => r.name).join(' + ')
                : (resources.length > 0 ? resources.map(r => r.name).join(' + ') : 'No Action Required')}
            </h2>
          </div>

          {resources.length > 0 && (
            <div className="flex items-center flex-wrap gap-x-6 gap-y-2 text-xs font-bold sm:justify-end">
              {enabled.map(r => (
                <div key={r.id} className="text-left sm:text-right">
                  <span className="text-[10px] uppercase text-slate-400 block font-bold tracking-wider">
                    {r.name.toUpperCase()}
                  </span>
                  <span className="text-slate-900 font-extrabold text-sm">
                    -{r.selectedReductionMw.toFixed(1)} MW
                  </span>
                </div>
              ))}
              <div className="text-left sm:text-right border-l border-slate-200 pl-4">
                <span className="text-[10px] uppercase text-teal-800 block font-bold tracking-wider">
                  TOTAL REDUCTION
                </span>
                <span className="text-teal-800 font-extrabold text-sm">
                  -{totalReductionMw.toFixed(1)} MW
                </span>
              </div>
            </div>
          )}
        </div>

        {plan.reason && (
          <div className="bg-slate-50 border border-slate-200/90 rounded-xl p-4 flex items-start space-x-3 text-xs sm:text-sm text-slate-700">
            <Info className="w-4 h-4 text-teal-700 mt-0.5 flex-shrink-0" />
            <div>
              <span className="font-bold block text-slate-900 mb-0.5">
                ML Action Engine Rationale:
              </span>
              <span>{plan.reason}</span>
            </div>
          </div>
        )}

        {hasNoActionNeeded ? (
          <div className="bg-emerald-50/60 border border-emerald-200/90 rounded-xl p-5 flex items-start space-x-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-emerald-900">
              No intervention required: predicted peak {plan.predictedPeakMw.toFixed(1)} MW is within normal operating limits and risk is LOW/MODERATE.
            </div>
          </div>
        ) : insufficientFlexibility ? (
          <div className="bg-red-50/60 border border-red-200/90 rounded-xl p-5 flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-red-900">
              Insufficient flexibility: available synthetic flexible resources are not enough to fully prevent the risk.
            </div>
          </div>
        ) : (
          <div className="bg-[#F4FAF7] border border-slate-200/90 rounded-2xl p-5 sm:p-6 flex flex-col lg:flex-row items-center justify-between gap-5 sm:gap-6">
            <div className="flex flex-wrap items-center gap-x-4 sm:gap-x-8 gap-y-3">
              <div>
                <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                  FORECASTED PEAK WITHOUT ACTION
                </span>
                <div className="text-2xl sm:text-3xl font-extrabold text-red-600 font-display mt-1">
                  {plan.predictedPeakMw.toFixed(1)} <span className="text-sm font-semibold text-red-400">MW</span>
                </div>
              </div>

              <ArrowRight className="w-5 h-5 text-slate-400 flex-shrink-0" />

              <div>
                <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                  SUGGESTED POWER REDUCTION
                </span>
                <div className="text-2xl sm:text-3xl font-extrabold text-teal-800 font-display mt-1">
                  -{totalReductionMw.toFixed(1)} <span className="text-sm font-semibold text-teal-600">MW</span>
                </div>
              </div>

              <ArrowRight className="w-5 h-5 text-slate-400 flex-shrink-0" />

              <div>
                <span className="text-[11px] uppercase font-bold text-slate-400 tracking-wider block">
                  EXPECTED LOAD AFTER ACTION
                </span>
                <div className={`text-2xl sm:text-3xl font-extrabold font-display mt-1 ${isSafe ? 'text-emerald-700' : 'text-red-600'}`}>
                  {expectedPeakMw.toFixed(1)} <span className={`text-sm font-semibold ${isSafe ? 'text-emerald-600' : 'text-red-400'}`}>MW</span>
                </div>
              </div>
            </div>

            <div className={`w-full sm:w-auto px-4 py-2.5 rounded-full border font-extrabold text-xs sm:text-sm flex items-center justify-center space-x-2 shadow-2xs flex-shrink-0 ${
              isSafe
                ? 'bg-emerald-100/80 border-emerald-300/80 text-emerald-800'
                : 'bg-red-50 border-red-200 text-red-700'
            }`}>
              {isSafe ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>
                    {plan.capacityMw - expectedPeakMw > 0
                      ? `SAFE (+${(plan.capacityMw - expectedPeakMw).toFixed(1)} MW SAFETY MARGIN)`
                      : 'RISK MITIGATED BEFORE OVERLOAD'}
                  </span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4 text-red-600" />
                  <span>INSUFFICIENT CURTAILMENT (+{(expectedPeakMw - plan.capacityMw).toFixed(1)} MW OVER)</span>
                </>
              )}
            </div>
          </div>
        )}

        {resources.length > 0 && (
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 sm:gap-4 pt-2">
            <button
              onClick={handleSimulate}
              disabled={isSimulating}
              className="w-full sm:w-auto px-5 py-3 rounded-xl bg-[#073B3A] hover:bg-[#0B5D56] text-white text-xs font-bold transition-all shadow-sm flex items-center justify-center space-x-2 cursor-pointer min-h-[44px] disabled:opacity-60"
            >
              <LineChart className="w-4 h-4" />
              <span>{isSimulating ? 'Simulating...' : 'Preview Outcome'}</span>
            </button>

            <button
              onClick={() => setShowDispatchModal(true)}
              disabled={enabled.length === 0 || isMitigated}
              className={`w-full sm:w-auto px-5 py-3 rounded-xl text-xs font-semibold transition-all border min-h-[44px] flex items-center justify-center ${
                enabled.length > 0 && !isMitigated
                  ? 'bg-white border-slate-300 text-slate-800 hover:bg-slate-50 cursor-pointer shadow-xs'
                  : 'bg-slate-100 border-slate-200 text-slate-400 cursor-not-allowed'
              }`}
            >
              <span>{isMitigated ? 'Intervention Confirmed' : 'Apply Actions to Grid →'}</span>
            </button>
          </div>
        )}
      </div>

      {/* 3. PROGRESSIVE DISCLOSURE COLLAPSIBLE SECTIONS */}
      <div className="space-y-1">
        <div className="text-xs uppercase font-bold text-slate-400 tracking-wider mb-3">
          DETAILS & AVAILABLE OPTIONS (CLICK TO EXPAND)
        </div>

        {/* 1. Reduction Targets & Safety Margin */}
        <CollapsibleSection
          title="REDUCTION TARGETS & SAFETY MARGIN"
          subtitle="Minimum required reduction vs recommended safety margin target"
          isOpen={openSection === 'details'}
          onToggle={() => toggleSection('details')}
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl space-y-1">
              <span className="text-xs uppercase font-bold text-slate-400 tracking-wider block">Required Reduction</span>
              <div className="text-2xl font-extrabold text-slate-900 font-display mt-0.5">
                {plan.requiredReductionMw.toFixed(1)} MW
              </div>
              <p className="text-xs sm:text-[13px] text-slate-600 leading-relaxed pt-1">
                Minimum reduction to bring {plan.predictedPeakMw.toFixed(1)} MW under the {plan.capacityMw.toFixed(1)} MW capacity.
              </p>
            </div>

            <div className="p-4 bg-teal-50/40 border border-teal-200/80 rounded-xl space-y-1">
              <span className="text-xs uppercase font-bold text-teal-800 tracking-wider block">Predicted After</span>
              <div className="text-2xl font-extrabold text-teal-800 font-display mt-0.5">
                {plan.predictedAfterMw.toFixed(1)} MW
              </div>
              <p className="text-xs sm:text-[13px] text-teal-800/90 leading-relaxed pt-1">
                Peak load if all recommended actions are applied.
              </p>
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200/70 rounded-xl space-y-1">
              <span className="text-xs uppercase font-bold text-slate-400 tracking-wider block">Status</span>
              <div className="text-2xl font-extrabold text-slate-900 font-display mt-0.5">
                {plan.status}
              </div>
              <p className="text-xs sm:text-[13px] text-slate-600 leading-relaxed pt-1">
                Recommendation status.
              </p>
            </div>
          </div>
        </CollapsibleSection>

        {/* 2. Available Action Options */}
        {resources.length > 0 && (
          <CollapsibleSection
            title="AVAILABLE ACTION OPTIONS"
            subtitle="EV charging controls, energy storage batteries, and commercial reduction options"
            badge={
              <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700">
                {resources.length} AVAILABLE OPTIONS
              </span>
            }
            isOpen={openSection === 'resources'}
            onToggle={() => toggleSection('resources')}
          >
            <div className="space-y-3 pt-1">
              <div className="space-y-2.5">
                {resources.map(res => (
                  <ResourceCard
                    key={res.id}
                    resource={res}
                    onToggle={handleToggleResource}
                    isRecommended
                  />
                ))}
              </div>
            </div>
          </CollapsibleSection>
        )}

        {/* 3. Evaluated Candidate Interventions (Real ML Prevention Engine) */}
        {plan.alternatives && plan.alternatives.length > 0 && (
          <CollapsibleSection
            title="EVALUATED CANDIDATE INTERVENTIONS"
            subtitle="Deterministic priority ranking of all candidate combinations tested"
            badge={
              <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700">
                {plan.candidatesEvaluated ?? plan.alternatives.length} CANDIDATES
              </span>
            }
            isOpen={openSection === 'candidates'}
            onToggle={() => toggleSection('candidates')}
          >
            <div className="pt-2">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-100 text-slate-400 uppercase font-bold tracking-wider">
                      <th className="py-2 px-3">Intervention Candidate</th>
                      <th className="py-2 px-3">Disruption Cost</th>
                      <th className="py-2 px-3">Total Reduction</th>
                      <th className="py-2 px-3">Projected Risk</th>
                      <th className="py-2 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-medium text-slate-700">
                    {plan.alternatives.map((alt, idx) => (
                      <tr key={idx} className={idx === 0 ? 'bg-teal-50/50 font-bold' : ''}>
                        <td className="py-2.5 px-3 flex items-center space-x-1.5">
                          <span>{alt.label}</span>
                          {idx === 0 && (
                            <span className="px-1.5 py-0.5 rounded bg-teal-800 text-white text-[10px] uppercase font-extrabold">
                              Selected
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3">{alt.cost.toFixed(1)}</td>
                        <td className="py-2.5 px-3">{alt.total_reduction_mw.toFixed(2)} MW</td>
                        <td className="py-2.5 px-3">
                          <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                            alt.projected_risk === 'LOW' ? 'bg-emerald-100 text-emerald-800' :
                            alt.projected_risk === 'MODERATE' ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800'
                          }`}>
                            {alt.projected_risk}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          {alt.resolved ? (
                            <span className="text-emerald-700 font-bold">Resolved</span>
                          ) : (
                            <span className="text-red-600 font-bold">Unresolved</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </CollapsibleSection>
        )}

        {/* 3. Simulation result (real backend /api/simulate via ML Simulation Engine) */}
        <CollapsibleSection
          title="SIMULATION RESULT"
          subtitle="Real counterfactual trajectory evaluation from the ML Simulation Engine (ml/src/simulation_engine.py)"
          badge={
            simResult ? (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                Live Response
              </span>
            ) : undefined
          }
          isOpen={openSection === 'counterfactual'}
          onToggle={() => toggleSection('counterfactual')}
        >
          {simResult ? (
            <div className="pt-2 space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 bg-slate-50 border border-slate-200/70 rounded-xl">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Forecast Peak</span>
                  <span className="text-lg font-extrabold text-slate-900 font-display">{simResult.forecast_peak.toFixed(1)} MW</span>
                </div>
                <div className="p-3 bg-slate-50 border border-slate-200/70 rounded-xl">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Total Reduction</span>
                  <span className="text-lg font-extrabold text-slate-900 font-display">{simResult.total_reduction.toFixed(1)} MW</span>
                </div>
                <div className="p-3 bg-slate-50 border border-slate-200/70 rounded-xl">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Simulated Load</span>
                  <span className="text-lg font-extrabold text-slate-900 font-display">{simResult.simulated_load.toFixed(1)} MW</span>
                </div>
                <div className="p-3 bg-slate-50 border border-slate-200/70 rounded-xl">
                  <span className="text-[10px] uppercase font-bold text-slate-400 block">Status</span>
                  <span className="text-lg font-extrabold text-slate-900 font-display">{simResult.status}</span>
                </div>
              </div>

              <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-xs">
                <div className="text-xs text-slate-500 mb-3 flex items-start gap-2">
                  <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-slate-400" />
                  <span>
                    Illustrative trajectory: applies the constant selected reduction ({totalReductionMw.toFixed(1)} MW) across the real
                    forecast curve below. The simulation only returns a single before/after peak, not a full mitigated
                    hourly trajectory.
                  </span>
                </div>
                <CounterfactualChart data={counterfactualPoints} capacityMw={plan.capacityMw} />
              </div>
            </div>
          ) : (
            <div className="pt-2 text-xs text-slate-400 text-center py-6">
              Run "Simulate Selected Actions" above to see a simulated result.
            </div>
          )}
        </CollapsibleSection>
      </div>

      {/* Confirmation Dispatch Modal */}
      {showDispatchModal && (
        <div className="fixed inset-0 z-[3000] flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4 animate-in fade-in-50 duration-150">
          <div className="bg-white border border-slate-200 rounded-2xl p-6 max-w-md w-full shadow-xl space-y-4">
            <div className="flex items-center space-x-3 text-teal-900 border-b border-slate-100 pb-3">
              <ShieldCheck className="w-6 h-6 text-teal-700" />
              <div>
                <h3 className="text-base font-bold text-slate-900 font-display">Confirm Dispatch</h3>
                <p className="text-xs text-slate-500">Calls POST /api/dispatch with the selected actions</p>
              </div>
            </div>

            <div className="text-xs text-slate-600 space-y-3">
              <p>
                Dispatching flexible curtailment resources onto <strong>Feeder {plan.feederId}</strong>:
              </p>
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2 text-xs">
                {enabled.map(r => (
                  <div key={r.id} className="flex justify-between text-slate-700">
                    <span>{r.name}:</span>
                    <span className="font-bold">{r.selectedReductionMw.toFixed(1)} MW</span>
                  </div>
                ))}
                <div className="border-t border-slate-200 pt-1.5 flex justify-between font-bold text-slate-900">
                  <span>Total Selected Reduction:</span>
                  <span className="text-teal-800">{totalReductionMw.toFixed(1)} MW</span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Total Cost (synthetic index):</span>
                  <span className="font-bold">${totalCostDemo.toFixed(0)}</span>
                </div>
                <div className="flex justify-between text-slate-600">
                  <span>Expected Peak After:</span>
                  <span className={`font-bold ${isSafe ? 'text-emerald-700' : 'text-red-600'}`}>
                    {expectedPeakMw.toFixed(1)} MW ({isSafe ? 'WITHIN CAPACITY' : 'OVER CAPACITY'})
                  </span>
                </div>
              </div>
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
                disabled={isDispatching}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-[#073B3A] hover:bg-[#0B5D56] text-white text-xs font-bold shadow-sm cursor-pointer min-h-[44px] text-center disabled:opacity-50"
              >
                {isDispatching ? 'Dispatching...' : 'Execute Dispatch Now'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
