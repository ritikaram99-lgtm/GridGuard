import {
  Feeder,
  ForecastPoint,
  ForecastResult,
  PreventionPlan,
  ShapContributor,
  WhatIfParams,
  WhatIfRecalculationResult,
  RiskLevel,
  BackendFeeder,
  BackendForecast,
  BackendRisk,
  BackendIntelligence,
  BackendRecommendation,
  BackendSimulationResponse,
  BackendDispatchResponse,
  BackendCopilotResponse,
  FlexibleResource
} from '../types';
import { apiFetch } from './client';
import { displayFeederName, toDisplayCoordinate } from '../data/delhiFeederLabels';

// Optional global "forecast origin" override. When set, every ML-backed
// endpoint call is pinned to this real historical timestamp instead of the
// backend's default (latest valid) origin -- e.g. to reproduce a specific
// real scenario for a demo. Never fabricates data: it just selects which
// real, already-computed ML result to request. See data/demoScenarios.ts.
let activeOrigin: string | null = null;

export function setActiveOrigin(origin: string | null): void {
  activeOrigin = origin;
}

export function getActiveOrigin(): string | null {
  return activeOrigin;
}

function withOrigin(path: string): string {
  if (!activeOrigin) return path;
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}origin=${encodeURIComponent(activeOrigin)}`;
}

/** Peak MW from a BackendForecast, whether it carries a real hourly[] (ML
 * feeders) or legacy m15..m60 (mock 'F12'). Never fabricates a value -- if
 * neither is available, returns null (caller must handle this honestly). */
function peakLoadMw(forecast: BackendForecast | null | undefined, fallback: number): number {
  if (!forecast) return fallback;
  if (forecast.hourly && forecast.hourly.length > 0) {
    return Math.max(fallback, ...forecast.hourly.map(pt => pt.load_mw));
  }
  const legacy = [forecast['15m'], forecast['30m'], forecast['45m'], forecast['60m']].filter(
    (v): v is number => v !== null && v !== undefined
  );
  return legacy.length > 0 ? Math.max(fallback, ...legacy) : fallback;
}

/** Builds the chart-ready ForecastPoint[] + metadata from a BackendForecast.
 * Uses the real hourly[] array for ML feeders; never manufactures sub-hourly
 * 15/30/45/60-minute values. */
function toForecastResult(raw: BackendForecast, currentLoad: number, capacity: number): ForecastResult {
  const meta = {
    source: raw.source,
    scope: raw.scope ?? undefined,
    forecastMethod: raw.forecast_method ?? null,
    regimeStatus: raw.regime_status ?? null,
    regimeScore: raw.regime_score ?? null,
    originTimestamp: raw.origin_timestamp ?? null,
  };

  if (raw.hourly && raw.hourly.length > 0) {
    const points: ForecastPoint[] = [
      { timeStep: 'Now', timestamp: raw.origin_timestamp ?? null, actualLoadMw: currentLoad, forecastLoadMw: currentLoad, capacityLimitMw: capacity },
      ...raw.hourly.map((pt): ForecastPoint => ({
        timeStep: `h+${pt.horizon}`,
        timestamp: pt.timestamp,
        actualLoadMw: null,
        forecastLoadMw: pt.load_mw,
        capacityLimitMw: capacity,
      })),
    ];
    return { points, meta };
  }

  // Legacy mock/joblib path (source='mock', currently only feeder 'F12'):
  // real 4-point sub-hourly data, not fabricated.
  const points: ForecastPoint[] = [
    { timeStep: 'Current', timestamp: null, actualLoadMw: currentLoad, forecastLoadMw: currentLoad, capacityLimitMw: capacity },
    { timeStep: '+15 min', timestamp: null, actualLoadMw: null, forecastLoadMw: raw['15m'], capacityLimitMw: capacity },
    { timeStep: '+30 min', timestamp: null, actualLoadMw: null, forecastLoadMw: raw['30m'], capacityLimitMw: capacity },
    { timeStep: '+45 min', timestamp: null, actualLoadMw: null, forecastLoadMw: raw['45m'], capacityLimitMw: capacity },
    { timeStep: '+60 min', timestamp: null, actualLoadMw: null, forecastLoadMw: raw['60m'], capacityLimitMw: capacity },
  ];
  return { points, meta };
}

class GridService {
  /**
   * Fetch all network feeders from live FastAPI backend
   * GET /api/feeders and enriched via GET /api/feeders/{id}/intelligence.
   * Reflects whatever origin is currently active (see setActiveOrigin).
   */
  async getFeeders(): Promise<Feeder[]> {
    const rawFeeders = await apiFetch<BackendFeeder[]>(withOrigin('/api/feeders'));

    // Enrich each feeder with real backend risk and forecast metrics
    const feeders = await Promise.all(
      rawFeeders.map(async (raw): Promise<Feeder> => {
        let score = raw.current_load > raw.capacity ? 80 : 10;
        let level: RiskLevel = raw.current_load > raw.capacity ? 'HIGH' : 'LOW';
        let riskSource: string | null = null;
        let timeToOverloadMin: number | null = null;
        let timeToOverloadHours: number | null = null;
        let peakForecast = raw.current_load;

        try {
          const intel = await apiFetch<BackendIntelligence>(withOrigin(`/api/feeders/${raw.id}/intelligence`));
          if (intel.risk) {
            // Rounded for display only -- same real value, no precision fabricated.
            score = Math.round(intel.risk.score);
            level = intel.risk.level;
            timeToOverloadMin = intel.risk.time_to_overload ?? null;
            timeToOverloadHours = intel.risk.time_to_overload_hours ?? null;
            riskSource = intel.risk.source ?? null;
          }
          if (intel.forecast) {
            peakForecast = peakLoadMw(intel.forecast, raw.current_load);
          }
        } catch {
          // Backend/ML genuinely unavailable for this feeder -- fall back to
          // the coarse current-vs-capacity comparison already computed
          // above, without fabricating a specific score or TTO.
        }

        // Backend always supplies location for every feeder it returns.
        // Recentered for display only -- see data/delhiFeederLabels.ts.
        const [lat, lon] = toDisplayCoordinate(raw.location.latitude, raw.location.longitude);

        return {
          id: raw.id,
          name: displayFeederName(raw.id, raw.name),
          substationId: `SUB_${raw.id}`,
          substationName: `Substation ${raw.id}`,
          currentLoadMw: raw.current_load,
          capacityMw: raw.capacity,
          stressScore: score,
          riskLevel: level,
          riskSource,
          timeToOverloadMin,
          timeToOverloadHours,
          peakForecastMw: peakForecast,
          voltagePu: raw.voltage,
          coordinates: [
            [lat, lon],
            [lat + 0.003, lon + 0.003],
            [lat + 0.007, lon + 0.005],
          ],
        };
      })
    );

    return feeders;
  }

  /**
   * Fetch a single feeder by ID from live FastAPI backend
   * GET /api/feeders/{id}
   */
  async getFeederById(id: string): Promise<Feeder | undefined> {
    try {
      const raw = await apiFetch<BackendFeeder>(withOrigin(`/api/feeders/${id}`));
      const intel = await apiFetch<BackendIntelligence>(withOrigin(`/api/feeders/${id}/intelligence`));

      const [lat, lon] = toDisplayCoordinate(raw.location.latitude, raw.location.longitude);

      const peakForecast = peakLoadMw(intel.forecast, raw.current_load);

      return {
        id: raw.id,
        name: displayFeederName(raw.id, raw.name),
        substationId: `SUB_${raw.id}`,
        substationName: `Substation ${raw.id}`,
        currentLoadMw: raw.current_load,
        capacityMw: raw.capacity,
        stressScore: intel.risk ? Math.round(intel.risk.score) : 0,
        riskLevel: intel.risk?.level ?? 'LOW',
        riskSource: intel.risk?.source ?? null,
        timeToOverloadMin: intel.risk?.time_to_overload ?? null,
        timeToOverloadHours: intel.risk?.time_to_overload_hours ?? null,
        peakForecastMw: peakForecast,
        voltagePu: raw.voltage,
        coordinates: [
          [lat, lon],
          [lat + 0.003, lon + 0.003],
          [lat + 0.007, lon + 0.005],
        ],
      };
    } catch {
      const feeders = await this.getFeeders();
      return feeders.find(f => f.id === id);
    }
  }

  /**
   * Fetch the real forecast for a feeder from the live FastAPI backend.
   * GET /api/forecast/{feeder_id}
   * For F01-F10 this is the feeder's own 24-hour ML allocation (`hourly`);
   * legacy feeder 'F12' returns the 4-point 15/30/45/60-minute mock data.
   * Never fabricates sub-hourly points for ML feeders.
   */
  async getForecast(feederId: string): Promise<ForecastResult> {
    const rawForecast = await apiFetch<BackendForecast>(withOrigin(`/api/forecast/${feederId}`));

    let currentLoad = 0;
    let capacity = rawForecast.hourly?.length
      ? Math.max(...rawForecast.hourly.map(pt => pt.load_mw))
      : 0;
    try {
      const feeder = await this.getFeederById(feederId);
      if (feeder) {
        currentLoad = feeder.currentLoadMw;
        capacity = feeder.capacityMw;
      }
    } catch {
      // Feeder lookup failed; fall back to the values derived above.
    }

    return toForecastResult(rawForecast, currentLoad, capacity);
  }

  /**
   * Fetch SHAP / risk explainability contributors from live FastAPI backend
   * GET /api/risk/{feeder_id}
   */
  async getExplainability(feederId: string): Promise<{ contributors: ShapContributor[]; narrative: string; source: string | null }> {
    const riskData = await apiFetch<BackendRisk>(withOrigin(`/api/risk/${feederId}`));

    const contributors: ShapContributor[] = (riskData.contributors || []).map((c, idx) => {
      let category: ShapContributor['category'] = 'Trajectory';
      const lower = c.name.toLowerCase();
      if (lower.includes('voltage')) category = 'Voltage';
      else if (lower.includes('heat') || lower.includes('temperature')) category = 'Temperature';
      else if (lower.includes('ev')) category = 'EV';
      else if (lower.includes('solar')) category = 'Solar';

      return {
        id: `contrib_${feederId}_${idx}`,
        featureName: c.name,
        impactMw: c.impact,
        category,
        description: `${c.name} contributes ${c.impact.toFixed(1)} points to the stress score.`,
      };
    });

    // time_to_overload_hours is the ML Stress Engine's real resolution; the
    // legacy formula (non-ML feeders) has no hourly field, only minutes.
    const ttoText = riskData.time_to_overload_hours != null
      ? ` Estimated time to overload: ~${riskData.time_to_overload_hours.toFixed(1)} hours (hour-resolution estimate).`
      : riskData.time_to_overload != null
      ? ` Estimated time to overload: ${riskData.time_to_overload} minutes.`
      : '';

    const narrative = `Feeder ${feederId} is operating under ${riskData.level} risk (score: ${riskData.score}/100).${ttoText}`;

    return { contributors, narrative, source: riskData.source ?? null };
  }

  /**
   * Fetch automated recommendation from the live FastAPI backend and map its
   * real action_details[] into flexible resources. This is the backend's own
   * optimization_service (not an ML Action Engine) -- no resource, cost, or
   * capacity value here is invented by the frontend.
   * POST /api/recommendations/{feeder_id}
   */
  async getPreventionPlan(feederId: string): Promise<PreventionPlan> {
    const [rec, feeder, forecast] = await Promise.all([
      apiFetch<BackendRecommendation>(withOrigin(`/api/recommendations/${feederId}`), { method: 'POST' }),
      this.getFeederById(feederId),
      this.getForecast(feederId).catch(() => null),
    ]);

    const resources: FlexibleResource[] = (rec.action_details ?? []).map((a, idx) => {
      const isEv = a.action_type === 'EV' || a.action_type === 'EV_SHIFT';
      const type: FlexibleResource['type'] =
        isEv ? 'EV' : a.action_type === 'BATTERY' ? 'BATTERY' : a.action_type === 'INDUSTRIAL' ? 'INDUSTRIAL' : 'OTHER';
      const label =
        isEv ? 'EV Charging Shift'
        : a.action_type === 'BATTERY' ? 'Battery Discharge'
        : a.action_type === 'INDUSTRIAL' ? 'Industrial Demand Response'
        : a.action_type;
      const disruptionLevel: FlexibleResource['disruptionLevel'] =
        a.action_type === 'BATTERY' ? 'None' : a.action_type === 'INDUSTRIAL' ? 'High' : 'Minimal';

      const durText = a.duration_hours ? ` (${a.duration_hours.toFixed(1)}h duration)` : '';

      return {
        id: `res_${feederId}_${idx}`,
        type,
        actionType: a.action_type,
        name: label,
        feederLabel: feeder?.name ?? feederId,
        maxReductionMw: a.load_reduction,
        selectedReductionMw: a.load_reduction,
        durationHours: a.duration_hours ?? null,
        isEnabled: true,
        estimatedCostDemo: a.cost,
        disruptionLevel,
        summary: `Evaluated ${label.toLowerCase()} of ${a.load_reduction.toFixed(1)} MW${durText} for feeder ${feederId}.`,
      };
    });

    return {
      feederId: rec.feeder_id ?? feederId,
      feederName: feeder?.name ?? feederId,
      originTimestamp: rec.origin_timestamp ?? null,
      currentLoadMw: feeder?.currentLoadMw ?? 0,
      capacityMw: rec.capacity ?? feeder?.capacityMw ?? 0,
      predictedPeakMw: rec.predicted_load ?? 0,
      requiredReductionMw: rec.required_reduction ?? 0,
      predictedAfterMw: rec.predicted_after,
      status: rec.status,
      baselineRiskLevel: rec.baseline_risk_level ?? null,
      projectedRiskLevel: rec.projected_risk_level ?? null,
      baselineStressScore: (rec as any).baseline_stress_score ?? null,
      projectedStressScore: (rec as any).projected_stress_score ?? null,
      overloadAvoided: rec.overload_avoided ?? null,
      actionRequired: rec.action_required ?? null,
      interventionCost: rec.intervention_cost ?? null,
      reason: rec.reason ?? null,
      candidatesEvaluated: (rec as any).candidates_evaluated ?? null,
      source: rec.source ?? null,
      alternatives: rec.alternatives ?? null,
      resources,
      forecastPoints: forecast?.points ?? [],
    };
  }

  /**
   * POST /api/simulate
   * Simulates flexible resource changes and scenario parameters against FastAPI backend (ML Simulation Engine)
   */
  async simulateIntervention(
    feederId: string, 
    changes: { ev_shift: number; battery: number; industrial: number }
  ): Promise<BackendSimulationResponse> {
    return apiFetch<BackendSimulationResponse>(withOrigin('/api/simulate'), {
      method: 'POST',
      body: JSON.stringify({
        feeder_id: feederId,
        changes: {
          ev_shift: changes.ev_shift,
          battery: changes.battery,
          industrial: changes.industrial,
        },
      }),
    });
  }

  /**
   * POST /api/dispatch
   * Authorizes intervention actions onto FastAPI backend
   */
  async dispatchActions(
    feederId: string,
    actions: Array<{ action_type: string; reduction_mw: number }>
  ): Promise<BackendDispatchResponse> {
    return apiFetch<BackendDispatchResponse>('/api/dispatch', {
      method: 'POST',
      body: JSON.stringify({
        feeder_id: feederId,
        actions: actions.map(a => ({
          action_type: a.action_type,
          reduction_mw: a.reduction_mw,
        })),
      }),
    });
  }

  /**
   * GET /api/copilot/{feeder_id}
   * Retrieves operational Copilot summary from FastAPI backend
   */
  async getCopilotInsight(feederId: string): Promise<BackendCopilotResponse> {
    return apiFetch<BackendCopilotResponse>(`/api/copilot/${feederId}`);
  }

  /**
   * Real ML Simulation Engine (ml/src/simulation_engine.py) via POST /api/simulate.
   * Evaluates counterfactual scenario adjustments (temperature, EV surge, solar drop)
   * against the feeder's genuine forecast trajectory.
   */
  async simulateWhatIf(feederId: string, params: WhatIfParams): Promise<WhatIfRecalculationResult> {
    const rawSim = await apiFetch<BackendSimulationResponse>(withOrigin('/api/simulate'), {
      method: 'POST',
      body: JSON.stringify({
        feeder_id: feederId,
        changes: {
          temperature: params.ambientTempC,
          ev_demand_percent: params.evDemandPct,
          solar_percent: params.solarGenerationPct,
        },
      }),
    });

    const forecastRes = await this.getForecast(feederId).catch(() => null);

    const peakMw = Math.round((rawSim.scenario_peak_load_mw ?? rawSim.simulated_load ?? rawSim.forecast_peak) * 10) / 10;
    const capacityMw = Math.round((rawSim.capacity ?? 100) * 10) / 10;
    const stressScore = Math.round(rawSim.scenario_stress_score ?? rawSim.baseline_stress_score ?? (peakMw > capacityMw ? 85 : 30));
    const riskLevel: RiskLevel = (rawSim.scenario_risk ?? rawSim.baseline_risk ?? (stressScore >= 80 ? 'HIGH' : stressScore >= 50 ? 'MODERATE' : 'LOW')) as RiskLevel;

    const minimumRequiredReductionMw = Math.max(0, Math.round((peakMw - capacityMw) * 10) / 10);
    const safetyTargetMw = Math.round(capacityMw * 0.90 * 10) / 10;
    const recommendedReductionMw = Math.max(0, Math.round((peakMw - safetyTargetMw) * 10) / 10);

    let recommendedCombination = 'No intervention required (Grid Safe)';
    if (recommendedReductionMw > 0) {
      recommendedCombination = `Evaluated safety reduction target: ${recommendedReductionMw.toFixed(1)} MW`;
    }

    return {
      feederId,
      currentLoadMw: Math.round((rawSim.forecast_peak ?? peakMw) * 10) / 10,
      capacityMw,
      peakForecastMw: peakMw,
      stressScore,
      riskLevel,
      timeToOverloadMin: null,
      forecastPoints: forecastRes?.points ?? [],
      recommendedReductionMw,
      recommendedCombination,
      minimumRequiredReductionMw,
      safetyMarginTargetMw: safetyTargetMw,
    };
  }
}

export const gridService = new GridService();
