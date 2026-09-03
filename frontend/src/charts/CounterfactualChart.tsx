import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import { ForecastPoint } from '../types';

interface CounterfactualChartProps {
  data: ForecastPoint[];
  capacityMw?: number;
}

export const CounterfactualChart: React.FC<CounterfactualChartProps> = ({
  data,
  capacityMw = 100,
}) => {
  const chartData = data.map(d => ({
    timeStep: d.timeStep,
    withoutAction: d.forecastLoadMw,
    withGridGuard: d.mitigatedLoadMw ?? d.forecastLoadMw,
    capacity: capacityMw,
    deltaAvoidedMw: d.forecastLoadMw != null ? d.forecastLoadMw - (d.mitigatedLoadMw ?? d.forecastLoadMw) : null,
  }));

  const withoutActionPeak = Math.max(0, ...data.map(d => d.forecastLoadMw ?? 0));
  const withGridGuardPeak = Math.max(0, ...data.map(d => d.mitigatedLoadMw ?? d.forecastLoadMw ?? 0));
  const isSafe = withGridGuardPeak <= capacityMw;
  const yMax = Math.max(capacityMw, withoutActionPeak) + 10;
  const yMin = Math.max(0, Math.min(capacityMw, withGridGuardPeak) - 10);

  return (
    <div className="w-full flex flex-col space-y-4">
      {/* Editorial Legend & Badge */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs px-1">
        <div className="flex items-center space-x-5">
          <div className="flex items-center space-x-1.5">
            <span className="w-3.5 h-1 bg-red-600 rounded-full inline-block"></span>
            <span className="text-slate-700 font-bold">Without Action (Peak {withoutActionPeak.toFixed(1)} MW)</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3.5 h-1 bg-emerald-600 rounded-full inline-block"></span>
            <span className="text-slate-700 font-bold">With Selected Actions ({withGridGuardPeak.toFixed(1)} MW)</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-3.5 border-t-2 border-dashed border-slate-400 inline-block"></span>
            <span className="text-slate-500 font-semibold">Capacity ({capacityMw.toFixed(1)} MW)</span>
          </div>
        </div>

        <div>
          <span className={`px-3 py-1 rounded-full font-extrabold text-xs inline-flex items-center space-x-1.5 shadow-2xs border ${
            isSafe
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isSafe ? 'bg-emerald-600' : 'bg-red-600'}`}></span>
            <span>{isSafe ? `OVERLOAD AVOIDED (+${(capacityMw - withGridGuardPeak).toFixed(1)} MW HEADROOM)` : `STILL OVER (+${(withGridGuardPeak - capacityMw).toFixed(1)} MW)`}</span>
          </span>
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="w-full h-72 sm:h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 15, right: 20, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey="timeStep"
              stroke="#94a3b8"
              tick={{ fill: '#64748b', fontSize: 11, fontWeight: 500 }}
              tickLine={{ stroke: '#cbd5e1' }}
            />
            <YAxis
              domain={[yMin, yMax]}
              stroke="#94a3b8"
              tick={{ fill: '#64748b', fontSize: 11, fontWeight: 500 }}
              tickFormatter={(v) => `${Math.round(v)} MW`}
              tickLine={{ stroke: '#cbd5e1' }}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload || !payload.length) return null;
                const p = payload[0].payload;
                return (
                  <div className="bg-white border border-slate-200 rounded-xl p-3.5 shadow-md text-xs min-w-[190px]">
                    <div className="font-bold text-slate-900 border-b border-slate-100 pb-1 mb-2 font-display">
                      Horizon: {label}
                    </div>
                    <div className="flex justify-between items-center text-red-600 mb-1 space-x-3">
                      <span>Without Action:</span>
                      <span className="font-extrabold">{p.withoutAction} MW</span>
                    </div>
                    <div className="flex justify-between items-center text-emerald-700 mb-1 space-x-3">
                      <span>With GridGuard:</span>
                      <span className="font-extrabold">{p.withGridGuard} MW</span>
                    </div>
                    {p.deltaAvoidedMw != null && (
                      <div className="flex justify-between items-center text-slate-500 pt-1.5 border-t border-slate-100 space-x-3">
                        <span>Restored Buffer:</span>
                        <span className="font-extrabold text-emerald-700">+{p.deltaAvoidedMw.toFixed(1)} MW</span>
                      </div>
                    )}
                  </div>
                );
              }}
            />
            <ReferenceLine
              y={capacityMw}
              stroke="#dc2626"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{
                value: `Capacity: ${capacityMw.toFixed(1)} MW`,
                fill: '#dc2626',
                fontSize: 11,
                fontWeight: 600,
                position: 'insideTopRight',
              }}
            />
            <ReferenceLine
              y={withGridGuardPeak}
              stroke="#16a34a"
              strokeDasharray="2 2"
              strokeWidth={1}
              label={{
                value: `Selected-Action Peak: ${withGridGuardPeak.toFixed(1)} MW`,
                fill: '#15803d',
                fontSize: 10,
                fontWeight: 600,
                position: 'insideBottomRight',
              }}
            />
            {/* Without Action Line */}
            <Line
              type="monotone"
              dataKey="withoutAction"
              stroke="#dc2626"
              strokeWidth={3}
              dot={{ fill: '#dc2626', r: 4, stroke: '#ffffff', strokeWidth: 2 }}
              activeDot={{ r: 6, fill: '#b91c1c' }}
              name="Without Action"
            />
            {/* With GridGuard Line */}
            <Line
              type="monotone"
              dataKey="withGridGuard"
              stroke="#16a34a"
              strokeWidth={3}
              dot={{ fill: '#16a34a', r: 4, stroke: '#ffffff', strokeWidth: 2 }}
              activeDot={{ r: 6, fill: '#15803d' }}
              name="With GridGuard"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Desktop & Tablet: Discrete Side-by-Side Timeline Sequence */}
      <div className="hidden sm:grid gap-2 sm:gap-3" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(72px, 1fr))` }}>
        {data.map((pt) => {
          const without = pt.forecastLoadMw;
          const withGg = pt.mitigatedLoadMw ?? pt.forecastLoadMw;
          const isOver = without != null && without > capacityMw;
          return (
            <div
              key={pt.timeStep}
              className={`p-3 rounded-xl border text-center transition-all ${
                isOver ? 'bg-red-50/40 border-red-200/90' : 'bg-slate-50 border-slate-200/80'
              }`}
            >
              <div className="text-[11px] text-slate-500 font-bold uppercase tracking-wider">{pt.timeStep}</div>
              <div className="text-sm font-extrabold text-red-600 font-display mt-1">
                {without != null ? without.toFixed(1) : '--'} <span className="text-[10px] font-normal text-slate-400">MW</span>
              </div>
              <div className="text-[10px] text-slate-400 my-0.5">↓ with action</div>
              <div className="text-sm font-extrabold text-emerald-700 font-display">
                {withGg != null ? withGg.toFixed(1) : '--'} <span className="text-[10px] font-normal text-emerald-500">MW</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Mobile Stacked Sequence (< sm) */}
      <div className="sm:hidden space-y-2.5 pt-1">
        <div className="p-3 rounded-xl bg-red-50/50 border border-red-200/90">
          <div className="text-[10px] uppercase font-bold text-red-700 tracking-wider mb-1.5 flex items-center justify-between">
            <span>Without Action</span>
            <span className="text-red-600 font-mono">{withoutActionPeak.toFixed(1)} MW Peak</span>
          </div>
          <div className="flex items-center justify-between text-xs font-bold text-red-600 font-display">
            {data.map(pt => (
              <div key={pt.timeStep} className="text-center">
                <span className="text-[10px] text-slate-400 block font-normal">{pt.timeStep}</span>
                <span>{pt.forecastLoadMw != null ? pt.forecastLoadMw.toFixed(1) : '--'}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="p-3 rounded-xl bg-emerald-50/60 border border-emerald-200/90">
          <div className="text-[10px] uppercase font-bold text-emerald-800 tracking-wider mb-1.5 flex items-center justify-between">
            <span>With Selected Actions</span>
            <span className="text-emerald-700 font-mono">{withGridGuardPeak.toFixed(1)} MW {isSafe ? 'Safe' : ''}</span>
          </div>
          <div className="flex items-center justify-between text-xs font-bold text-emerald-700 font-display">
            {data.map(pt => (
              <div key={pt.timeStep} className="text-center">
                <span className="text-[10px] text-slate-400 block font-normal">{pt.timeStep}</span>
                <span>{(pt.mitigatedLoadMw ?? pt.forecastLoadMw) != null ? (pt.mitigatedLoadMw ?? pt.forecastLoadMw)!.toFixed(1) : '--'}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
