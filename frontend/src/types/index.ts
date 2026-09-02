export type RiskLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';

export interface Substation {
  id: string;
  name: string;
  voltage: string;
  lat: number;
  lng: number;
}

export interface Feeder {
  id: string; // e.g. 'F07'
  name: string;
  substationId: string;
  substationName: string;
  currentLoadMw: number;
  capacityMw: number;
  stressScore: number; // 0 - 100
  riskLevel: RiskLevel;
  timeToOverloadMin: number | null; // e.g. 38, or null if safe
  peakForecastMw: number;
  voltageKv: number;
  coordinates: [number, number][]; // Lat/Lng polyline
}

export interface ForecastPoint {
  timeStep: 'Current' | '+15 min' | '+30 min' | '+45 min' | '+60 min';
  actualLoadMw: number | null;
  forecastLoadMw: number;
  capacityLimitMw: number;
  mitigatedLoadMw?: number;
}

export interface ShapContributor {
  id: string;
  featureName: string;
  impactMw: number; // Positive increases risk, negative decreases risk
  category: 'EV' | 'Temperature' | 'Trajectory' | 'Solar' | 'Voltage';
  description: string;
}

export type ResourceType = 'EV' | 'BATTERY' | 'INDUSTRIAL';

export interface FlexibleResource {
  id: string;
  type: ResourceType;
  name: string;
  substationAssigned: string;
  maxReductionMw: number;
  selectedReductionMw: number;
  isEnabled: boolean;
  estimatedCostDemo: number; // NOTE: Explicit synthetic/demo value index
  disruptionLevel: 'None' | 'Minimal' | 'High';
  summary: string;
}

export type ScenarioId = 'summer_peak' | 'solar_drop' | 'industrial_anomaly' | 'baseline';

export interface GridScenario {
  id: ScenarioId;
  name: string;
  tagline: string;
  description: string;
  ambientTempC: number;
  evDemandPct: number;
  solarAvailabilityPct: number;
  primaryAlertFeederId: string;
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
  currentLoadMw: number;
  capacityMw: number;
  predictedPeakMw: number;
  minimumRequiredReductionMw: number;
  targetSafetyReductionMw: number;
  targetSafetyLoadMw: number;
  resources: FlexibleResource[];
  totalSelectedReductionMw: number;
  totalEstimatedCostDemo: number;
  isOverloadAvoided: boolean;
  expectedPeakAfterInterventionMw: number;
  counterfactualPoints: ForecastPoint[];
}

// Live FastAPI Backend Types
export interface BackendFeeder {
  id: string;
  name: string;
  capacity: number;
  current_load: number;
  voltage: number;
  location: {
    latitude: number;
    longitude: number;
    lat?: number | null;
    lon?: number | null;
  };
}

export interface BackendForecast {
  '15m': number;
  '30m': number;
  '45m': number;
  '60m': number;
  source?: string;
}

export interface BackendContributor {
  name: string;
  impact: number;
}

export interface BackendRisk {
  score: number;
  level: RiskLevel;
  time_to_overload: number | null;
  contributors?: BackendContributor[];
}

export interface BackendActionDetail {
  action_type: string;
  load_reduction: number;
  cost: number;
  disruption: number;
}

export interface BackendRecommendation {
  feeder_id: string;
  predicted_load: number;
  capacity: number;
  required_reduction: number;
  actions: string[];
  recommended_actions: string[];
  predicted_after: number;
  expected_load_after: number;
  status: string;
  action_details: BackendActionDetail[];
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

