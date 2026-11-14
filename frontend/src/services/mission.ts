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
  crew_readings: Record<string, Observation>; cabin_latest_missing: Observation[]
  mission_day: number; cursor_utc: string; synthetic: true; replay_status: Replay["status"]
  crew_summaries: Crew[]; cabin_readings: Observation[]
}
export type Replay = {
  dataset_id: string; mission_day: number; cursor_utc: string
  status: 'PAUSED' | 'RUNNING' | 'COMPLETE'; visible_count: number; revision: number
  speed: ReplaySpeed
}
export type ReplaySpeed = 5 | 2 | 0.5
export type ReplayAction = 'PLAY' | 'PAUSE' | 'NEXT_DAY' | 'NEXT_EVENT' | 'RESET' | 'SET_SPEED'
export type ReplayView = Replay & {
  historical_days: number; mission_days: number; playback_error: string | null
  latest_activity: {
    mission_day: number; observation_count: number; crew_count: number; cabin_count: number
    first_utc: string | null; last_utc: string | null
  } | null
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

export async function fetchMissionData<T>(
  url: string, signal: AbortSignal, options?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    cache: 'no-store',
    headers: { Accept: 'application/json', ...options?.headers },
    signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message ?? 'The backend could not load this view.')
  }
  return response.json()
}

async function fetchObservationSeries(query: URL, signal: AbortSignal) {
  let page = await fetchMissionData<ObservationPage>(query.href, signal)
  const { revision, cursor_utc: cutoff } = page
  const items = [...page.items]
  const seen = new Set<string>()
  while (page.next_cursor) {
    if (seen.has(page.next_cursor)) throw new Error('History pagination repeated. Retry to reload the records.')
    seen.add(page.next_cursor)
    query.searchParams.set('cursor', page.next_cursor)
    page = await fetchMissionData<ObservationPage>(query.href, signal)
    if (page.revision !== revision || page.cursor_utc !== cutoff) {
      throw new Error('Mission time changed while loading history. Retry to reload the records.')
    }
    items.push(...page.items)
  }
  return { items, revision, cutoff }
}

export async function fetchObservationHistory(url: string, signal: AbortSignal): Promise<Observation[]> {
  const query = new URL(url, window.location.origin)
  const metrics = query.searchParams.getAll('metric')
  const histories = await Promise.all(metrics.map((metric) => {
    const seriesUrl = new URL(query)
    seriesUrl.searchParams.set('metric', metric)
    return fetchObservationSeries(seriesUrl, signal)
  }))
  if (histories.some(({ revision, cutoff }) => revision !== histories[0].revision || cutoff !== histories[0].cutoff)) {
    throw new Error('Mission time changed while loading history. Retry to reload the records.')
  }
  return histories.flatMap(({ items }) => items).sort((a, b) =>
    a.timestamp_utc.localeCompare(b.timestamp_utc) || a.observation_id.localeCompare(b.observation_id))
}

export function useMissionData<T>(
  url: string, retry = 0, loader: (url: string, signal: AbortSignal) => Promise<T> = fetchMissionData<T>, cutoff?: string,
): Result<T> {
  const [response, setResponse] = useState<{ url: string; retry: number; cutoff?: string; result: Result<T> }>()
  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      let result: Result<T>
      try {
        const data = await loader(url, controller.signal)
        result = { state: 'ready', data }
      } catch (error) {
        result = { state: 'error', message: error instanceof Error && error.name === 'Error'
          ? error.message : 'The backend could not load this view.' }
      }
      if (!controller.signal.aborted) setResponse({ url, retry, cutoff, result })
    }
    void load()
    return () => controller.abort()
  }, [url, retry, loader, cutoff])
  // While advancing, keep the previous published data visible during refresh. Hide it immediately after reset.
  const previousCutoff = response?.cutoff
  const current = previousCutoff === cutoff || (
    response?.result.state === 'ready' && previousCutoff !== undefined && cutoff !== undefined && previousCutoff < cutoff
  )
  return response?.url === url && response.retry === retry && current ? response.result : { state: 'loading' }
}
