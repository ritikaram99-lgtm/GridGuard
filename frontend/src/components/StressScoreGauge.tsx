import React from 'react';
import { getStressScoreColor } from '../utils/formatters';

interface StressScoreGaugeProps {
  score: number; // 0 - 100
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

export const StressScoreGauge: React.FC<StressScoreGaugeProps> = ({ 
  score, 
  size = 'md',
  showLabel = true,
}) => {
  const colorClass = getStressScoreColor(score);
  const strokeColor = score >= 85 ? '#dc2626' : score >= 65 ? '#d97706' : score >= 40 ? '#2563eb' : '#16a34a';

  // SVG dimensions
  const radius = size === 'lg' ? 36 : size === 'sm' ? 20 : 26;
  const strokeWidth = size === 'lg' ? 6 : size === 'sm' ? 4 : 5;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  const dimension = (radius + strokeWidth) * 2;

  return (
    <div className="flex items-center space-x-2.5">
      <div className="relative flex items-center justify-center flex-shrink-0" style={{ width: dimension, height: dimension }}>
        <svg className="transform -rotate-90" width={dimension} height={dimension}>
          {/* Background circle */}
          <circle
            cx={dimension / 2}
            cy={dimension / 2}
            r={radius}
            stroke="#e2e8f0"
            strokeWidth={strokeWidth}
            fill="transparent"
          />
          {/* Active progress */}
          <circle
            cx={dimension / 2}
            cy={dimension / 2}
            r={radius}
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            fill="transparent"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`font-bold leading-none ${colorClass} ${size === 'lg' ? 'text-lg' : size === 'sm' ? 'text-[12px]' : 'text-xs'}`}>
            {score}
          </span>
        </div>
      </div>
      {showLabel && (
        <div>
          <div className="text-[11px] text-slate-500 font-medium leading-tight">Stress Score</div>
          <div className={`font-semibold text-xs leading-tight ${colorClass}`}>
            {score >= 85 ? 'Critical' : score >= 65 ? 'Elevated' : score >= 40 ? 'Moderate' : 'Nominal'}
          </div>
        </div>
      )}
    </div>
  );
};
