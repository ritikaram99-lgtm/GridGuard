import React, { useState } from 'react';
import { ScenarioId } from '../types';
import { MOCK_SCENARIOS } from '../data/scenarios';
import { ScreenTab } from '../layouts/DashboardLayout';
import { Zap, HelpCircle, Menu, X, ArrowRight, ShieldCheck, AlertCircle } from 'lucide-react';

interface HeaderProps {
  activeScreen: ScreenTab;
  onScreenChange: (tab: ScreenTab) => void;
  activeScenarioId: ScenarioId;
  onScenarioChange: (id: ScenarioId) => void;
  isMitigated: boolean;
  selectedFeederId: string;
  onOpenCopilot: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeScreen,
  onScreenChange,
  activeScenarioId,
  onScenarioChange,
  isMitigated,
  selectedFeederId,
  onOpenCopilot,
}) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const navItems: { id: ScreenTab; label: string; hasWarning?: boolean }[] = [
    { id: 'command_center', label: 'Overview' },
    { 
      id: 'feeder_intelligence', 
      label: 'Feeder Intelligence', 
      hasWarning: selectedFeederId === 'F07' && !isMitigated 
    },
    { id: 'prevention_center', label: 'Prevention' },
    { id: 'what_if_simulator', label: 'What-If' },
  ];

  const handleNavClick = (id: ScreenTab) => {
    onScreenChange(id);
    setIsMobileMenuOpen(false);
  };

  return (
    <header className="w-full bg-white/95 backdrop-blur-md border-b border-slate-200/80 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3 sm:gap-6">
        {/* Left: Confident Brand Identity */}
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-lg bg-[#073B3A] flex items-center justify-center text-emerald-400 shadow-sm flex-shrink-0">
            <Zap className="w-4.5 h-4.5 fill-current text-lime-400" />
          </div>
          <div>
            <div className="flex items-baseline space-x-1.5">
              <span className="font-extrabold text-slate-900 text-base tracking-tight font-display">
                GRIDGUARD
              </span>
              <span className="text-xs font-bold text-teal-700 font-mono tracking-widest-sm">
                AI
              </span>
            </div>
            <div className="text-[10px] uppercase font-bold text-slate-400 tracking-widest-sm leading-none">
              Grid Operations
            </div>
          </div>
        </div>

        {/* Center: Desktop / Tablet Editorial Navigation */}
        <nav className="hidden md:flex items-center space-x-0.5 lg:space-x-1">
          {navItems.map((item) => {
            const isActive = activeScreen === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onScreenChange(item.id)}
                className={`relative px-3 lg:px-4 py-2 text-sm font-semibold transition-all cursor-pointer ${
                  isActive
                    ? 'text-[#073B3A]'
                    : 'text-slate-500 hover:text-slate-900'
                }`}
              >
                <span className="flex items-center space-x-1.5">
                  <span>{item.label}</span>
                  {item.hasWarning && (
                    <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse"></span>
                  )}
                </span>
                {isActive && (
                  <span className="absolute bottom-0 left-3 right-3 h-[2.5px] bg-[#073B3A] rounded-full"></span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Right: Operational Controls & Copilot (Desktop & Mobile) */}
        <div className="flex items-center space-x-2 sm:space-x-3">
          {/* Live Grid Indicator - Desktop full, Mobile compact */}
          {isMitigated ? (
            <div className="flex items-center space-x-1.5 px-2 sm:px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-600"></span>
              <span className="hidden sm:inline">Nominal (Mitigated)</span>
              <span className="sm:hidden font-bold">Safe</span>
            </div>
          ) : (
            <div className="flex items-center space-x-1.5 px-2 sm:px-2.5 py-1 rounded-full bg-red-50 border border-red-200 text-red-700 text-xs font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse"></span>
              <span className="hidden sm:inline">1 Overload Risk (F07)</span>
              <span className="sm:hidden font-bold">F07 Risk</span>
            </div>
          )}

          {/* Scenario Selector (Hidden on small mobile, accessible in drawer) */}
          <div className="hidden sm:flex items-center">
            <select
              value={activeScenarioId}
              onChange={(e) => onScenarioChange(e.target.value as ScenarioId)}
              className="bg-slate-50 text-slate-700 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-teal-700 cursor-pointer"
            >
              {MOCK_SCENARIOS.map((sc) => (
                <option key={sc.id} value={sc.id}>
                  {sc.name}
                </option>
              ))}
            </select>
          </div>

          {/* Ask GridGuard Drawer Trigger (Desktop) */}
          <button
            onClick={onOpenCopilot}
            className="hidden sm:flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 text-xs font-semibold hover:bg-slate-50 hover:border-slate-300 transition-colors cursor-pointer"
          >
            <HelpCircle className="w-3.5 h-3.5 text-teal-700" />
            <span>Ask GridGuard</span>
          </button>

          {/* Mobile Menu Button (< md) with touch target >= 44px */}
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="md:hidden w-11 h-11 flex items-center justify-center rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 cursor-pointer focus:outline-none"
            aria-label="Toggle Navigation Menu"
            aria-expanded={isMobileMenuOpen}
          >
            {isMobileMenuOpen ? (
              <X className="w-5 h-5 text-slate-800" />
            ) : (
              <Menu className="w-5 h-5 text-slate-800" />
            )}
          </button>
        </div>
      </div>

      {/* Mobile Drawer / Slide-Over Menu */}
      {isMobileMenuOpen && (
        <div className="md:hidden fixed inset-0 top-16 z-50 bg-slate-900/40 backdrop-blur-xs animate-in fade-in-50 duration-200">
          <div className="bg-white border-b border-slate-200 shadow-xl p-5 space-y-5 animate-in slide-in-from-top-2 duration-200 max-h-[calc(100vh-4rem)] overflow-y-auto">
            {/* Nav Items */}
            <div className="space-y-1">
              <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block mb-2 px-3">
                Navigation
              </span>
              {navItems.map((item) => {
                const isActive = activeScreen === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => handleNavClick(item.id)}
                    className={`w-full flex items-center justify-between px-3.5 py-3 rounded-xl text-sm font-bold transition-all cursor-pointer min-h-[44px] ${
                      isActive
                        ? 'bg-[#073B3A] text-white'
                        : 'text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <span className="flex items-center space-x-2">
                      <span>{item.label}</span>
                      {item.hasWarning && (
                        <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                      )}
                    </span>
                    <ArrowRight className={`w-4 h-4 ${isActive ? 'text-lime-300' : 'text-slate-400'}`} />
                  </button>
                );
              })}
            </div>

            {/* System Status & Scenario */}
            <div className="pt-4 border-t border-slate-100 space-y-3">
              <div>
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider block mb-1.5 px-1">
                  Grid Simulation Scenario
                </span>
                <select
                  value={activeScenarioId}
                  onChange={(e) => onScenarioChange(e.target.value as ScenarioId)}
                  className="w-full bg-slate-50 text-slate-800 border border-slate-200 rounded-xl px-3 py-2.5 text-xs font-semibold focus:outline-none min-h-[44px]"
                >
                  {MOCK_SCENARIOS.map((sc) => (
                    <option key={sc.id} value={sc.id}>
                      {sc.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Status Row */}
              <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-200/80 text-xs">
                <span className="font-semibold text-slate-600">System Telemetry</span>
                {isMitigated ? (
                  <span className="text-emerald-700 font-bold flex items-center space-x-1">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Nominal / Mitigated</span>
                  </span>
                ) : (
                  <span className="text-red-700 font-bold flex items-center space-x-1">
                    <AlertCircle className="w-3.5 h-3.5" />
                    <span>Feeder F07 Overload Risk</span>
                  </span>
                )}
              </div>

              {/* Ask GridGuard Mobile Trigger */}
              <button
                onClick={() => {
                  setIsMobileMenuOpen(false);
                  onOpenCopilot();
                }}
                className="w-full flex items-center justify-center space-x-2 px-4 py-3 rounded-xl bg-slate-100 hover:bg-slate-200 border border-slate-200 text-slate-800 text-xs font-bold transition-colors cursor-pointer min-h-[44px]"
              >
                <HelpCircle className="w-4 h-4 text-teal-800" />
                <span>Ask GridGuard Assistant</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};
