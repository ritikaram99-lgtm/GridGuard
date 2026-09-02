import { 
  Feeder, 
  ForecastPoint, 
  PreventionPlan, 
  ScenarioId, 
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

class GridService {
  /**
   * Fetch all network feeders from live FastAPI backend
   * GET /api/feeders and enriched via GET /api/feeders/{id}/intelligence
   */
  async getFeeders(_scenarioId: ScenarioId = 'summer_peak'): Promise<Feeder[]> {
    const rawFeeders = await apiFetch<BackendFeeder[]>('/api/feeders');
    
    // Enrich each feeder with real backend risk and forecast metrics
    const feeders = await Promise.all(
      rawFeeders.map(async (raw): Promise<Feeder> => {
        let score = raw.current_load > raw.capacity ? 80 : 10;
        let level: RiskLevel = raw.current_load > raw.capacity ? 'HIGH' : 'LOW';
        let timeToOverload: number | null = null;
        let peakForecast = raw.current_load;

        try {
          const intel = await apiFetch<BackendIntelligence>(`/api/feeders/${raw.id}/intelligence`);
          if (intel.risk) {
            score = intel.risk.score;
            level = intel.risk.level;
            timeToOverload = intel.risk.time_to_overload;
          }
          if (intel.forecast) {
            peakForecast = Math.max(
              raw.current_load,
              intel.forecast['15m'] || 0,
              intel.forecast['30m'] || 0,
              intel.forecast['45m'] || 0,
              intel.forecast['60m'] || 0
            );
          }
        } catch {
          // Fallback to basic risk evaluation if single feeder intelligence fails
          if (raw.current_load > raw.capacity) {
            level = 'HIGH';
            score = 80;
            timeToOverload = 30;
          }
        }

        const lat = raw.location?.latitude ?? 12.9716;
        const lon = raw.location?.longitude ?? 77.5946;

        return {
          id: raw.id,
          name: raw.name,
          substationId: raw.id === 'F07' ? 'SUB_ALPHA' : `SUB_${raw.id}`,
          substationName: raw.id === 'F07' ? 'Substation Alpha' : `Substation ${raw.id}`,
          currentLoadMw: raw.current_load,
          capacityMw: raw.capacity,
          stressScore: score,
          riskLevel: level,
          timeToOverloadMin: timeToOverload,
          peakForecastMw: peakForecast,
          voltageKv: Math.round((raw.voltage > 1 ? raw.voltage : raw.voltage * 11) * 100) / 100,
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
      const raw = await apiFetch<BackendFeeder>(`/api/feeders/${id}`);
      const intel = await apiFetch<BackendIntelligence>(`/api/feeders/${id}/intelligence`);

      const lat = raw.location?.latitude ?? 12.9716;
      const lon = raw.location?.longitude ?? 77.5946;

      const peakForecast = intel.forecast
        ? Math.max(
            raw.current_load,
            intel.forecast['15m'] || 0,
            intel.forecast['30m'] || 0,
            intel.forecast['45m'] || 0,
            intel.forecast['60m'] || 0
          )
        : raw.current_load;

      return {
        id: raw.id,
        name: raw.name,
        substationId: raw.id === 'F07' ? 'SUB_ALPHA' : `SUB_${raw.id}`,
        substationName: raw.id === 'F07' ? 'Substation Alpha' : `Substation ${raw.id}`,
        currentLoadMw: raw.current_load,
        capacityMw: raw.capacity,
        stressScore: intel.risk?.score ?? 10,
        riskLevel: intel.risk?.level ?? 'LOW',
        timeToOverloadMin: intel.risk?.time_to_overload ?? null,
        peakForecastMw: peakForecast,
        voltageKv: Math.round((raw.voltage > 1 ? raw.voltage : raw.voltage * 11) * 100) / 100,
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
   * Fetch 60-minute forecast horizon from live FastAPI backend
   * GET /api/forecast/{feeder_id}
   */
  async getForecast(feederId: string): Promise<ForecastPoint[]> {
    const rawForecast = await apiFetch<BackendForecast>(`/api/forecast/${feederId}`);
    
    // Retrieve feeder capacity and current load for proper context
    let currentLoad = 97;
    let capacity = 100;
    try {
      const feeder = await this.getFeederById(feederId);
      if (feeder) {
        currentLoad = feeder.currentLoadMw;
        capacity = feeder.capacityMw;
      }
    } catch {
      // Keep sensible default if individual fetch is slow
    }

    return [
      { timeStep: 'Current', actualLoadMw: currentLoad, forecastLoadMw: currentLoad, capacityLimitMw: capacity },
      { timeStep: '+15 min', actualLoadMw: null, forecastLoadMw: rawForecast['15m'], capacityLimitMw: capacity },
      { timeStep: '+30 min', actualLoadMw: null, forecastLoadMw: rawForecast['30m'], capacityLimitMw: capacity },
      { timeStep: '+45 min', actualLoadMw: null, forecastLoadMw: rawForecast['45m'], capacityLimitMw: capacity },
      { timeStep: '+60 min', actualLoadMw: null, forecastLoadMw: rawForecast['60m'], capacityLimitMw: capacity },
    ];
  }

  /**
   * Fetch SHAP / risk explainability contributors from live FastAPI backend
   * GET /api/risk/{feeder_id}
   */
  async getExplainability(feederId: string): Promise<{ contributors: ShapContributor[]; narrative: string }> {
    const riskData = await apiFetch<BackendRisk>(`/api/risk/${feederId}`);

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
        description: `${c.name} accounts for +${c.impact.toFixed(1)} MW of stress loading on circuit.`,
      };
    });

    const narrative = `Feeder ${feederId} is operating under ${riskData.level} risk (score: ${riskData.score}/100)${
      riskData.time_to_overload ? ` with predicted thermal overload in ${riskData.time_to_overload} minutes.` : '.'
    }`;

    return { contributors, narrative };
  }

  /**
   * Fetch automated recommendation and flexible resources from live FastAPI backend
   * POST /api/recommendations/{feeder_id}
   */
  async getPreventionPlan(feederId: string): Promise<PreventionPlan> {
    const rec = await apiFetch<BackendRecommendation>(`/api/recommendations/${feederId}`, {
      method: 'POST',
    });

    // Map backend action_details into frontend flexible resources
    const evDetail = rec.action_details?.find(a => a.action_type === 'EV_SHIFT');
    const battDetail = rec.action_details?.find(a => a.action_type === 'BATTERY');

    const evReduction = evDetail?.load_reduction ?? 7.0;
    const battReduction = battDetail?.load_reduction ?? 8.0;

    const resources: FlexibleResource[] = [
      {
        id: 'res_ev',
        type: 'EV',
        name: 'Smart EV Fleet Throttle (Level 2/3 Depot)',
        substationAssigned: `Substation Alpha - Feeder ${feederId}`,
        maxReductionMw: 10.0,
        selectedReductionMw: evReduction,
        isEnabled: true,
        estimatedCostDemo: evDetail?.cost ?? 14,
        disruptionLevel: 'Minimal',
        summary: 'Modulate commercial depot charging rates via OpenADR 2.0b signal.',
      },
      {
        id: 'res_battery',
        type: 'BATTERY',
        name: 'Metro East BESS Unit 2 (Substation Battery)',
        substationAssigned: `Substation Alpha - Feeder ${feederId}`,
        maxReductionMw: 10.0,
        selectedReductionMw: battReduction,
        isEnabled: true,
        estimatedCostDemo: battDetail?.cost ?? 24,
        disruptionLevel: 'None',
        summary: 'Dispatch localized Li-ion battery storage system directly onto Feeder bus.',
      },
      {
        id: 'res_industrial',
        type: 'INDUSTRIAL',
        name: 'Commercial HVAC & Industrial Demand Response',
        substationAssigned: `Substation Alpha - Feeder ${feederId}`,
        maxReductionMw: 5.0,
        selectedReductionMw: 0.0,
        isEnabled: false,
        estimatedCostDemo: 100,
        disruptionLevel: 'High',
        summary: 'Emergency standby curtailment of manufacturing chillers and compressors.',
      },
    ];

    const totalSelected = evReduction + battReduction;
    const totalCost = (evDetail?.cost ?? 14) + (battDetail?.cost ?? 24);

    // Retrieve real forecast to build trajectory comparison points
    let forecastPts: ForecastPoint[] = [];
    try {
      forecastPts = await this.getForecast(feederId);
    } catch {
      forecastPts = [
        { timeStep: 'Current', actualLoadMw: 97, forecastLoadMw: 97, capacityLimitMw: 100 },
        { timeStep: '+15 min', actualLoadMw: null, forecastLoadMw: 99, capacityLimitMw: 100 },
        { timeStep: '+30 min', actualLoadMw: null, forecastLoadMw: 103, capacityLimitMw: 100 },
        { timeStep: '+45 min', actualLoadMw: null, forecastLoadMw: 108, capacityLimitMw: 100 },
        { timeStep: '+60 min', actualLoadMw: null, forecastLoadMw: 110, capacityLimitMw: 100 },
      ];
    }

    const counterfactualPoints: ForecastPoint[] = forecastPts.map(pt => {
      let mitigatedVal = pt.forecastLoadMw;
      if (pt.timeStep !== 'Current') {
        mitigatedVal = Math.min(rec.predicted_after, Math.round((pt.forecastLoadMw - totalSelected) * 10) / 10);
      }
      return {
        ...pt,
        mitigatedLoadMw: mitigatedVal,
      };
    });

    return {
      feederId: rec.feeder_id,
      feederName: `Feeder ${rec.feeder_id} (Metro Depot & Commercial)`,
      currentLoadMw: 97,
      capacityMw: rec.capacity,
      predictedPeakMw: rec.predicted_load,
      minimumRequiredReductionMw: rec.required_reduction,
      targetSafetyReductionMw: rec.predicted_load - rec.predicted_after,
      targetSafetyLoadMw: rec.predicted_after,
      resources,
      totalSelectedReductionMw: totalSelected,
      totalEstimatedCostDemo: totalCost,
      isOverloadAvoided: rec.status === 'OVERLOAD_AVOIDED',
      expectedPeakAfterInterventionMw: rec.predicted_after,
      counterfactualPoints,
    };
  }

  /**
   * POST /api/simulate
   * Simulates flexible resource changes against FastAPI backend
   */
  async simulateIntervention(
    feederId: string, 
    changes: { ev_shift: number; battery: number; industrial: number }
  ): Promise<BackendSimulationResponse> {
    return apiFetch<BackendSimulationResponse>('/api/simulate', {
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
   * Recalculate forecast and risk in What-If Simulator (Isolated client sensitivity sandbox)
   */
  async simulateWhatIf(feederId: string, params: WhatIfParams): Promise<WhatIfRecalculationResult> {
    const capacityMw = 100;
    const baseCurrentLoad = 97;

    const tempDelta = (params.ambientTempC - 36) * 0.7;
    const evDelta = (params.evDemandPct - 145) * 0.08;
    const solarDelta = (40 - params.solarGenerationPct) * 0.06;

    const totalDelta = tempDelta + evDelta + solarDelta;

    const currentLoadMw = Math.round((baseCurrentLoad + totalDelta * 0.5) * 10) / 10;
    const peakForecastMw = Math.round((110 + totalDelta) * 10) / 10;

    let stressScore = Math.min(100, Math.max(10, Math.round(80 + totalDelta * 2.5)));
    let riskLevel: RiskLevel = 'LOW';
    let timeToOverloadMin: number | null = null;

    if (peakForecastMw > capacityMw) {
      const overloadAmount = peakForecastMw - capacityMw;
      stressScore = Math.min(100, Math.max(80, Math.round(80 + overloadAmount * 2)));
      riskLevel = stressScore >= 90 ? 'CRITICAL' : 'HIGH';
      timeToOverloadMin = Math.max(15, Math.round(30 - totalDelta * 1.5));
    } else if (peakForecastMw >= capacityMw * 0.85) {
      riskLevel = 'MODERATE';
      stressScore = Math.round(50 + (peakForecastMw - 85) * 2);
    } else {
      riskLevel = 'LOW';
      stressScore = Math.min(45, Math.max(15, Math.round(peakForecastMw * 0.4)));
    }

    const forecastPoints: ForecastPoint[] = [
      { timeStep: 'Current', actualLoadMw: currentLoadMw, forecastLoadMw: currentLoadMw, capacityLimitMw: capacityMw },
      { timeStep: '+15 min', actualLoadMw: null, forecastLoadMw: Math.round((currentLoadMw + (peakForecastMw - currentLoadMw) * 0.35) * 10) / 10, capacityLimitMw: capacityMw },
      { timeStep: '+30 min', actualLoadMw: null, forecastLoadMw: Math.round((currentLoadMw + (peakForecastMw - currentLoadMw) * 0.70) * 10) / 10, capacityLimitMw: capacityMw },
      { timeStep: '+45 min', actualLoadMw: null, forecastLoadMw: peakForecastMw, capacityLimitMw: capacityMw },
      { timeStep: '+60 min', actualLoadMw: null, forecastLoadMw: Math.round((peakForecastMw - 1.0) * 10) / 10, capacityLimitMw: capacityMw },
    ];

    const minimumRequiredReductionMw = Math.max(0, Math.round((peakForecastMw - capacityMw) * 10) / 10);
    const safetyMarginTargetMw = 95;
    const recommendedReductionMw = Math.max(0, Math.round((peakForecastMw - safetyMarginTargetMw) * 10) / 10);

    let recommendedCombination = 'No intervention required (Grid Safe)';
    if (recommendedReductionMw > 0) {
      if (recommendedReductionMw <= 7) {
        recommendedCombination = `EV Smart Charging (${recommendedReductionMw.toFixed(1)} MW)`;
      } else if (recommendedReductionMw <= 15) {
        recommendedCombination = `EV Throttling (7.0 MW) + BESS Unit (${(recommendedReductionMw - 7.0).toFixed(1)} MW)`;
      } else {
        recommendedCombination = `EV (7 MW) + BESS (8 MW) + Industrial DR (${(recommendedReductionMw - 15).toFixed(1)} MW)`;
      }
    }

    return {
      feederId,
      currentLoadMw,
      capacityMw,
      peakForecastMw,
      stressScore,
      riskLevel,
      timeToOverloadMin,
      forecastPoints,
      recommendedReductionMw,
      recommendedCombination,
      minimumRequiredReductionMw,
      safetyMarginTargetMw,
    };
  }
}

export const gridService = new GridService();
