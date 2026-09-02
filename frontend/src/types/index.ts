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
  minimumRequiredReductionMw: number; // 8 MW (108 - 100)
  targetSafetyReductionMw: number;   // ~14 MW (bringing to 94 MW for safety margin)
  targetSafetyLoadMw: number;        // ~94 MW
  resources: FlexibleResource[];
  totalSelectedReductionMw: number;
  totalEstimatedCostDemo: number;
  isOverloadAvoided: boolean;
  expectedPeakAfterInterventionMw: number;
  counterfactualPoints: ForecastPoint[];
}
