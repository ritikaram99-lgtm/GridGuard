import React from 'react';
import { MapContainer, TileLayer, Popup, Polyline, CircleMarker } from 'react-leaflet';
import { Feeder } from '../types';
import { formatMw, formatTto } from '../utils/formatters';

interface GridMapProps {
  feeders: Feeder[];
  selectedFeederId: string;
  onSelectFeeder: (id: string) => void;
  onNavigateToIntelligence?: (id: string) => void;
  isMitigated?: boolean;
}

export const GridMap: React.FC<GridMapProps> = ({
  feeders,
  selectedFeederId,
  onSelectFeeder,
  onNavigateToIntelligence,
  isMitigated = false,
}) => {
  // Fallback center only used when no feeders have loaded yet -- the Delhi
  // display reference point (see data/delhiFeederLabels.ts).
  const defaultCenter: [number, number] = feeders.length > 0 && feeders[0].coordinates.length > 0
    ? feeders[0].coordinates[0]
    : [28.6139, 77.209];
  const defaultZoom = 12;

  const getFeederStroke = (feeder: Feeder) => {
    const isSelected = feeder.id === selectedFeederId;
    const isMitigatedFeeder = isSelected && isMitigated;
    const isAtRisk = feeder.riskLevel === 'CRITICAL' || feeder.riskLevel === 'HIGH';

    if (isSelected && isAtRisk && !isMitigatedFeeder) {
      return {
        color: '#dc2626', // Clean red when this selected feeder is critical/high risk
        weight: 4.5,
        opacity: 0.95,
        dashArray: '6, 8',
      };
    }
    if (isMitigatedFeeder) {
      return {
        color: '#16a34a', // Safe green after prevention
        weight: 4.5,
        opacity: 0.95,
      };
    }
    if (isSelected) {
      return {
        color: '#073B3A', // Deep teal for selected
        weight: 3.5,
        opacity: 0.9,
      };
    }
    // Neutral muted utility lines
    return {
      color: '#64748b',
      weight: 2.5,
      opacity: 0.65,
    };
  };

  return (
    <div className="w-full h-full min-h-[300px] sm:min-h-[360px] relative rounded-xl overflow-hidden border border-slate-200/90 bg-white">
      {/* Map Legend Overlay */}
      <div className="absolute top-2 right-2 sm:top-3 sm:right-3 z-[1000] bg-white/95 border border-slate-200/90 rounded-xl p-2 sm:p-3 shadow-sm text-[10px] sm:text-xs space-y-1 sm:space-y-1.5 backdrop-blur-xs max-w-[190px] sm:max-w-none">
        <div className="font-bold text-slate-800 text-[10px] sm:text-[11px] uppercase tracking-wider mb-0.5 sm:mb-1 font-display">
          Network Topology
        </div>
        <div className="flex items-center space-x-1.5 sm:space-x-2">
          <span className="w-3 sm:w-3.5 h-1 rounded-full bg-red-600"></span>
          <span className="text-red-700 font-semibold">Selected Feeder At Risk</span>
        </div>
        <div className="flex items-center space-x-1.5 sm:space-x-2">
          <span className="w-3 sm:w-3.5 h-1 bg-emerald-600 rounded-full"></span>
          <span className="text-emerald-700 font-semibold">Mitigated</span>
        </div>
        <div className="flex items-center space-x-1.5 sm:space-x-2">
          <span className="w-3 sm:w-3.5 h-1 bg-[#073B3A] rounded-full"></span>
          <span className="text-slate-800 font-semibold">Selected Feeder</span>
        </div>
        <div className="flex items-center space-x-1.5 sm:space-x-2">
          <span className="w-3 sm:w-3.5 h-1 bg-slate-400 rounded-full"></span>
          <span className="text-slate-500 font-normal">Other Feeder</span>
        </div>
      </div>

      <MapContainer
        center={defaultCenter}
        zoom={defaultZoom}
        scrollWheelZoom={true}
        className="w-full h-full"
        style={{ height: '100%', minHeight: '300px' }}
      >
        {/* Carto Positron Light Muted Basemap */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        />

        {/* Feeders -- no substation layer is rendered: the backend has no
            real substation topology, and we no longer overlay a fabricated
            one on top of real feeder data. */}
        {feeders.map((feeder) => {
          const isSelected = feeder.id === selectedFeederId;
          const isMitigatedFeeder = isSelected && isMitigated;
          const stroke = getFeederStroke(feeder);

          return (
            <React.Fragment key={feeder.id}>
              {feeder.coordinates.length > 0 && (
                <CircleMarker
                  center={feeder.coordinates[Math.floor(feeder.coordinates.length / 2)]}
                  radius={isSelected ? 5 : 3.5}
                  pathOptions={{
                    fillColor: stroke.color,
                    fillOpacity: 0.9,
                    color: '#ffffff',
                    weight: 1.5,
                  }}
                  eventHandlers={{
                    click: () => onSelectFeeder(feeder.id),
                  }}
                />
              )}

              <Polyline
                positions={feeder.coordinates}
                pathOptions={stroke}
                eventHandlers={{
                  click: () => onSelectFeeder(feeder.id),
                }}
              >
                <Popup>
                  <div className="p-1 text-slate-800 min-w-[190px]">
                    <div className="flex items-center justify-between border-b border-slate-100 pb-1 mb-2">
                      <span className="font-extrabold text-xs text-slate-900 font-display">{feeder.id}</span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                          isMitigatedFeeder
                            ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                            : feeder.riskLevel === 'CRITICAL'
                            ? 'bg-red-50 text-red-700 border border-red-200'
                            : feeder.riskLevel === 'HIGH'
                            ? 'bg-amber-50 text-amber-800 border border-amber-200'
                            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        }`}
                      >
                        {isMitigatedFeeder ? 'MITIGATED' : feeder.riskLevel}
                      </span>
                    </div>
                    <div className="text-xs text-slate-600 space-y-1.5 mb-2.5">
                      <div className="flex justify-between">
                        <span className="text-slate-400">Current Load:</span>
                        <span className="font-bold text-slate-900">
                          {formatMw(feeder.currentLoadMw)} / {feeder.capacityMw} MW
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Stress Score:</span>
                        <span className="font-bold text-slate-900">{feeder.stressScore} / 100</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Time-to-Overload:</span>
                        <span className={`font-bold ${feeder.timeToOverloadMin ? 'text-red-600' : 'text-slate-700'}`}>
                          {formatTto(feeder.timeToOverloadMin)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Peak Forecast:</span>
                        <span className="font-bold text-slate-900">{formatMw(feeder.peakForecastMw)}</span>
                      </div>
                    </div>
                    {onNavigateToIntelligence && (
                      <button
                        onClick={() => onNavigateToIntelligence(feeder.id)}
                        className="w-full px-3 py-1.5 bg-[#073B3A] hover:bg-[#0B5D56] text-white text-xs font-bold rounded-lg transition-colors text-center cursor-pointer"
                      >
                        Analyze Feeder →
                      </button>
                    )}
                  </div>
                </Popup>
              </Polyline>
            </React.Fragment>
          );
        })}
      </MapContainer>
    </div>
  );
};
