import React from 'react';
import { ShapContributor } from '../types';

interface ShapContributorsBarChartProps {
  contributors: ShapContributor[];
  feederId: string;
}

export const ShapContributorsBarChart: React.FC<ShapContributorsBarChartProps> = ({
  contributors,
  feederId,
}) => {
  if (contributors.length === 0) {
    return (
      <div className="text-xs text-slate-400 text-center py-6">
        No active risk contributors returned for feeder {feederId}.
      </div>
    );
  }

  const maxImpact = Math.max(...contributors.map(c => c.impactMw), 0.1);
  const totalImpact = contributors.reduce((sum, c) => sum + c.impactMw, 0);
  const top = [...contributors].sort((a, b) => b.impactMw - a.impactMw)[0];
  const topPct = totalImpact > 0 ? Math.round((top.impactMw / totalImpact) * 100) : 0;

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center justify-between text-xs text-slate-400 font-bold uppercase tracking-wider border-b border-slate-100 pb-2">
        <span>Ranked Overload Drivers</span>
        <span>Attribution Impact</span>
      </div>

      <div className="divide-y divide-slate-100">
        {contributors.map((item, idx) => {
          const barWidthPercent = Math.min(100, Math.round((item.impactMw / maxImpact) * 100));
          const pctShare = Math.round((item.impactMw / totalImpact) * 100);
          const num = String(idx + 1).padStart(2, '0');
          return (
            <div key={item.id} className="py-3 first:pt-0 last:pb-0">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 sm:gap-4 mb-1.5">
                <div className="flex items-start sm:items-center space-x-2.5 sm:space-x-3">
                  <span className="text-xs font-mono font-bold text-slate-400 mt-0.5 sm:mt-0">{num}</span>
                  <div>
                    <span className="text-sm font-bold text-slate-900 font-display">
                      {item.featureName}
                    </span>
                    <span className="text-xs text-slate-500 block">
                      {item.description}
                    </span>
                  </div>
                </div>

                <div className="flex items-center space-x-2 sm:block sm:text-right pl-6 sm:pl-0 flex-shrink-0">
                  <span className="text-sm font-extrabold text-red-600 font-display">
                    +{item.impactMw.toFixed(1)} MW
                  </span>
                  <span className="text-xs font-semibold text-slate-400 sm:ml-2 font-mono">
                    +{pctShare}%
                  </span>
                </div>
              </div>

              {/* Clean minimal progress bar in deep teal */}
              <div className="w-full h-1.5 rounded-full bg-slate-100 overflow-hidden ml-6 sm:ml-7 max-w-[calc(100%-24px)] sm:max-w-[calc(100%-28px)]">
                <div
                  className="h-full rounded-full bg-[#073B3A] transition-all duration-300"
                  style={{ width: `${barWidthPercent}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 p-4 rounded-xl bg-slate-50 border border-slate-200/70 text-xs text-slate-600 leading-relaxed">
        <strong className="text-slate-900 font-semibold">Largest contributor:</strong> "{top.featureName}" accounts for {topPct}% of feeder {feederId}'s current stress-score contribution ({top.impactMw.toFixed(1)} points), per the backend's own returned breakdown.
      </div>
    </div>
  );
};
