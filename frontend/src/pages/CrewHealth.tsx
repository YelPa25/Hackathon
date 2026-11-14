import { Activity, BedDouble, Droplets, HeartPulse, Thermometer, Zap } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { fetchObservationHistory } from '../services/mission'
import type { Crew, CrewProfile, Latest, Observation } from '../services/mission'
import { HealthChart, HistoryRecords } from './HealthChart'
import type { HistoryWindow, Series } from './HealthChart'
import '../styles/crew-health.css'
import { capitalize, formatExactUtc, label, metricLabel, Panel, Resource, unit } from './mission-display'

const primary = [
  { title: 'Resting Heart Rate', metrics: ['resting_heart_rate'], icon: HeartPulse },
  { title: 'Blood Pressure', metrics: ['systolic_bp', 'diastolic_bp'], icon: Activity },
  { title: 'Sleep Duration', metrics: ['sleep_duration'], icon: BedDouble },
  { title: 'Fatigue', metrics: ['fatigue'], icon: Zap },
  { title: 'Body Temperature', metrics: ['body_temperature'], icon: Thermometer },
  { title: 'Oxygen Saturation', metrics: ['spo2'], icon: Droplets },
]

const primaryMetrics = new Set(primary.flatMap(({ metrics }) => metrics))
const pressureMetrics = primary[1].metrics
const ranges = [7, 30, 45] as const
type HistoryDays = (typeof ranges)[number]

function readingStatus(reading?: Observation, missing?: Observation) {
  if (!reading) return { text: missing ? 'Missing' : 'Unavailable', tone: 'warn' }
  return missing ? { text: 'Newer sample missing', tone: 'warn' } : { text: 'Available', tone: 'good' }
}

function describeReading(reading: Observation) {
  return reading.value === null ? 'Missing' : reading.value + ' ' + unit(reading.unit)
}

function ReadingDetails({ title, records }: { title: string; records: Observation[] }) {
  if (!records.length) return null
  return <details className="health-details reading-details">
    <summary aria-label={title + ' reading details'}>Reading details</summary>
    <dl>{records.map((record) => <div key={record.observation_id}>
      <dt>{metricLabel(record.metric)} · {capitalize(record.quality.toLowerCase())}</dt>
      <dd><time dateTime={record.timestamp_utc}>{formatExactUtc(record.timestamp_utc)}</time></dd>
      <dd>{capitalize(label(record.source))} · {capitalize(record.provenance.toLowerCase())} provenance</dd>
      <dd>Context: {capitalize(label(record.activity_context))}</dd>
      {record.missing_reason && <dd>{capitalize(label(record.missing_reason.toLowerCase()))}</dd>}
    </div>)}</dl>
  </details>
}

function PrimaryReadings({ latest }: { latest: Latest }) {
  return <Panel title="Health overview">
    <p className="health-section-note">Latest available measurements · Synthetic</p>
    <div className="primary-health-grid">{primary.map(({ title, metrics, icon: Icon }) => {
      const entries = metrics.map((metric) => ({
        reading: latest.items.find((item) => item.metric === metric),
        missing: latest.latest_missing.find((item) => item.metric === metric),
      }))
      const valid = entries.flatMap(({ reading }) => reading ? [reading] : [])
      const gaps = entries.flatMap(({ missing }) => missing ? [missing] : [])
      const isPressure = metrics === pressureMetrics
      let status = readingStatus(valid[0], gaps[0])
      if (isPressure && valid.length === 1) status = { text: 'Partial reading', tone: 'warn' }
      if (isPressure && valid.length === 2 && valid[0].timestamp_utc !== valid[1].timestamp_utc) {
        status = { text: 'Separate measurement times', tone: 'warn' }
      }
      return <section className="health-metric" key={title} aria-label={title}>
        <h3><Icon size={17} aria-hidden="true" />{title}</h3>
        <p className="health-metric-value">
          <strong>{entries.map(({ reading }) => reading?.value ?? '—').join(isPressure ? ' / ' : '')}</strong>
          {valid[0] && <span>{unit(valid[0].unit)}</span>}
        </p>
        {isPressure && <p className="health-pressure-label">Systolic / Diastolic</p>}
        <p className="health-reading-status" data-tone={status.tone}><span className="status-dot" aria-hidden="true" />{status.text}</p>
        <ReadingDetails title={title} records={[...valid, ...gaps]} />
      </section>
    })}</div>
  </Panel>
}

function OtherReadings({ latest, select }: { latest: Latest; select: (metric: string) => void }) {
  const metrics = [...new Set([...latest.items, ...latest.latest_missing].map(({ metric }) => metric))]
    .filter((metric) => !primaryMetrics.has(metric)).sort()
  if (!metrics.length) return null
  return <Panel title="Other available indicators">
    <ul className="secondary-health-list">{metrics.map((metric) => {
      const reading = latest.items.find((item) => item.metric === metric)
      const missing = latest.latest_missing.find((item) => item.metric === metric)
      return <li key={metric}>
        <div className="secondary-reading-row">
          <a href="#health-history" onClick={() => select(metric)}>{metricLabel(metric)}</a>
          <span>{reading ? describeReading(reading) : readingStatus(reading, missing).text}</span>
        </div>
        {reading && missing && <p className="health-reading-status" data-tone="warn">Newer sample missing</p>}
        <ReadingDetails title={metricLabel(metric)} records={[reading, missing].filter((item) => item !== undefined)} />
      </li>
    })}</ul>
  </Panel>
}

function historyWindow(cutoff: string, days: HistoryDays): HistoryWindow {
  const to = new Date(cutoff)
  const start = new Date(to)
  start.setUTCHours(0, 0, 0, 0)
  start.setUTCDate(start.getUTCDate() - (days - 1))
  return { from: start.toISOString().replace('.000Z', 'Z'), to: cutoff }
}

function MeasurementHistory({ crew, latest, metric, days, setMetric, setDays }: {
  crew: string; latest: Latest; metric: string; days: HistoryDays
  setMetric: (metric: string) => void; setDays: (days: HistoryDays) => void
}) {
  const available = [...new Set([...latest.items, ...latest.latest_missing].map((item) => item.metric))].sort()
  const choices = available.filter((key) => !pressureMetrics.includes(key))
  if (pressureMetrics.some((key) => available.includes(key))) choices.unshift('blood_pressure')
  const selected = choices.includes(metric) ? metric : choices.includes('resting_heart_rate') ? 'resting_heart_rate' : choices[0]
  if (!selected) return <Panel title="Measurement history"><p>No measurement history for this crew member.</p></Panel>

  const series: Series[] = selected === 'blood_pressure'
    ? [{ metric: 'systolic_bp', name: 'Systolic', color: 'var(--color-cyan)' },
      { metric: 'diastolic_bp', name: 'Diastolic', color: 'var(--health-secondary)', dashed: true }]
    : [{ metric: selected, name: metricLabel(selected), color: 'var(--color-cyan)' }]
  const title = selected === 'blood_pressure' ? 'Blood Pressure' : metricLabel(selected)
  const window = historyWindow(latest.cursor_utc, days)
  const query = new URLSearchParams({ crew_id: crew, from_utc: window.from, to_utc: window.to, limit: '100' })
  series.forEach(({ metric }) => query.append('metric', metric))
  return <section className="surface data-panel health-history" id="health-history" tabIndex={-1} aria-labelledby="health-history-title">
    <h2 id="health-history-title">Measurement history</h2>
    <div className="health-history-controls">
      <label className="data-label">Health indicator
        <select value={selected} onChange={(event) => setMetric(event.target.value)}>
          {choices.map((key) => <option key={key} value={key}>{metricLabel(key)}</option>)}
        </select>
      </label>
      <fieldset className="health-ranges">
        <legend>History range</legend>
        <div>{ranges.map((range) => <button type="button" aria-pressed={range === days} key={range}
          onClick={() => setDays(range)}>{range} days</button>)}</div>
      </fieldset>
    </div>
    <Resource<Observation[]> url={'/api/observations?' + query} load={fetchObservationHistory}>{(records) =>
      records.length ? <>
        <HealthChart records={records} series={series} window={window} title={title} />
        <HistoryRecords key={crew + selected} records={records} />
      </> : <p className="health-chart-empty">No recorded measurements in this range. Select a longer range to look further back.</p>
    }</Resource>
  </section>
}

export default function CrewHealth() {
  const [params, setParams] = useSearchParams()
  const [metric, setMetric] = useState('resting_heart_rate')
  const [days, setDays] = useState<HistoryDays>(45)
  return <Resource<{ items: Crew[] }> url="/api/crew">{({ items }) => {
    const selected = items.find((crew) => crew.crew_id === params.get('crew')) ?? items[0]
    if (!selected) return <p>No crew profiles loaded.</p>
    const id = encodeURIComponent(selected.crew_id)
    return <div className="mission-stack">
      <Panel title="Crew member">
        <div className="health-profile">
          <label className="data-label">Select astronaut
            <select value={selected.crew_id} onChange={(event) => setParams({ crew: event.target.value }, { replace: true })}>
              {items.map((crew) => <option key={crew.crew_id} value={crew.crew_id}>{crew.display_name}</option>)}
            </select>
          </label>
          <Resource<CrewProfile> url={'/api/crew/' + id}>{(profile) => <div>
            <h3>{profile.display_name}</h3>
            <p>{profile.role} · {profile.age_years} years old · {label(profile.activity_pref)} exercise preference</p>
          </div>}</Resource>
        </div>
      </Panel>
      <Resource<Latest> url={'/api/observations/latest?crew_id=' + id}>{(latest) => <>
        <PrimaryReadings latest={latest} />
        <MeasurementHistory crew={selected.crew_id} latest={latest} metric={metric} days={days}
          setMetric={setMetric} setDays={setDays} />
        <OtherReadings latest={latest} select={setMetric} />
      </>}</Resource>
    </div>
  }}</Resource>
}
