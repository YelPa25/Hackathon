import { createContext, useContext } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { useLiveCapture } from './live'
import type { DemoSummary, Modality, SampleView } from './results'

type ResearchState = {
  result: DemoSummary | null
  setResult: Dispatch<SetStateAction<DemoSummary | null>>
  samples: Record<Modality, SampleView>
  setSample: (modality: Modality, update: Partial<SampleView>) => void
  live: Record<Modality, ReturnType<typeof useLiveCapture>>
}

export const ResearchContext = createContext<ResearchState | null>(null)

export function useResearch() {
  const state = useContext(ResearchContext)
  if (!state) throw new Error('ResearchProvider is unavailable.')
  return state
}
