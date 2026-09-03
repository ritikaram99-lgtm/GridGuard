export type RiskLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';

// Mirrors the backend's KNOWN_ML_FEEDER_IDS (ml_adapter_service.py): F01-F10
// are the authoritative ML feeder universe (synthetic feeders displayed as
// Delhi-area locations, real per-feeder ML forecast + Stress Engine -- see
// data/delhiFeederLabels.ts for the display-name/coordinate mapping). Any
// other id (e.g. legacy 'F12')
// is a non-ML feeder on an incomparable scale (e.g. F12's forecast is the
// raw NATIONAL demand, not a feeder-level allocation -- see forecast_service.py) --
// aggregate dashboard comparisons across feeders should use this to avoid
// mixing those two categories.
const ML_FEEDER_ID_PATTERN = /^F(0[1-9]|10)$/;
export function isMlFeeder(feederId: string): boolean {
  return ML_FEEDER_ID_PATTERN.test(feederId);
}

export interface Substation {
  id: string;
  name: string;
  voltage: string;
  lat: number;
  lng: number;
}

export interface Feeder {
  id: string; // e.g. 'F07' (one of the 10 ML feeders F01-F10, or legacy 'F12')
  name: string;
  substationId: string;
  substationName: string;
  currentLoadMw: number;
  capacityMw: number;
  stressScore: number; // 0 - 100
  riskLevel: RiskLevel;
  riskSource?: string | null; // 'ml_stress_engine' | 'legacy_formula'
  timeToOverloadMin: number | null; // converted from time_to_overload_hours; hour-resolution estimate
  timeToOverloadHours: number | null; // real ML Stress Engine resolution
  peakForecastMw: number;
  voltagePu: number; // backend voltage is per-unit (~0.85-1.05); no kV class is defined by the ML pipeline
  coordinates: [number, number][]; // Lat/Lng polyline
}

export interface ForecastPoint {
  timeStep: string; // e.g. 'Current', 'h+1'..'h+24', or a What-If preview label
  timestamp: string | null; // real ISO-ish timestamp when known (from hourly[]), else null
  actualLoadMw: number | null;
  forecastLoadMw: number | null; // nullable: ML feeders carry no sub-hourly points, only hourly[]
  capacityLimitMw: number;
  mitigatedLoadMw?: number | null;
}

export interface ForecastMeta {
  source?: string; // 'ml' | 'mock'
  scope?: string; // 'feeder' | 'national'
  forecastMethod?: string | null; // e.g. 'BIAS_CORRECTED_DIRECT_XGBOOST' | 'PREVIOUS_DAY_FALLBACK'
  regimeStatus?: string | null; // 'NORMAL' | 'SHIFT'
  regimeScore?: number | null;
  originTimestamp?: string | null;
}

export interface ForecastResult {
  points: ForecastPoint[];
  meta: ForecastMeta;
}

export interface ShapContributor {
  id: string;
  featureName: string;
  impactMw: number; // Positive increases risk, negative decreases risk
  category: 'EV' | 'Temperature' | 'Trajectory' | 'Solar' | 'Voltage';
  description: string;
}

export type ResourceType = 'EV' | 'BATTERY' | 'INDUSTRIAL' | 'OTHER';

export interface FlexibleResource {
  id: string;
  type: ResourceType;
  actionType: string; // raw backend action_type, e.g. 'EV', 'BATTERY', 'INDUSTRIAL'
  name: string; // generic label derived from action_type -- not a fabricated named asset
  feederLabel: string; // real feeder name/id this action applies to
  maxReductionMw: number;
  selectedReductionMw: number;
  durationHours?: number | null;
  isEnabled: boolean; // whether included in the (client-side) dispatch selection
  estimatedCostDemo: number; // real `cost` field from action_details -- itself a backend synthetic index, not frontend-fabricated
  disruptionLevel: 'None' | 'Minimal' | 'High';
  summary: string;
}

export type ScenarioId = 'live' | 'single_feeder_alert';

export interface GridScenario {
  id: ScenarioId;
  name: string;
  tagline: string;
  description: string;
  // Real ISO forecast-origin timestamp this scenario pins the whole app to,
  // or null for "live" (the backend's default/latest valid origin). See
  // data/scenarios.ts -- this is a real historical ML origin, not fabricated
  // data, selected because it naturally produces the described risk profile.
  origin: string | null;
}

export interface WhatIfParams {
  ambientTempC: number;
  evDemandPct: number;
  solarGenerationPct: number;
}

export interface WhatIfRecalculationResult {
  feederId: string;
  currentLoadMw: number;
  capacityMw: number;
  peakForecastMw: number;
  stressScore: number;
  riskLevel: RiskLevel;
  timeToOverloadMin: number | null;
  forecastPoints: ForecastPoint[];
  recommendedReductionMw: number;
  recommendedCombination: string;
  minimumRequiredReductionMw: number;
  safetyMarginTargetMw: number;
}

export interface FeederIntelligenceData {
  feeder: Feeder;
  forecast: ForecastPoint[];
  shapContributors: ShapContributor[];
  aiExecutiveSummary: string;
}

export interface PreventionPlan {
  feederId: string;
  feederName: string;
  originTimestamp?: string | null;
  currentLoadMw: number;
  capacityMw: number;
  predictedPeakMw: number; // backend predicted_load
  requiredReductionMw: number; // backend required_reduction
  predictedAfterMw: number; // backend predicted_after (all recommended actions applied)
  status: string; // 'NO_ACTION_REQUIRED' | 'PREVENTED' | 'REDUCED_NOT_PREVENTED' | 'INSUFFICIENT_FLEXIBILITY' | 'DURATION_LIMITED' | legacy
  baselineRiskLevel?: string | null;
  projectedRiskLevel?: string | null;
  baselineStressScore?: number | null;
  projectedStressScore?: number | null;
  overloadAvoided?: boolean | null;
  actionRequired?: boolean | null;
  interventionCost?: number | null;
  reason?: string | null;
  candidatesEvaluated?: number | null;
  source?: string | null;
  alternatives?: Array<{
    label: string;
    cost: number;
    total_reduction_mw: number;
    projected_risk: string;
    overload_after: boolean;
    resolved: boolean;
  }> | null;
  resources: FlexibleResource[]; // from action_details[]; empty if backend recommends none
  forecastPoints: ForecastPoint[]; // real forecast trajectory (getForecast), for chart baseline
}

// Live FastAPI Backend Types
export interface BackendFeeder {
  id: string;
  name: string;
  capacity: number;
  current_load: number;
  voltage: number; // per-unit, not kV
  location: {
    latitude: number;
    longitude: number;
    lat?: number | null;
    lon?: number | null;
  };
}

export interface BackendHourlyForecastPoint {
  horizon: number; // 1-24
  timestamp: string;
  load_mw: number;
}

export interface BackendForecast {
  // Legacy 15/30/45/60-minute fields. Non-null only for source='mock' (legacy
  // feeder ids); always null for the real ML feeders (F01-F10, source='ml').
  '15m': number | null;
  '30m': number | null;
  '45m': number | null;
  '60m': number | null;
  source?: string; // 'ml' | 'mock'
  hourly?: BackendHourlyForecastPoint[] | null; // genuine 24-point hourly forecast, source='ml' only
  origin_timestamp?: string | null;
  forecast_method?: string | null; // 'BIAS_CORRECTED_DIRECT_XGBOOST' | 'PREVIOUS_DAY_FALLBACK'
  regime_status?: string | null; // 'NORMAL' | 'SHIFT'
  regime_score?: number | null;
  scope?: string | null; // 'feeder' | 'national'
}

export interface BackendContributor {
  name: string;
  impact: number;
}

export interface BackendRisk {
  score: number;
  level: RiskLevel;
  time_to_overload: number | null; // minutes; hour-resolution estimate for ML feeders
  time_to_overload_hours?: number | null; // real ML Stress Engine resolution
  source?: string | null; // 'ml_stress_engine' | 'legacy_formula'
  contributors?: BackendContributor[];
}

export interface BackendActionDetail {
  action_type: string;
  load_reduction: number;
  duration_hours?: number | null;
  cost: number;
  disruption: number;
}

export interface BackendRecommendation {
  feeder_id: string;
  origin_timestamp?: string | null;
  predicted_load: number;
  capacity: number;
  required_reduction: number;
  actions: string[];
  recommended_actions: string[];
  predicted_after: number;
  expected_load_after: number;
  status: string;
  action_details: BackendActionDetail[];
  baseline_risk_level?: string | null;
  projected_risk_level?: string | null;
  overload_avoided?: boolean | null;
  action_required?: boolean | null;
  intervention_cost?: number | null;
  reason?: string | null;
  source?: string | null;
  alternatives?: any[] | null;
}

export interface BackendIntelligence {
  feeder_id: string;
  current: {
    load: number;
    capacity: number;
    voltage: number;
  };
  location: {
    latitude: number;
    longitude: number;
    lat: number;
    lon: number;
  };
  forecast: BackendForecast;
  risk: BackendRisk;
  contributors: BackendContributor[];
  recommendation: BackendRecommendation;
}

export interface BackendSimulationResponse {
  feeder_id: string;
  origin_timestamp?: string | null;
  forecast_peak: number;
  capacity: number;
  changes: {
    ev_shift: number;
    battery: number;
    industrial: number;
    temperature?: number;
    ev_demand_percent?: number;
    solar_percent?: number;
  };
  total_reduction: number;
  simulated_load: number;
  status: string;
  scenario_peak_load_mw?: number | null;
  baseline_risk?: string | null;
  baseline_stress_score?: number | null;
  scenario_risk?: string | null;
  scenario_stress_score?: number | null;
  final_risk?: string | null;
  final_stress_score?: number | null;
  overload_before?: boolean | null;
  overload_after_scenario?: boolean | null;
  overload_after?: boolean | null;
  overload_avoided?: boolean | null;
  load_change_mw?: Record<string, number> | null;
  actions_applied?: any[] | null;
  source?: string | null;
  without_action_forecast?: any;
  with_action_forecast?: any;
  risk?: any;
  recommendation?: any;
  final_status: string;
}

export interface BackendDispatchResponse {
  feeder_id: string;
  status: string;
  forecast_peak: number;
  capacity: number;
  total_reduction: number;
  simulated_load: number;
  overload_avoided: boolean;
  actions: Array<{
    action_type: string;
    reduction_mw: number;
    status: string;
  }>;
}

export interface BackendCopilotResponse {
  feeder_id: string;
  summary: string;
  risk_explanation: string;
  recommended_action_explanation: string;
  expected_outcome: string;
  operator_message: string;
  source: string;
}

