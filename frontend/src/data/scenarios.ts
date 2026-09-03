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
    name: 'Demo: Single Feeder Alert',
    tagline: 'Real ML scenario',
    // Found by querying the real ML pipeline across its historical origin
    // range: at this timestamp, feeder F06 (an industrial-type feeder) is
    // independently classified HIGH by the real Grid Stress Engine while
    // every other feeder stays LOW/MODERATE -- a real, naturally-occurring
    // single-feeder alert, not an invented one.
    description: 'A real historical origin (2020-01-20 14:00) where the ML Stress Engine independently flags exactly one feeder as HIGH risk.',
    origin: '2020-01-20 14:00:00',
  },
];
