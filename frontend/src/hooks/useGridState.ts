import { useState, useEffect, useCallback } from 'react';
import { Feeder, ScenarioId } from '../types';
import { gridService, setActiveOrigin } from '../api/gridService';
import { MOCK_SCENARIOS } from '../data/scenarios';

export function useGridState() {
  const [activeScenarioId, setActiveScenarioId] = useState<ScenarioId>('live');
  // No feeder is privileged by default -- picked once real feeder data loads
  // (see below), rather than hardcoding one of the 10 ML feeders.
  const [selectedFeederId, setSelectedFeederId] = useState<string>('');
  const [feeders, setFeeders] = useState<Feeder[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  // Tracks which single feeder had a dispatch confirmed in this session (if
  // any). We only know a real dispatch happened -- we do NOT know a new
  // load/score for that feeder without another real API call, so no numbers
  // are fabricated here; UI reads this only to show a "dispatched" badge.
  const [mitigatedFeederId, setMitigatedFeederId] = useState<string | null>(null);

  const loadFeeders = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      // Pin every ML-backed request to the selected scenario's real origin
      // (or clear the pin for 'live') before fetching -- see data/scenarios.ts.
      const scenario = MOCK_SCENARIOS.find(s => s.id === activeScenarioId);
      setActiveOrigin(scenario?.origin ?? null);

      const data = await gridService.getFeeders();
      if (!data || data.length === 0) {
        throw new Error('Telemetry stream offline. Unable to retrieve the latest grid data.');
      }
      setFeeders(data);
      setSelectedFeederId(prev => (prev && data.some(f => f.id === prev) ? prev : data[0].id));
    } catch (err: any) {
      console.error('Failed to load feeders:', err);
      setError(err?.message || 'Unable to retrieve the latest grid data.');
    } finally {
      setIsLoading(false);
    }
  }, [activeScenarioId]);

  useEffect(() => {
    loadFeeders();
  }, [loadFeeders]);

  const changeScenario = (id: ScenarioId) => {
    setActiveScenarioId(id);
    setMitigatedFeederId(null);
  };

  const applyMitigation = (feederId: string) => {
    setMitigatedFeederId(feederId);
  };

  const resetMitigation = () => {
    setMitigatedFeederId(null);
  };

  const activeFeeder = feeders.find(f => f.id === selectedFeederId) || feeders[0];
  const isMitigated = mitigatedFeederId !== null;

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
    mitigatedFeederId,
    applyMitigation,
    resetMitigation,
    reloadFeeders: loadFeeders,
  };
}
