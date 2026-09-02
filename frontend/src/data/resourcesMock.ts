import { FlexibleResource, ForecastPoint } from '../types';

export const MOCK_F07_RESOURCES: FlexibleResource[] = [
  {
    id: 'res_ev',
    type: 'EV',
    name: 'Smart EV Fleet Throttle (Level 2/3 Depot)',
    substationAssigned: 'Substation Alpha - Feeder F07',
    maxReductionMw: 6.0,
    selectedReductionMw: 5.0,
    isEnabled: true,
    estimatedCostDemo: 120, // Explicit synthetic/demo index value
    disruptionLevel: 'Minimal',
    summary: 'Modulate commercial depot charging rates from 150 kW to 90 kW via OpenADR 2.0b signal.',
  },
  {
    id: 'res_battery',
    type: 'BATTERY',
    name: 'Metro East BESS Unit 2 (Substation Battery)',
    substationAssigned: 'Substation Alpha - Feeder F07',
    maxReductionMw: 9.0,
    selectedReductionMw: 9.0,
    isEnabled: true,
    estimatedCostDemo: 280, // Explicit synthetic/demo index value
    disruptionLevel: 'None',
    summary: 'Dispatch localized 4-hour Li-ion battery storage system directly onto Feeder F07 bus.',
  },
  {
    id: 'res_industrial',
    type: 'INDUSTRIAL',
    name: 'Commercial HVAC & Industrial Demand Response',
    substationAssigned: 'Substation Alpha - Feeder F07',
    maxReductionMw: 10.0,
    selectedReductionMw: 0.0,
    isEnabled: false,
    estimatedCostDemo: 1200, // Explicit synthetic/demo index value (high penalty/curtailment rate)
    disruptionLevel: 'High',
    summary: 'Emergency curtailment of manufacturing refrigeration and office building chillers.',
  },
];

// Without Action: 97 -> 101 -> 105 -> 108 -> 107 MW
export const F07_WITHOUT_ACTION_FORECAST: ForecastPoint[] = [
  { timeStep: 'Current', actualLoadMw: 97, forecastLoadMw: 97, capacityLimitMw: 100 },
  { timeStep: '+15 min', actualLoadMw: null, forecastLoadMw: 101, capacityLimitMw: 100 },
  { timeStep: '+30 min', actualLoadMw: null, forecastLoadMw: 105, capacityLimitMw: 100 },
  { timeStep: '+45 min', actualLoadMw: null, forecastLoadMw: 108, capacityLimitMw: 100 },
  { timeStep: '+60 min', actualLoadMw: null, forecastLoadMw: 107, capacityLimitMw: 100 },
];

// With GridGuard: 97 -> 96 -> 95 -> 94 -> 93 MW (14 MW mitigated via EV 5MW + Battery 9MW)
export const F07_WITH_GRIDGUARD_FORECAST: ForecastPoint[] = [
  { timeStep: 'Current', actualLoadMw: 97, forecastLoadMw: 97, capacityLimitMw: 100, mitigatedLoadMw: 97 },
  { timeStep: '+15 min', actualLoadMw: null, forecastLoadMw: 101, capacityLimitMw: 100, mitigatedLoadMw: 96 },
  { timeStep: '+30 min', actualLoadMw: null, forecastLoadMw: 105, capacityLimitMw: 100, mitigatedLoadMw: 95 },
  { timeStep: '+45 min', actualLoadMw: null, forecastLoadMw: 108, capacityLimitMw: 100, mitigatedLoadMw: 94 },
  { timeStep: '+60 min', actualLoadMw: null, forecastLoadMw: 107, capacityLimitMw: 100, mitigatedLoadMw: 93 },
];
