import { useState } from 'react'
import type { ReactNode } from 'react'
import { useReplay } from '../services/replay-state'
import { useMissionData } from '../services/mission'

const utc = new Intl.DateTimeFormat('en-GB', {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
})
export const formatUtc = (value: string) => formatDate(value) + ' UTC'
const exactUtc = new Intl.DateTimeFormat('en-GB', {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC',
})
export const formatExactUtc = (value: string) => exactUtc.format(new Date(value)) + ' UTC'
export const formatDate = (value: string) => utc.format(new Date(value))
const abbreviations: Readonly<Record<string, string>> = { co2: 'CO₂', bp: 'BP', spo2: 'SpO₂' }
export const capitalize = (word: string) => word.charAt(0).toUpperCase() + word.slice(1)

export function label(value: string) {
  return value.split('_').map((word) => abbreviations[word] ?? word).join(' ')
}

export function metricLabel(metric: string) {
  return metric.split('_').map((word) => abbreviations[word] ?? capitalize(word)).join(' ')
}
export const unit = (value: string) => ({ degC: '°C', percent: '%', score_0_4: '/ 4' })[value] ?? value

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="surface data-panel"><h2>{title}</h2>{children}</section>
}

export function Resource<T>({ url, load, live, children }: {
  url: string; live?: boolean; load?: (url: string, signal: AbortSignal) => Promise<T>; children: (data: T) => ReactNode
}) {
  const [retry, setRetry] = useState(0)
  const { state } = useReplay()
  const result = useMissionData<T>(url, retry, load, live ? state?.cursor_utc : undefined)
  if (live && result.state === 'ready') {
    const snapshot = result.data as { cursor_utc?: string; replay?: { cursor_utc: string } }
    const cursor = snapshot.cursor_utc ?? snapshot.replay?.cursor_utc
    if (!state || cursor && cursor > state.cursor_utc) {
      return <p className="surface data-panel" role="status">Synchronizing published mission time…</p>
    }
  }
  if (result.state === 'loading') return <p className="surface data-panel" role="status">Loading mission data…</p>
  if (result.state === 'error') return <section className="surface data-panel">
    <p role="alert">{result.message}</p>
    <button type="button" className="data-control" onClick={() => setRetry(retry + 1)}>Retry</button>
  </section>
  return children(result.data)
}
