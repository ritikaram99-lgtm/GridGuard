import { ShapContributor } from '../types';

export const F07_SHAP_CONTRIBUTORS: ShapContributor[] = [
  {
    id: 'shap_ev',
    featureName: 'EV Fleet Depot Surge',
    impactMw: 4.8,
    category: 'EV',
    description: 'Concurrent fast charging cluster (+145% normal volume) connecting at Transit East Terminal.',
  },
  {
    id: 'shap_temp',
    featureName: 'Ambient Heatwave (HVAC Cooling)',
    impactMw: 3.6,
    category: 'Temperature',
    description: 'Current ambient 36°C driving continuous compressor cycling across commercial office districts.',
  },
  {
    id: 'shap_traj',
    featureName: 'Prior 2-Hour Load Trajectory',
    impactMw: 2.1,
    category: 'Trajectory',
    description: 'Steep ramp-rate momentum (+8.2 MW/hr) observed from 16:00 to 17:30.',
  },
  {
    id: 'shap_solar',
    featureName: 'Rooftop Solar Cloud Attenuation',
    impactMw: 1.5,
    category: 'Solar',
    description: 'Drop from 85% to 40% PV generation, transferring net customer demand back to substation feeders.',
  },
  {
    id: 'shap_volt',
    featureName: 'Feeder End Voltage Sag',
    impactMw: 0.8,
    category: 'Voltage',
    description: 'Voltage reduction to 10.82 kV increasing current draw for constant-power industrial motor loads.',
  },
];

export const F07_EXPLAINABILITY_NARRATIVE = 
  "Feeder F07 is predicted to exceed its 100 MW thermal limit in 38 minutes (reaching 108 MW at +45 to +60 min). " +
  "The primary drivers are concurrent commercial EV fleet charging (+4.8 MW) and sustained heatwave cooling demand (+3.6 MW), " +
  "further exacerbated by diminished rooftop solar offset (-1.5 MW).";
