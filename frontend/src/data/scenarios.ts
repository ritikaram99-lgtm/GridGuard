import { GridScenario } from '../types';

export const MOCK_SCENARIOS: GridScenario[] = [
  {
    id: 'summer_peak',
    name: 'Summer Peak / EV Surge',
    tagline: 'Primary Hackathon Demo',
    description: 'High ambient heatwave (36°C) combined with concurrent commuter EV fleet charging. Feeder F07 predicted to hit 108 MW (+8 MW overload in 38 min).',
    ambientTempC: 36,
    evDemandPct: 145,
    solarAvailabilityPct: 40,
    primaryAlertFeederId: 'F07',
  },
  {
    id: 'solar_drop',
    name: 'Sudden Solar Cloud Cover',
    tagline: 'Renewable Drop Scenario',
    description: 'Rapid marine layer cloud cover drops distributed rooftop solar output by 70%, shifting residential load directly onto distribution feeders.',
    ambientTempC: 28,
    evDemandPct: 100,
    solarAvailabilityPct: 20,
    primaryAlertFeederId: 'F07',
  },
  {
    id: 'industrial_anomaly',
    name: 'Industrial Shift Spike',
    tagline: 'Harbor Grid Stress',
    description: 'Shipyard cold ironing and cold-storage refrigeration ramp simultaneously on Substation Charlie feeders.',
    ambientTempC: 24,
    evDemandPct: 90,
    solarAvailabilityPct: 80,
    primaryAlertFeederId: 'F09',
  },
  {
    id: 'baseline',
    name: 'Normal Baseline Grid',
    tagline: 'Optimal Operating State',
    description: 'Mild weather (22°C), normal EV depot schedule, high solar generation. All network feeders operate safely below 75% capacity.',
    ambientTempC: 22,
    evDemandPct: 100,
    solarAvailabilityPct: 85,
    primaryAlertFeederId: 'F07',
  },
];
