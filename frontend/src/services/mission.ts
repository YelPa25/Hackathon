import { useEffect, useState } from 'react'

export type Crew = { crew_id: string; display_name: string; role: string }
export type CrewProfile = Crew & { age_years: number; activity_pref: string }
export type Observation = {
  observation_id: string
  timestamp_utc: string
  metric: string
  value: number | null
  unit: string
  source: string
  activity_context: string
  quality: 'VALID' | 'MISSING'
  missing_reason: string | null
  provenance: 'SYNTHETIC'
}
export type ObservationPage = {
  revision: number; cursor_utc: string; items: Observation[]; next_cursor: string | null
}
export type Latest = ObservationPage & { latest_missing: Observation[] }
export type Mission = {
  mission_day: number; cursor_utc: string; synthetic: true
  crew_summaries: Crew[]; cabin_readings: Observation[]
}
export type Replay = {
  dataset_id: string; mission_day: number; cursor_utc: string
  status: 'PAUSED' | 'RUNNING' | 'COMPLETE'; visible_count: number
}
export type Metric = { metric: string; unit: string; description: string; scope: 'person' | 'cabin'; measurement_cadence: string }
export type Reference = { source_id: string; organization: string; title: string; url: string; use: string }
export type Dataset = {
  dataset_id: string; version: string; provenance: 'SYNTHETIC'; mission_days: number
  historical_days: number; historical_count: number; historical_missing_count: number
  mission_start_utc: string; source_status: 'VERIFIED' | 'UNAVAILABLE' | 'INVALID'
  cabin_total_pressure_assumed_mmhg: number; replay: Replay; metrics: Metric[]; references: Reference[]
}

type Result<T> = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; data: T }

export function useMissionData<T>(url: string, retry = 0): Result<T> {
  const [response, setResponse] = useState<{ url: string; retry: number; result: Result<T> }>()
  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      let result: Result<T>
      try {
        const response = await fetch(url, {
          cache: 'no-store',
          headers: { Accept: 'application/json' },
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
        })
        if (!response.ok) {
          const body = await response.json().catch(() => null)
          throw new Error(body?.error?.message ?? 'The backend could not load this view.')
        }
        const data: T = await response.json()
        result = { state: 'ready', data }
      } catch (error) {
        result = { state: 'error', message: error instanceof Error && error.name === 'Error'
          ? error.message : 'The backend could not load this view.' }
      }
      if (!controller.signal.aborted) setResponse({ url, retry, result })
    }
    void load()
    return () => controller.abort()
  }, [url, retry])
  return response?.url === url && response.retry === retry ? response.result : { state: 'loading' }
}
