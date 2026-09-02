import React from 'react';
import { RiskLevel } from '../types';
import { getRiskColorClass } from '../utils/formatters';

interface RiskBadgeProps {
  level: RiskLevel;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showDotOnly?: boolean;
}

export const RiskBadge: React.FC<RiskBadgeProps> = ({ 
  level, 
  className = '', 
  size = 'md',
  showDotOnly = false,
}) => {
  const styles = getRiskColorClass(level);
  
  if (showDotOnly) {
    return (
      <span className="relative flex items-center justify-center" title={level}>
        <span className={`w-2 h-2 rounded-full ${styles.dot}`} />
      </span>
    );
  }

  const sizeClasses = size === 'sm' 
    ? 'px-2.5 py-0.5 text-xs sm:text-[13px] font-semibold rounded-md' 
    : size === 'lg' 
    ? 'px-3.5 py-1 text-sm font-bold rounded-md' 
    : 'px-3 py-0.5 text-sm font-semibold rounded-md';

  return (
    <span
      className={`inline-flex items-center space-x-1.5 rounded font-medium border ${styles.bg} ${styles.text} ${styles.border} ${sizeClasses} ${className}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${styles.dot}`} />
      <span>{level}</span>
    </span>
  );
};
