import React, { useState } from 'react';
import { X, HelpCircle, ChevronRight, FileText } from 'lucide-react';

interface CopilotDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  activeFeederId?: string;
}

export const CopilotDrawer: React.FC<CopilotDrawerProps> = ({
  isOpen,
  onClose,
  activeFeederId = 'F07',
}) => {
  const [selectedQuestion, setSelectedQuestion] = useState<number | null>(0);

  if (!isOpen) return null;

  const cannedQuestions = [
    {
      id: 0,
      title: `Why is Feeder ${activeFeederId} at risk?`,
      answer: `Feeder ${activeFeederId} is predicted to exceed its 100 MW thermal continuous rating in 38 minutes (reaching 108 MW between +45m and +60m). The primary driver is concurrent commercial EV fleet depot charging (+4.8 MW) combined with high ambient temperature air-conditioning demand (+3.6 MW), compounded by a 70% drop in rooftop solar offset (-1.5 MW).`,
    },
    {
      id: 1,
      title: 'Why this recommendation?',
      answer: `Dispatching EV depot smart charging rate throttling (5.0 MW) combined with Metro East BESS Battery Storage (9.0 MW) yields a total 14.0 MW peak load reduction. This achieves the 94.0 MW safety target (restoring 6% headroom under the 100 MW thermal limit) with zero customer outage disruption, avoiding costly industrial manufacturing interruption penalties.`,
    },
    {
      id: 2,
      title: 'Which feeder should I monitor first?',
      answer: `Feeder F07 requires immediate attention (Stress Score 91, Time-to-Overload: 38 min, projected peak 108 MW). Secondary monitoring should watch Feeder F03 (Silicon Expressway, Stress Score 74, TTO: 52 min) and Feeder F09 (Harbor Shipyards, Stress Score 68, TTO: 58 min).`,
    },
  ];

  return (
    <div className="fixed inset-0 z-[2000] flex justify-end bg-slate-900/30 backdrop-blur-xs transition-opacity">
      <div className="w-full sm:max-w-md bg-white border-l border-slate-200 h-full flex flex-col shadow-xl animate-in slide-in-from-right duration-200">
        {/* Clean Header */}
        <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div>
            <h3 className="font-bold text-sm text-slate-900 font-display">Operator Decision Assistant</h3>
            <p className="text-xs text-slate-500">Structured grid analytics and insights</p>
          </div>
          <button
            onClick={onClose}
            className="w-11 h-11 flex items-center justify-center rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-200/80 transition-colors cursor-pointer"
            aria-label="Close Assistant"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <div className="text-xs text-slate-500 font-medium">
            Select a query to review operational analysis:
          </div>

          {/* Preset Questions */}
          <div className="space-y-2">
            {cannedQuestions.map((q) => (
              <button
                key={q.id}
                onClick={() => setSelectedQuestion(q.id)}
                className={`w-full text-left p-3.5 rounded-xl border text-xs font-semibold transition-colors flex items-center justify-between min-h-[44px] cursor-pointer ${
                  selectedQuestion === q.id
                    ? 'bg-teal-50/70 border-teal-300 text-teal-950'
                    : 'bg-white border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <HelpCircle className={`w-4 h-4 flex-shrink-0 ${selectedQuestion === q.id ? 'text-teal-700' : 'text-slate-400'}`} />
                  <span>{q.title}</span>
                </div>
                <ChevronRight className={`w-4 h-4 flex-shrink-0 ${selectedQuestion === q.id ? 'text-teal-700' : 'text-slate-400'}`} />
              </button>
            ))}
          </div>

          {/* Structured Response Box */}
          {selectedQuestion !== null && (
            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 mt-4 space-y-2">
              <div className="flex items-center space-x-2 text-xs font-semibold text-slate-700">
                <FileText className="w-4 h-4 text-teal-700" />
                <span>Synthesis</span>
              </div>
              <p className="text-xs text-slate-700 leading-relaxed">
                {cannedQuestions[selectedQuestion].answer}
              </p>
            </div>
          )}
        </div>

        {/* Subtle Footer */}
        <div className="p-3 border-t border-slate-200 bg-slate-50 text-[11px] text-slate-400 text-center">
          GridGuard Operational Decision Support
        </div>
      </div>
    </div>
  );
};
