import { useState, useEffect, useCallback } from 'react';
import { Feeder, ScenarioId } from '../types';
import { gridService } from '../api/gridService';

export function useGridState() {
  const [activeScenarioId, setActiveScenarioId] = useState<ScenarioId>('summer_peak');
  const [selectedFeederId, setSelectedFeederId] = useState<string>('F07');
  const [feeders, setFeeders] = useState<Feeder[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isMitigated, setIsMitigated] = useState<boolean>(false);

  const loadFeeders = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await gridService.getFeeders(activeScenarioId);
      if (!data || data.length === 0) {
        throw new Error('Telemetry stream offline. Unable to retrieve the latest grid data.');
      }
      // If F07 is mitigated in UI, update its state
      if (isMitigated) {
        const updated = data.map(f => {
          if (f.id === 'F07') {
            return {
              ...f,
              currentLoadMw: 95,
              peakForecastMw: 95,
              stressScore: 40,
              riskLevel: 'LOW' as const,
              timeToOverloadMin: null,
            };
          }
          return f;
        });
        setFeeders(updated);
      } else {
        setFeeders(data);
      }
    } catch (err: any) {
      console.error('Failed to load feeders:', err);
      setError(err?.message || 'Unable to retrieve the latest grid data.');
    } finally {
      setIsLoading(false);
    }
  }, [activeScenarioId, isMitigated]);

  useEffect(() => {
    loadFeeders();
  }, [loadFeeders]);

  const changeScenario = (id: ScenarioId) => {
    setActiveScenarioId(id);
    setIsMitigated(false);
  };

  const applyMitigation = () => {
    setIsMitigated(true);
  };

  const resetMitigation = () => {
    setIsMitigated(false);
  };

  const activeFeeder = feeders.find(f => f.id === selectedFeederId) || feeders[0];

  return {
    activeScenarioId,
    changeScenario,
    selectedFeederId,
    setSelectedFeederId,
    feeders,
    activeFeeder,
    isLoading,
    error,
    isMitigated,
    applyMitigation,
    resetMitigation,
    reloadFeeders: loadFeeders,
  };
}
