// Display-only rebrand: the backend/ML pipeline is trained on and returns
// Panama data (feeder names + coordinates come from ml/src/feeder_generator.py,
// which we do not modify). This module maps the 10 ML feeder ids (F01-F10) to
// Delhi-area display names, and recenters their coordinates from the Panama
// reference point onto a Delhi reference point via a fixed offset -- the
// REAL relative spatial layout produced by the ML allocation is preserved
// unchanged, only the map is recentered for display. No feeder data itself
// (capacity, load, risk, forecast) is altered by this module.

export const DELHI_FEEDER_NAMES: Record<string, string> = {
  F01: 'Rohini Residential North',
  F02: 'Dwarka Residential',
  F03: 'Connaught Place Commercial Core',
  F04: 'Nehru Place Business Park',
  F05: 'Okhla Industrial Area A',
  F06: 'Mayapuri Industrial Area B',
  F07: 'Lajpat Nagar Mixed Suburban',
  F08: 'Najafgarh Mixed Fringe',
  F09: 'Karol Bagh EV Corridor',
  F10: 'IGI Airport EV Depot',
};

export function displayFeederName(feederId: string, backendName: string): string {
  return DELHI_FEEDER_NAMES[feederId.toUpperCase()] ?? backendName;
}

// Panama reference point used by ml/src/feeder_generator.py's own
// PANAMA_REFERENCE constant (documented there as a plausible-coordinate
// anchor, not a real feeder location) vs. a Delhi reference point.
const PANAMA_REF = { lat: 8.9824, lon: -79.5199 };
const DELHI_REF = { lat: 28.6139, lon: 77.209 };

export function toDisplayCoordinate(lat: number, lon: number): [number, number] {
  return [DELHI_REF.lat + (lat - PANAMA_REF.lat), DELHI_REF.lon + (lon - PANAMA_REF.lon)];
}
