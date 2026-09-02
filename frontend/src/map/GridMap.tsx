import React from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker } from 'react-leaflet';
import L from 'leaflet';
import { Feeder, Substation } from '../types';
import { MOCK_SUBSTATIONS } from '../data/feeders';
import { formatMw, formatTto } from '../utils/formatters';

// Clean professional Substation Pin with subtle teal/green utility accent
const createSubstationIcon = () => {
  return L.divIcon({
    className: 'custom-substation-pin',
    html: `
      <div style="
        background: #ffffff;
        border: 2px solid #073B3A;
        border-radius: 6px;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 5px rgba(7, 59, 58, 0.15);
      ">
        <span style="color: #073B3A; font-size: 10px; font-weight: 800; font-family: sans-serif;">SS</span>
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
};

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
  const defaultCenter: [number, number] = feeders.length > 0 && feeders[0].coordinates.length > 0 
    ? feeders[0].coordinates[0] 
    : [12.9716, 77.5946];
  const defaultZoom = 12;
  const substationIcon = createSubstationIcon();

  const getFeederStroke = (feeder: Feeder) => {
    const isF07 = feeder.id === 'F07';
    const isSelected = feeder.id === selectedFeederId;

    if (isF07) {
      if (isMitigated) {
        return {
          color: '#16a34a', // Safe green after prevention
          weight: 4.5,
          opacity: 0.95,
        };
      }
      return {
        color: '#dc2626', // Clean red when critical
        weight: 4.5,
        opacity: 0.95,
        dashArray: '6, 8',
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
          <span className={`w-3 sm:w-3.5 h-1 rounded-full ${isMitigated ? 'bg-emerald-600' : 'bg-red-600'}`}></span>
          <span className={`font-semibold ${isMitigated ? 'text-emerald-700' : 'text-red-700'}`}>
            F07 ({isMitigated ? 'Safe' : 'Hotspot'})
          </span>
        </div>
        <div className="flex items-center space-x-1.5 sm:space-x-2">
          <span className="w-3 sm:w-3.5 h-1 bg-[#073B3A] rounded-full"></span>
          <span className="text-slate-800 font-semibold">Selected Feeder</span>
        </div>
        <div className="flex items-center space-x-1.5 sm:space-x-2">
          <span className="w-3 sm:w-3.5 h-1 bg-slate-400 rounded-full"></span>
          <span className="text-slate-500 font-normal">Normal 11kV Line</span>
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

        {/* Substations with Deep Teal Pins */}
        {MOCK_SUBSTATIONS.map((sub: Substation) => (
          <Marker
            key={sub.id}
            position={[sub.lat, sub.lng]}
            icon={substationIcon}
          >
            <Popup>
              <div className="p-1 text-slate-800">
                <div className="font-bold text-xs text-slate-900 font-display">{sub.name}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">Bus Rating: {sub.voltage}</div>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Feeders */}
        {feeders.map((feeder) => {
          const isF07 = feeder.id === 'F07';
          const stroke = getFeederStroke(feeder);

          return (
            <React.Fragment key={feeder.id}>
              {feeder.coordinates.length > 0 && (
                <CircleMarker
                  center={feeder.coordinates[Math.floor(feeder.coordinates.length / 2)]}
                  radius={isF07 ? 5 : 3.5}
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
                          isF07 && isMitigated
                            ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                            : feeder.riskLevel === 'CRITICAL'
                            ? 'bg-red-50 text-red-700 border border-red-200'
                            : feeder.riskLevel === 'HIGH'
                            ? 'bg-amber-50 text-amber-800 border border-amber-200'
                            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        }`}
                      >
                        {isF07 && isMitigated ? 'MITIGATED' : feeder.riskLevel}
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
                        <span className={`font-bold ${isF07 && isMitigated ? 'text-emerald-700' : feeder.timeToOverloadMin ? 'text-red-600' : 'text-slate-700'}`}>
                          {isF07 && isMitigated ? 'SAFE' : formatTto(feeder.timeToOverloadMin)}
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
