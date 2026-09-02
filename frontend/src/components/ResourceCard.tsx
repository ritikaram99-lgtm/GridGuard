import React from 'react';
import { FlexibleResource } from '../types';
import { Zap, BatteryCharging, Factory, Check, Plus } from 'lucide-react';

interface ResourceCardProps {
  resource: FlexibleResource;
  onToggle: (id: string) => void;
  onReductionChange?: (id: string, mw: number) => void;
  isRecommended?: boolean;
}

export const ResourceCard: React.FC<ResourceCardProps> = ({
  resource,
  onToggle,
  isRecommended = false,
}) => {
  const getResourceIcon = () => {
    switch (resource.type) {
      case 'EV':
        return <Zap className="w-4 h-4 text-teal-700" />;
      case 'BATTERY':
        return <BatteryCharging className="w-4 h-4 text-emerald-600" />;
      case 'INDUSTRIAL':
        return <Factory className="w-4 h-4 text-slate-600" />;
    }
  };

  const getDisruptionBadge = () => {
    switch (resource.disruptionLevel) {
      case 'None':
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-50 border border-emerald-200 text-emerald-800">
            Zero Impact
          </span>
        );
      case 'Minimal':
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-amber-50 border border-amber-200 text-amber-800">
            Minimal
          </span>
        );
      case 'High':
        return (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-red-50 border border-red-200 text-red-700">
            High Disruption
          </span>
        );
    }
  };

  return (
    <div
      className={`bg-white border rounded-xl p-4 sm:p-5 transition-all ${
        resource.isEnabled
          ? 'border-teal-700/80 bg-teal-50/20 shadow-xs'
          : 'border-slate-200/90 hover:border-slate-300'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start space-x-3.5">
          <div className="p-2.5 rounded-xl bg-slate-100 border border-slate-200/80 text-slate-700 mt-0.5 flex-shrink-0">
            {getResourceIcon()}
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h4 className="text-sm sm:text-base font-bold text-slate-900 font-display">
                {resource.name}
              </h4>
              {isRecommended && (
                <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full bg-teal-50 text-teal-800 border border-teal-200">
                  Recommended
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{resource.summary}</p>
          </div>
        </div>

        {/* Clean Enterprise Toggle Button with touch target >= 44px */}
        <button
          onClick={() => onToggle(resource.id)}
          className={`flex items-center space-x-1.5 px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex-shrink-0 cursor-pointer min-h-[44px] ${
            resource.isEnabled
              ? 'bg-[#073B3A] hover:bg-[#0B5D56] text-white shadow-xs'
              : 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-50'
          }`}
        >
          {resource.isEnabled ? (
            <>
              <Check className="w-4 h-4 text-lime-300" />
              <span>Engaged</span>
            </>
          ) : (
            <>
              <Plus className="w-4 h-4 text-slate-400" />
              <span>Include</span>
            </>
          )}
        </button>
      </div>

      {/* Metrics Row with Clean Dividers */}
      <div className="grid grid-cols-3 gap-2 sm:gap-4 mt-4 pt-3.5 border-t border-slate-100 text-xs">
        <div>
          <span className="text-slate-400 text-[10px] uppercase font-bold tracking-wider block">Target Reduction</span>
          <span className="text-sm font-extrabold text-slate-900 font-display mt-0.5 block">
            {resource.isEnabled ? `${resource.selectedReductionMw.toFixed(1)} MW` : '0.0 MW'}
          </span>
          <span className="text-[11px] text-slate-400">Max: {resource.maxReductionMw.toFixed(1)} MW</span>
        </div>

        <div>
          <span className="text-slate-400 text-[10px] uppercase font-bold tracking-wider block">Estimated Cost</span>
          <span className="text-sm font-extrabold text-slate-900 font-display mt-0.5 block">
            ${resource.estimatedCostDemo}
          </span>
          <span className="text-[10px] text-slate-400 italic">Synthetic Index</span>
        </div>

        <div>
          <span className="text-slate-400 text-[10px] uppercase font-bold tracking-wider block">Disruption Tier</span>
          <div className="mt-1">{getDisruptionBadge()}</div>
        </div>
      </div>
    </div>
  );
};
