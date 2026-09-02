import { 
  Feeder, 
  ForecastPoint, 
  PreventionPlan, 
  ScenarioId, 
  ShapContributor, 
  WhatIfParams, 
  WhatIfRecalculationResult,
  RiskLevel
} from '../types';
import { MOCK_FEEDERS } from '../data/feeders';
import { F07_SHAP_CONTRIBUTORS, F07_EXPLAINABILITY_NARRATIVE } from '../data/shapMock';
import { 
  MOCK_F07_RESOURCES, 
  F07_WITHOUT_ACTION_FORECAST, 
  F07_WITH_GRIDGUARD_FORECAST 
} from '../data/resourcesMock';

class GridService {
  /**
   * Fetch all network feeders, adapted for current scenario
   */
  async getFeeders(scenarioId: ScenarioId = 'summer_peak'): Promise<Feeder[]> {
    if (scenarioId === 'baseline') {
      return MOCK_FEEDERS.map(f => {
        if (f.id === 'F07') {
          return {
            ...f,
            currentLoadMw: 62,
            capacityMw: 100,
            stressScore: 38,
            riskLevel: 'LOW',
            timeToOverloadMin: null,
            peakForecastMw: 68,
          };
        }
        return {
          ...f,
          currentLoadMw: Math.round(f.currentLoadMw * 0.75),
          stressScore: Math.round(f.stressScore * 0.6),
          riskLevel: 'LOW',
          timeToOverloadMin: null,
        };
      });
    }

    if (scenarioId === 'solar_drop') {
      return MOCK_FEEDERS.map(f => {
        if (f.id === 'F07') {
          return {
            ...f,
            currentLoadMw: 98,
            stressScore: 94,
            riskLevel: 'CRITICAL',
            timeToOverloadMin: 25,
            peakForecastMw: 111,
          };
        }
        if (f.id === 'F04' || f.id === 'F01') {
          return {
            ...f,
            currentLoadMw: Math.min(f.capacityMw, Math.round(f.currentLoadMw * 1.25)),
            stressScore: Math.min(90, f.stressScore + 25),
            riskLevel: 'HIGH',
          };
        }
        return f;
      });
    }

    if (scenarioId === 'industrial_anomaly') {
      return MOCK_FEEDERS.map(f => {
        if (f.id === 'F09') {
          return {
            ...f,
            currentLoadMw: 73,
            capacityMw: 75,
            stressScore: 92,
            riskLevel: 'CRITICAL',
            timeToOverloadMin: 30,
            peakForecastMw: 83,
          };
        }
        return f;
      });
    }

    // Default: summer_peak (F07 Critical)
    return [...MOCK_FEEDERS];
  }

  /**
   * Fetch a single feeder by ID
   */
  async getFeederById(id: string, scenarioId: ScenarioId = 'summer_peak'): Promise<Feeder | undefined> {
    const feeders = await this.getFeeders(scenarioId);
    return feeders.find(f => f.id === id);
  }

  /**
   * Fetch 60-minute forecast horizon for a specific feeder
   */
  async getForecast(feederId: string, scenarioId: ScenarioId = 'summer_peak'): Promise<ForecastPoint[]> {
    if (feederId === 'F07') {
      if (scenarioId === 'baseline') {
        return [
          { timeStep: 'Current', actualLoadMw: 62, forecastLoadMw: 62, capacityLimitMw: 100 },
          { timeStep: '+15 min', actualLoadMw: null, forecastLoadMw: 64, capacityLimitMw: 100 },
          { timeStep: '+30 min', actualLoadMw: null, forecastLoadMw: 67, capacityLimitMw: 100 },
          { timeStep: '+45 min', actualLoadMw: null, forecastLoadMw: 68, capacityLimitMw: 100 },
          { timeStep: '+60 min', actualLoadMw: null, forecastLoadMw: 66, capacityLimitMw: 100 },
        ];
      }
      return [...F07_WITHOUT_ACTION_FORECAST];
    }

    // Generic fallback for other feeders
    const base = feederId === 'F03' ? 78 : feederId === 'F09' ? 64 : 50;
    const cap = feederId === 'F03' ? 90 : feederId === 'F09' ? 75 : 80;
    return [
      { timeStep: 'Current', actualLoadMw: base, forecastLoadMw: base, capacityLimitMw: cap },
      { timeStep: '+15 min', actualLoadMw: null, forecastLoadMw: base + 3, capacityLimitMw: cap },
      { timeStep: '+30 min', actualLoadMw: null, forecastLoadMw: base + 6, capacityLimitMw: cap },
      { timeStep: '+45 min', actualLoadMw: null, forecastLoadMw: base + 8, capacityLimitMw: cap },
      { timeStep: '+60 min', actualLoadMw: null, forecastLoadMw: base + 7, capacityLimitMw: cap },
    ];
  }

  /**
   * Fetch SHAP / risk explainability contributors
   */
  async getExplainability(feederId: string): Promise<{ contributors: ShapContributor[]; narrative: string }> {
    if (feederId === 'F07') {
      return {
        contributors: F07_SHAP_CONTRIBUTORS,
        narrative: F07_EXPLAINABILITY_NARRATIVE,
      };
    }
    return {
      contributors: [
        {
          id: 'shap_base',
          featureName: 'System Baseline Load',
          impactMw: 2.5,
          category: 'Trajectory',
          description: 'Normal seasonal background energy consumption.',
        },
      ],
      narrative: `Feeder ${feederId} is operating within nominal safety parameters.`,
    };
  }

  /**
   * Fetch prevention resources and counterfactual comparison for F07
   */
  async getPreventionPlan(feederId: string): Promise<PreventionPlan> {
    const isF07 = feederId === 'F07';
    const currentLoadMw = isF07 ? 97 : 70;
    const capacityMw = isF07 ? 100 : 80;
    const predictedPeakMw = isF07 ? 108 : 75;

    // Minimum required reduction: to bring peak down to capacity (108 - 100 = 8 MW)
    const minimumRequiredReductionMw = Math.max(0, predictedPeakMw - capacityMw);
    // Target safety reduction: to bring peak to ~94 MW with safety margin
    const targetSafetyLoadMw = 94;
    const targetSafetyReductionMw = Math.max(0, predictedPeakMw - targetSafetyLoadMw);

    return {
      feederId,
      feederName: isF07 ? 'Feeder F07 (Metro Depot & Commercial)' : `Feeder ${feederId}`,
      currentLoadMw,
      capacityMw,
      predictedPeakMw,
      minimumRequiredReductionMw, // 8 MW
      targetSafetyReductionMw,    // 14 MW
      targetSafetyLoadMw,         // 94 MW
      resources: MOCK_F07_RESOURCES.map(r => ({ ...r })),
      totalSelectedReductionMw: 14.0, // EV 5MW + Battery 9MW
      totalEstimatedCostDemo: 400,    // $120 + $280
      isOverloadAvoided: true,
      expectedPeakAfterInterventionMw: 94,
      counterfactualPoints: [...F07_WITH_GRIDGUARD_FORECAST],
    };
  }

  /**
   * Recalculate forecast and risk in What-If Simulator
   * Pure service mock logic - no React calculation
   */
  async simulateWhatIf(feederId: string, params: WhatIfParams): Promise<WhatIfRecalculationResult> {
    const capacityMw = 100;
    const baseCurrentLoad = 97;

    // Deltas:
    // Temp: baseline 36°C. Delta = (temp - 36) * 0.7 MW
    const tempDelta = (params.ambientTempC - 36) * 0.7;
    // EV: baseline 145%. Delta = (ev% - 145) * 0.08 MW
    const evDelta = (params.evDemandPct - 145) * 0.08;
    // Solar: baseline 40%. Delta = (40 - solar%) * 0.06 MW (less solar = higher load)
    const solarDelta = (40 - params.solarGenerationPct) * 0.06;

    const totalDelta = tempDelta + evDelta + solarDelta;

    const currentLoadMw = Math.round((baseCurrentLoad + totalDelta * 0.5) * 10) / 10;
    const peakForecastMw = Math.round((108 + totalDelta) * 10) / 10;

    let stressScore = Math.min(100, Math.max(10, Math.round(91 + totalDelta * 2.5)));
    let riskLevel: RiskLevel = 'LOW';
    let timeToOverloadMin: number | null = null;

    if (peakForecastMw > capacityMw) {
      const overloadAmount = peakForecastMw - capacityMw;
      stressScore = Math.min(100, Math.max(85, Math.round(85 + overloadAmount * 2)));
      riskLevel = stressScore >= 90 ? 'CRITICAL' : 'HIGH';
      timeToOverloadMin = Math.max(15, Math.round(38 - totalDelta * 1.5));
    } else if (peakForecastMw >= capacityMw * 0.85) {
      riskLevel = 'MODERATE';
      stressScore = Math.round(50 + (peakForecastMw - 85) * 2);
    } else {
      riskLevel = 'LOW';
      stressScore = Math.min(45, Math.max(15, Math.round(peakForecastMw * 0.4)));
    }

    // Dynamic 5-point horizon
    const forecastPoints: ForecastPoint[] = [
      { timeStep: 'Current', actualLoadMw: currentLoadMw, forecastLoadMw: currentLoadMw, capacityLimitMw: capacityMw },
      { timeStep: '+15 min', actualLoadMw: null, forecastLoadMw: Math.round((currentLoadMw + (peakForecastMw - currentLoadMw) * 0.35) * 10) / 10, capacityLimitMw: capacityMw },
      { timeStep: '+30 min', actualLoadMw: null, forecastLoadMw: Math.round((currentLoadMw + (peakForecastMw - currentLoadMw) * 0.70) * 10) / 10, capacityLimitMw: capacityMw },
      { timeStep: '+45 min', actualLoadMw: null, forecastLoadMw: peakForecastMw, capacityLimitMw: capacityMw },
      { timeStep: '+60 min', actualLoadMw: null, forecastLoadMw: Math.round((peakForecastMw - 1.0) * 10) / 10, capacityLimitMw: capacityMw },
    ];

    const minimumRequiredReductionMw = Math.max(0, Math.round((peakForecastMw - capacityMw) * 10) / 10);
    const safetyMarginTargetMw = 94;
    const recommendedReductionMw = Math.max(0, Math.round((peakForecastMw - safetyMarginTargetMw) * 10) / 10);

    let recommendedCombination = 'No intervention required (Grid Safe)';
    if (recommendedReductionMw > 0) {
      if (recommendedReductionMw <= 5) {
        recommendedCombination = `EV Smart Charging (${recommendedReductionMw.toFixed(1)} MW)`;
      } else if (recommendedReductionMw <= 14) {
        recommendedCombination = `EV Throttling (5.0 MW) + BESS Unit (${(recommendedReductionMw - 5.0).toFixed(1)} MW)`;
      } else {
        recommendedCombination = `EV (6 MW) + BESS (9 MW) + Industrial DR (${(recommendedReductionMw - 15).toFixed(1)} MW)`;
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
