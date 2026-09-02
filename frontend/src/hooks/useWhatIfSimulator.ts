import { useState, useEffect, useCallback } from 'react';
import { WhatIfParams, WhatIfRecalculationResult } from '../types';
import { gridService } from '../api/gridService';

const DEFAULT_PARAMS: WhatIfParams = {
  ambientTempC: 36,
  evDemandPct: 145,
  solarGenerationPct: 40,
};

export function useWhatIfSimulator(feederId: string = 'F07') {
  const [params, setParams] = useState<WhatIfParams>(DEFAULT_PARAMS);
  const [result, setResult] = useState<WhatIfRecalculationResult | null>(null);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);

  const runSimulation = useCallback(async (currentParams: WhatIfParams) => {
    setIsSimulating(true);
    try {
      const res = await gridService.simulateWhatIf(feederId, currentParams);
      setResult(res);
    } catch (err) {
      console.error('Simulation error:', err);
    } finally {
      setIsSimulating(false);
    }
  }, [feederId]);

  useEffect(() => {
    runSimulation(params);
  }, [params, runSimulation]);

  const updateParam = (key: keyof WhatIfParams, value: number) => {
    setParams(prev => ({
      ...prev,
      [key]: value,
    }));
  };

  const resetToBaseline = () => {
    setParams(DEFAULT_PARAMS);
  };

  const applyPreset = (preset: Partial<WhatIfParams>) => {
    setParams(prev => ({
      ...prev,
      ...preset,
    }));
  };

  return {
    params,
    result,
    isSimulating,
    updateParam,
    resetToBaseline,
    applyPreset,
  };
}
