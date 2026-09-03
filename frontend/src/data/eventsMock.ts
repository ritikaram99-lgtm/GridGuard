export interface GridEvent {
  id: string;
  timestamp: string;
  feederId?: string;
  title: string;
  type: 'critical' | 'warning' | 'info' | 'success';
  description: string;
}

// ILLUSTRATIVE ONLY: the backend persists risk alerts (see
// backend/app/models/alert.py) but does not currently expose any endpoint
// returning that history, so this demo log cannot be backed by real data.
// Kept generic (no specific feeder id, MW figure, or named asset claimed) so
// it never contradicts the real live values shown elsewhere on this page.
export const MOCK_RECENT_EVENTS: GridEvent[] = [
  {
    id: 'evt_1',
    timestamp: 'Demo log',
    title: 'SCADA Telemetry Sweep Completed',
    type: 'success',
    description: 'Periodic telemetry sweep across monitored feeders completed with nominal reporting latency.',
  },
  {
    id: 'evt_2',
    timestamp: 'Demo log',
    title: 'Forecast Cycle Refreshed',
    type: 'info',
    description: 'The 24-hour ML demand forecast was recomputed for all monitored feeders.',
  },
  {
    id: 'evt_3',
    timestamp: 'Demo log',
    title: 'Risk Evaluation Cycle Completed',
    type: 'info',
    description: 'The Grid Stress Engine re-evaluated risk for all monitored feeders against the latest forecast.',
  },
];
