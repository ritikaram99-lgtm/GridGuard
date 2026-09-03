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

interface ForecastHorizonChartProps {
  data: ForecastPoint[];
  capacityMw?: number;
  showMitigated?: boolean;
  highlightBreach?: boolean;
  /** Real ML Stress Engine time-to-overload (hour-resolution estimate). */
  timeToOverloadHours?: number | null;
}

export const ForecastHorizonChart: React.FC<ForecastHorizonChartProps> = ({
  data,
  capacityMw = 100,
  showMitigated = false,
  highlightBreach = true,
  timeToOverloadHours = null,
}) => {
  const chartData = data.map(d => ({
    timeStep: d.timeStep,
    actualLoad: d.actualLoadMw,
    forecastLoad: d.forecastLoadMw,
    mitigatedLoad: d.mitigatedLoadMw ?? null,
    capacity: capacityMw,
    isOverload: d.forecastLoadMw != null && d.forecastLoadMw > capacityMw,
  }));

  const forecastValues = data.map(d => d.forecastLoadMw).filter((v): v is number => v != null);
  const maxVal = forecastValues.length
    ? Math.max(capacityMw + 12, ...forecastValues, ...data.map(d => d.mitigatedLoadMw ?? 0))
    : capacityMw + 12;
  const minVal = forecastValues.length
    ? Math.max(0, Math.min(60, ...forecastValues) - 10)
    : 0;
  const isHourly = data.some(d => d.timestamp != null);

  return (
    <div className="w-full flex flex-col">
      <div className="text-[10px] uppercase font-bold tracking-wider text-slate-400 mb-1.5 px-1">
        {isHourly ? '24-Hour ML Forecast (hourly resolution)' : 'Legacy 15/30/45/60-Minute Forecast'}
      </div>
      {/* Editorial Chart Legend & Breach Status */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 text-[11px] sm:text-xs text-slate-500 mb-3 px-1">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <span className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-800 inline-block"></span>
            <span className="text-slate-700 font-semibold">Actual Demand</span>
          </span>
          <span className="flex items-center space-x-1.5">
            <span className="w-3.5 h-1 bg-[#073B3A] rounded-full inline-block"></span>
            <span className="text-[#073B3A] font-bold">Forecast Trajectory</span>
          </span>
          {showMitigated && (
            <span className="flex items-center space-x-1.5">
              <span className="w-3.5 h-1 bg-emerald-600 rounded-full inline-block"></span>
              <span className="text-emerald-700 font-semibold">Post-Action</span>
            </span>
          )}
          <span className="flex items-center space-x-1.5">
            <span className="w-3.5 border-t-2 border-dashed border-red-500 inline-block"></span>
            <span className="text-red-700 font-semibold">Capacity ({capacityMw.toFixed(1)} MW)</span>
          </span>
        </div>
        {highlightBreach && (
          <span className="text-xs px-2.5 py-0.5 rounded-full bg-red-50 border border-red-200 text-red-700 font-bold">
            {timeToOverloadHours != null
              ? `Est. overload in ~${timeToOverloadHours.toFixed(1)}h`
              : 'Overload risk elevated'}
          </span>
        )}
      </div>

      <div className="w-full h-[280px] sm:h-72 lg:h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 15, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey="timeStep"
              stroke="#94a3b8"
              tick={{ fill: '#64748b', fontSize: 11, fontWeight: 500 }}
              tickLine={{ stroke: '#cbd5e1' }}
            />
            <YAxis
              domain={[minVal, maxVal]}
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
                  <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-md text-xs min-w-[170px]">
                    <div className="font-bold text-slate-900 border-b border-slate-100 pb-1 mb-1.5 font-display">
                      Horizon: {label}
                    </div>
                    {p.actualLoad != null && (
                      <div className="flex justify-between items-center text-slate-700 mb-1 space-x-3">
                        <span>Actual Demand:</span>
                        <span className="font-bold">{p.actualLoad.toFixed(1)} MW</span>
                      </div>
                    )}
                    {p.forecastLoad != null ? (
                      <div className="flex justify-between items-center text-[#073B3A] mb-1 space-x-3">
                        <span className="font-semibold">Forecast Load:</span>
                        <span className="font-extrabold">{p.forecastLoad.toFixed(1)} MW</span>
                      </div>
                    ) : (
                      <div className="text-slate-400 mb-1">No forecast value at this point.</div>
                    )}
                    {p.mitigatedLoad != null && (
                      <div className="flex justify-between items-center text-emerald-700 mb-1 space-x-3">
                        <span>Post-Action:</span>
                        <span className="font-bold">{p.mitigatedLoad.toFixed(1)} MW</span>
                      </div>
                    )}
                    <div className="flex justify-between items-center text-red-600 pt-1 border-t border-slate-100 space-x-3">
                      <span>Capacity:</span>
                      <span className="font-bold">{p.capacity.toFixed(1)} MW</span>
                    </div>
                    {p.isOverload && p.forecastLoad != null && (
                      <div className="mt-1.5 px-2 py-0.5 bg-red-50 border border-red-200 rounded-md text-red-700 text-center font-bold text-[11px]">
                        +{(p.forecastLoad - p.capacity).toFixed(1)} MW Overload
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
            {/* Forecast Line in deep teal */}
            <Line
              type="monotone"
              dataKey="forecastLoad"
              stroke="#073B3A"
              strokeWidth={3}
              dot={{ fill: '#073B3A', r: 4, stroke: '#ffffff', strokeWidth: 2 }}
              activeDot={{ r: 6, fill: '#0B5D56' }}
              name="Forecast Load"
            />
            {/* Mitigated Line in green */}
            {showMitigated && (
              <Line
                type="monotone"
                dataKey="mitigatedLoad"
                stroke="#16a34a"
                strokeWidth={2.5}
                strokeDasharray="4 4"
                dot={{ fill: '#16a34a', r: 3.5, stroke: '#ffffff', strokeWidth: 1.5 }}
                activeDot={{ r: 5, fill: '#15803d' }}
                name="Post-Mitigation"
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
