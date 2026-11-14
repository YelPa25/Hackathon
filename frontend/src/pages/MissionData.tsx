import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useMissionData } from '../services/mission'
import type { Crew, CrewProfile, Dataset, Latest, Mission, Observation, ObservationPage, Replay } from '../services/mission'

const utc = new Intl.DateTimeFormat('en-GB', {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
})
const formatUtc = (value: string) => formatDate(value) + ' UTC'
const formatDate = (value: string) => utc.format(new Date(value))
const abbreviations: Readonly<Record<string, string>> = { co2: 'CO₂', bp: 'BP', spo2: 'SpO₂' }
const capitalize = (word: string) => word.charAt(0).toUpperCase() + word.slice(1)

function label(value: string) {
  return value.split('_').map((word) => abbreviations[word] ?? word).join(' ')
}

function metricLabel(metric: string) {
  return metric.split('_').map((word) => abbreviations[word] ?? capitalize(word)).join(' ')
}
const unit = (value: string) => ({ degC: '°C', percent: '%', score_0_4: '/ 4' })[value] ?? value

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="surface data-panel"><h2>{title}</h2>{children}</section>
}

function Resource<T>({ url, children }: { url: string; children: (data: T) => ReactNode }) {
  const [retry, setRetry] = useState(0)
  const result = useMissionData<T>(url, retry)
  if (result.state === 'loading') return <p className="surface data-panel" role="status">Loading mission data…</p>
  if (result.state === 'error') return <section className="surface data-panel">
    <p role="alert">{result.message}</p>
    <button type="button" className="data-control" onClick={() => setRetry(retry + 1)}>Retry</button>
  </section>
  return children(result.data)
}

function ReadingValue({ reading }: { reading: Observation }) {
  return reading.quality === 'MISSING'
    ? <span data-tone="warn">Missing<span className="sr-only"> ({label(reading.missing_reason ?? 'reason unavailable')})</span></span>
    : <>{reading.value} <small>{unit(reading.unit)}</small></>
}

function ReadingCards({ items, missing = [] }: { items: Observation[]; missing?: Observation[] }) {
  const groups = new Map(items.map((reading) => [reading.metric, reading]))
  for (const reading of missing) {
    if (!groups.has(reading.metric)) groups.set(reading.metric, reading)
  }
  if (!groups.size) return <p>No readings in this period.</p>
  return <dl className="reading-grid">{Array.from(groups.values(), (reading) => {
    const gap = reading.quality === 'VALID' ? missing.find((item) => item.metric === reading.metric) : undefined
    return <div className="reading-tile" key={reading.metric}>
      <dt>{metricLabel(reading.metric)}</dt>
      <dd className="reading-value"><ReadingValue reading={reading} /></dd>
      <dd><time dateTime={reading.timestamp_utc}>{formatUtc(reading.timestamp_utc)}</time></dd>
      <dd>{capitalize(label(reading.activity_context))} · {capitalize(label(reading.source))}</dd>
      {gap && <dd data-tone="warn">Newer sample missing · {formatUtc(gap.timestamp_utc)}</dd>}
    </div>
  })}</dl>
}

export function MissionOverview({ readiness }: { readiness: ReactNode }) {
  return <Resource<Mission> url="/api/mission">{(mission) => <div className="mission-stack">
    <div className="overview-grid">
      <Panel title="Fictional 90-day transit">
        <p className="mission-day">Day {mission.mission_day}</p>
        <p><time dateTime={mission.cursor_utc}>{formatUtc(mission.cursor_utc)}</time></p>
        <p>Historical data initialized · Synthetic observations</p>
      </Panel>
      {readiness}
    </div>
    <Panel title="Crew">
      <ul className="reading-grid">{mission.crew_summaries.map((crew) => <li key={crew.crew_id}>
        <Link className="reading-tile crew-link" to={'/crew-health?' + new URLSearchParams({ crew: crew.crew_id })}>
          <strong>{crew.display_name}</strong><span>{crew.role}</span>
        </Link>
      </li>)}</ul>
    </Panel>
    <Panel title="Latest valid cabin readings">
      <ReadingCards items={mission.cabin_readings} />
      <p className="dataset-note">CO₂ concentration in ppm is derived from an assumed cabin pressure of 760 mmHg. Partial pressure is the primary CO₂ reading.</p>
    </Panel>
  </div>}</Resource>
}

function History({ crew, metric }: { crew: string; metric: string }) {
  const params = new URLSearchParams({ crew_id: crew, metric, limit: '100' })
  return <Resource<ObservationPage> url={'/api/observations?' + params}>{(history) => {
    if (!history.items.length) return <p>No historical observations for this indicator.</p>
    return <>
      <p className="dataset-note">{history.items.length} stored observations · newest first · UTC</p>
      <div className="observation-scroll" role="region" aria-label="Historical readings" tabIndex={0}>
        <table className="observation-table">
          <thead><tr><th scope="col">Observed at (UTC)</th><th scope="col">Reading</th><th scope="col">Context</th><th scope="col">Source</th></tr></thead>
          <tbody>{history.items.slice().reverse().map((reading) => <tr key={reading.observation_id}>
            <td><time dateTime={reading.timestamp_utc}>{formatDate(reading.timestamp_utc)}</time></td>
            <td><ReadingValue reading={reading} /></td>
            <td>{capitalize(label(reading.activity_context))}</td>
            <td>{capitalize(label(reading.source))}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </>
  }}</Resource>
}

function CrewReadings({ crew }: { crew: string }) {
  const [metric, setMetric] = useState('')
  const params = new URLSearchParams({ crew_id: crew })
  return <Resource<Latest> url={'/api/observations/latest?' + params}>{(latest) => {
    const metrics = [...new Set([...latest.items, ...latest.latest_missing].map((item) => item.metric))].sort()
    const selected = metrics.includes(metric) ? metric : metrics.includes('resting_heart_rate') ? 'resting_heart_rate' : metrics[0]
    return <>
      <Panel title="Latest valid readings">
        <ReadingCards items={latest.items} missing={latest.latest_missing} />
      </Panel>
      <Panel title="Measurement history">
        {selected ? <>
          <label className="data-label">Health indicator
            <select value={selected} onChange={(event) => setMetric(event.target.value)}>
              {metrics.map((key) => <option key={key} value={key}>{metricLabel(key)}</option>)}
            </select>
          </label>
          <History crew={crew} metric={selected} />
        </> : <p>No measurement history for this crew member.</p>}
      </Panel>
    </>
  }}</Resource>
}

export function CrewHealth() {
  const [params, setParams] = useSearchParams()
  return <Resource<{ items: Crew[] }> url="/api/crew">{({ items }) => {
    const selected = items.find((crew) => crew.crew_id === params.get('crew')) ?? items[0]
    if (!selected) return <p>No crew profiles loaded.</p>
    const id = encodeURIComponent(selected.crew_id)
    return <div className="mission-stack">
      <Panel title="Crew member">
        <label className="data-label">Select astronaut
          <select value={selected.crew_id} onChange={(event) => setParams({ crew: event.target.value }, { replace: true })}>
            {items.map((crew) => <option key={crew.crew_id} value={crew.crew_id}>{crew.display_name}</option>)}
          </select>
        </label>
        <Resource<CrewProfile> url={'/api/crew/' + id}>{(profile) => <div className="profile-summary">
          <h3>{profile.display_name}</h3>
          <p>{profile.role} · {profile.age_years} years old · {label(profile.activity_pref)} exercise preference</p>
        </div>}</Resource>
      </Panel>
      <CrewReadings key={selected.crew_id} crew={selected.crew_id} />
    </div>
  }}</Resource>
}

export function MissionReplay() {
  return <Resource<Replay> url="/api/replay">{(state) => <Panel title="Published mission time">
    <p className="mission-day">Day {state.mission_day}</p>
    <p><time dateTime={state.cursor_utc}>{formatUtc(state.cursor_utc)}</time></p>
    <dl className="replay-facts">
      <div><dt>State</dt><dd>{label(state.status.toLowerCase())}</dd></div>
      <div><dt>Historical observations</dt><dd>{state.visible_count.toLocaleString()} available</dd></div>
      <div><dt>Future observations</dt><dd>Hidden</dd></div>
    </dl>
    <p>Replay controls will become available in Stage 03.</p>
  </Panel>}</Resource>
}

export function DataScience() {
  return <Resource<Dataset> url="/api/data">{(dataset) => <div className="mission-stack">
    <Panel title="Synthetic mission dataset">
      <p className="profile-summary"><strong>{dataset.dataset_id} · v{dataset.version}</strong></p>
      <p>Research-informed synthetic observations for a fictional crew. NASA and CDC publications informed the dataset design. It contains no actual astronaut health records.</p>
      <dl className="replay-facts">
        <div><dt>Mission duration</dt><dd>{dataset.mission_days} days</dd></div>
        <div><dt>Published history</dt><dd>Days 1–{dataset.historical_days}</dd></div>
        <div><dt>Historical records</dt><dd>{dataset.historical_count.toLocaleString()}</dd></div>
        <div><dt>Explicitly missing readings</dt><dd>{dataset.historical_missing_count}</dd></div>
      </dl>
      {dataset.source_status !== 'VERIFIED' && <p data-tone="warn" role="status">
        {dataset.source_status === 'INVALID' ? 'Source integrity check failed.' : 'Source bundle unavailable.'} The last verified import is available.
      </p>}
    </Panel>
    <Panel title={'Metric dictionary · ' + dataset.metrics.length + ' metrics'}>
      <dl className="reading-grid">{dataset.metrics.map((metric) =>
        <div className="reading-tile" key={metric.metric}>
          <dt>{metricLabel(metric.metric)} · {unit(metric.unit)}</dt>
          <dd>{metric.description}</dd>
          <dd>{metric.scope === 'person' ? 'Crew' : 'Cabin'} · {label(metric.measurement_cadence)}</dd>
        </div>
      )}</dl>
    </Panel>
    <Panel title="Research references">
      <ul className="reference-list">{dataset.references.map((reference) => <li key={reference.source_id}>
        <a href={reference.url}>{reference.title}</a>
        <p>{reference.organization} · {reference.use}</p>
      </li>)}</ul>
    </Panel>
  </div>}</Resource>
}
