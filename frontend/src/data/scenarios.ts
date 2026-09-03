import { GridScenario } from '../types';

// Real, functional scenario selector: choosing a scenario pins every
// ML-backed request to a specific real historical forecast origin (see
// gridService.setActiveOrigin), so the whole app (feeder list, map, risk,
// recommendations) reflects that ONE real, already-computed ML moment.
// Not a fabricated "what-if" -- every number shown is the backend's real
// output for that timestamp.
export const MOCK_SCENARIOS: GridScenario[] = [
  {
    id: 'live',
    name: 'Live (Latest Forecast)',
    tagline: 'Default',
    description: 'The backend\'s latest valid forecast origin -- the default view.',
    origin: null,
  },
  {
    id: 'single_feeder_alert',
    name: 'Demo Replay',
    tagline: '2020-01-20 14:00 Origin',
    description: 'Historical ML forecast origin (2020-01-20 14:00) where feeder F06 is evaluated as HIGH risk (stress score 62.61), triggering the Action → Simulation → Prevention pipeline.',
    origin: '2020-01-20 14:00:00',
  },
];
