export interface GridEvent {
  id: string;
  timestamp: string;
  feederId?: string;
  title: string;
  type: 'critical' | 'warning' | 'info' | 'success';
  description: string;
}

export const MOCK_RECENT_EVENTS: GridEvent[] = [
  {
    id: 'evt_1',
    timestamp: '17:12:04',
    feederId: 'F07',
    title: 'Predicted Thermal Overload Alert',
    type: 'critical',
    description: 'Demand trajectory projected to breach 100 MW continuous threshold in 38 min (Peak 108 MW).',
  },
  {
    id: 'evt_2',
    timestamp: '17:08:30',
    feederId: 'F03',
    title: 'High Load Growth Rate Detected',
    type: 'warning',
    description: 'Ramp-rate increased to +6.8 MW/h on Silicon Expressway corridor.',
  },
  {
    id: 'evt_3',
    timestamp: '17:01:15',
    feederId: 'F07',
    title: 'Metro East BESS Unit 2 Standby Confirmed',
    type: 'info',
    description: '4-hour battery storage unit reporting 9.0 MW discharge capacity available for dispatch.',
  },
  {
    id: 'evt_4',
    timestamp: '16:54:22',
    feederId: 'F07',
    title: 'Commercial EV Fleet Depot Demand Surge',
    type: 'warning',
    description: 'Transit East terminal concurrent charging load reached 4.8 MW (+145% baseline).',
  },
  {
    id: 'evt_5',
    timestamp: '16:45:00',
    feederId: 'SUB_ALPHA',
    title: 'SCADA Telemetry Sweep Completed',
    type: 'success',
    description: 'All 10 feeder transducers and substation transformer telemetry reporting nominal latency (28ms).',
  },
];
