import React, { useState } from 'react';
import { Plus, Minus } from 'lucide-react';

interface CollapsibleSectionProps {
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  defaultOpen?: boolean;
  isOpen?: boolean;
  onToggle?: () => void;
  children: React.ReactNode;
  headerRight?: React.ReactNode;
  className?: string;
}

export const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
  title,
  subtitle,
  badge,
  defaultOpen = false,
  isOpen: controlledIsOpen,
  onToggle,
  children,
  headerRight,
  className = '',
}) => {
  const [internalIsOpen, setInternalIsOpen] = useState(defaultOpen);
  const isExpanded = controlledIsOpen !== undefined ? controlledIsOpen : internalIsOpen;

  const handleToggle = () => {
    if (onToggle) {
      onToggle();
    } else {
      setInternalIsOpen(prev => !prev);
    }
  };

  return (
    <div className={`border-t border-slate-200/80 transition-all ${className}`}>
      {/* Editorial Expandable Row Header */}
      <div className="py-4 flex flex-wrap sm:flex-nowrap items-center justify-between gap-3 sm:gap-4 min-h-[44px]">
        <div
          role="button"
          tabIndex={0}
          onClick={handleToggle}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleToggle();
            }
          }}
          className="flex-1 flex items-start sm:items-center space-x-3 sm:space-x-3.5 cursor-pointer select-none group min-h-[44px]"
          aria-expanded={isExpanded}
        >
          <span className="w-7 h-7 sm:w-6 sm:h-6 rounded-full border border-slate-300 group-hover:border-slate-500 flex items-center justify-center text-slate-500 group-hover:text-slate-900 transition-colors flex-shrink-0 mt-0.5 sm:mt-0">
            {isExpanded ? (
              <Minus className="w-3.5 h-3.5 text-slate-700" />
            ) : (
              <Plus className="w-3.5 h-3.5 text-slate-500" />
            )}
          </span>

          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm sm:text-base font-bold text-slate-900 tracking-tight font-display group-hover:text-[#073B3A] transition-colors">
                {title}
              </span>
              {badge}
            </div>
            {subtitle && (
              <p className="text-[13px] text-slate-500 mt-0.5 leading-normal">{subtitle}</p>
            )}
          </div>
        </div>

        <div className="flex items-center space-x-3 flex-shrink-0 self-end sm:self-center pl-10 sm:pl-0">
          {headerRight}
          <button
            type="button"
            onClick={handleToggle}
            className="text-xs sm:text-[13px] font-bold uppercase tracking-wider text-slate-400 hover:text-slate-700 hidden sm:inline cursor-pointer min-h-[36px] items-center"
          >
            {isExpanded ? 'Hide' : 'Expand'}
          </button>
        </div>
      </div>

      {/* Expanded Content with Generous Whitespace */}
      {isExpanded && (
        <div className="pb-6 pt-1 animate-in fade-in-50 duration-200">
          {children}
        </div>
      )}
    </div>
  );
};
