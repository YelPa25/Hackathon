import { useCallback, useState } from 'react'
import type { ReactNode } from 'react'
import { useLiveCapture } from './live'
import type { DemoSummary, Modality, SampleView } from './results'
import { ResearchContext } from './state'

const initialSample: SampleView = { scenario: 'fatigue_ramp', step: -1, feature: '', open: false }

export function ResearchProvider({ children }: { children: ReactNode }) {
  const [result, setResult] = useState<DemoSummary | null>(null)
  const [samples, setSamples] = useState({ facial: initialSample, speech: initialSample })
  const facial = useLiveCapture('facial')
  const speech = useLiveCapture('speech')

  const setSample = useCallback((modality: Modality, update: Partial<SampleView>) => {
    setSamples((current) => ({ ...current, [modality]: { ...current[modality], ...update } }))
  }, [])

  return <ResearchContext.Provider value={{ result, setResult, samples, setSample, live: { facial, speech } }}>
    {children}
  </ResearchContext.Provider>
}
