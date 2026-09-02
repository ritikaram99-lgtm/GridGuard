import React from 'react';

interface MetricTileProps {
  label: string;
  value: string | number;
  unit?: string;
  subtext?: string;
  statusColor?: 'emerald' | 'amber' | 'red' | 'blue' | 'slate';
  badge?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

export const MetricTile: React.FC<MetricTileProps> = ({
  label,
  value,
  unit,
  subtext,
  statusColor = 'slate',
  badge,
  icon,
  className = '',
}) => {
  const getTextColor = () => {
    switch (statusColor) {
      case 'red':
        return 'text-red-600';
      case 'amber':
        return 'text-amber-600';
      case 'emerald':
        return 'text-emerald-600';
      case 'blue':
        return 'text-blue-600';
      default:
        return 'text-slate-900';
    }
  };

  return (
    <div className={`bg-white border border-slate-200/90 rounded-lg p-3.5 shadow-sm transition-all hover:border-slate-300 ${className}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-slate-500">
          {label}
        </span>
        <div className="flex items-center space-x-1.5">
          {badge}
          {icon && <span className="text-slate-400">{icon}</span>}
        </div>
      </div>
      <div className="flex items-baseline space-x-1">
        <span className={`text-xl font-bold tracking-tight ${getTextColor()}`}>
          {value}
        </span>
        {unit && <span className="text-xs font-normal text-slate-500">{unit}</span>}
      </div>
      {subtext && <div className="mt-1 text-[11px] text-slate-500 leading-tight">{subtext}</div>}
    </div>
  );
};
