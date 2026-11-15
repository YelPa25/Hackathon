import { Activity, BedDouble, Droplets, HeartPulse, Thermometer, Zap } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router'
import { ResearchSummary } from '../research/ResearchSummary'
import { fetchObservationHistory, useMissionData } from '../services/mission'
import { useReplay } from '../services/replay-state'
import type { CrewAnalysis } from '../services/health-analysis'
import { MonitoringBadge, PersonalFindings } from './HealthFindings'
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

function PrimaryReadings({ latest, analysis }: { latest: Latest; analysis?: CrewAnalysis }) {
  return <Panel title="Health overview">
    <p className="health-section-note">Latest valid readings · Synthetic</p>
    <div className="primary-health-grid">{primary.map(({ title, metrics, icon: Icon }) => {
      const entries = metrics.map((metric) => ({
        metric,
        reading: latest.items.find((item) => item.metric === metric),
        missing: latest.latest_missing.find((item) => item.metric === metric),
        indicator: analysis?.indicators.find((item) => item.metric === metric),
        reference: analysis?.baselines.find((item) => item.metric === metric),
      }))
      const valid = entries.flatMap(({ reading }) => reading ? [reading] : [])
      const gaps = entries.flatMap(({ missing }) => missing ? [missing] : [])
      const isPressure = metrics === pressureMetrics
      const paired = valid.length === 2 && valid[0].timestamp_utc === valid[1].timestamp_utc
        && valid[0].source === valid[1].source && valid[0].activity_context === valid[1].activity_context
      const statuses = entries.map((entry) => entry.indicator?.status)
      const statistical = statuses.includes('FLAGGED') ? 'FLAGGED' : statuses.includes('WATCH') ? 'WATCH'
        : statuses.every((status) => status === 'STABLE') && (!isPressure || paired) ? 'STABLE'
        : analysis ? 'INSUFFICIENT_DATA' : undefined
      let status = readingStatus(valid[0], gaps[0])
      if (gaps.length) status = { text: valid.length ? 'Newer sample missing' : 'Missing', tone: 'warn' }
      else if (isPressure && valid.length && !paired) status = { text: 'No paired reading', tone: 'warn' }
      else if (entries.some(({ indicator }) => indicator?.availability === 'STALE')) status = { text: 'Older reading', tone: 'warn' }
      else if (valid.length && entries.every(({ indicator }) => indicator?.availability === 'CURRENT')) status = { text: 'Current', tone: 'good' }
      return <section className="health-metric" key={title} aria-label={title}>
        <h3><Icon size={17} aria-hidden="true" />{title}</h3>
        {isPressure && !paired && valid.length ? <div className="pressure-components">{entries.map(({ metric, reading }) =>
          <p key={metric}>{metric === 'systolic_bp' ? 'Systolic' : 'Diastolic'}: {reading ? describeReading(reading) : 'Unavailable'}</p>
        )}</div> : <p className="health-metric-value">
          <strong>{valid.length ? valid.map(({ value }) => value).join(' / ') : '—'}</strong>
          {valid[0] && <span>{unit(valid[0].unit)}</span>}
        </p>}
        {isPressure && paired && <p className="health-pressure-label">Systolic / Diastolic · Same session</p>}
        <p className="health-reading-status" data-tone={status.tone}><span className="status-dot" aria-hidden="true" />{status.text}</p>
        {entries.map(({ metric, reference, indicator }) => reference && <p className="health-reference" key={metric}>
          {isPressure && (metric === 'systolic_bp' ? 'Systolic' : 'Diastolic') + ' · '}
          {reference.median === null ? 'Reference unavailable' : <>Reference {reference.median} {unit(reference.unit)}
            {indicator?.difference != null && <> · {indicator.difference > 0 ? '+' : ''}{Number(indicator.difference.toFixed(2))} {unit(reference.unit)}</>}</>}
        </p>)}
        {statistical && <MonitoringBadge status={statistical} />}
        <ReadingDetails title={title} records={[...valid, ...gaps]} />
        {analysis && <details className="health-details reading-details">
          <summary>Statistical details</summary>
          {entries.map(({ metric, reference, indicator }) => reference && <p key={metric}>
            {metricLabel(metric)} · {reference.distinct_days} reference days ({reference.valid_sample_count} samples)
            {reference.mad !== null && ' · MAD ' + Number(reference.mad.toFixed(3)) + ' · Effective MAD ' + Number(reference.effective_mad?.toFixed(3))}
            {indicator?.modified_z != null && ' · Modified Z ' + indicator.modified_z.toFixed(2)}
            {indicator?.slope_per_day != null && ' · Trend ' + indicator.slope_per_day.toFixed(2) + ' ' + unit(reference.unit) + '/day'}
            {indicator?.rolling_median != null && ' · Recent median ' + indicator.rolling_median + ' ' + unit(reference.unit)}
            {indicator?.age_hours != null && ' · Latest valid reading ' + Math.floor(indicator.age_hours) + ' h old'}
          </p>)}
        </details>}
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

function MeasurementHistory({ crew, latest, analysis, metric, days, setMetric, setDays, recordsOpen, setRecordsOpen }: {
  crew: string; latest: Latest; analysis?: CrewAnalysis; metric: string; days: HistoryDays
  setMetric: (metric: string) => void; setDays: (days: HistoryDays) => void
  recordsOpen: boolean; setRecordsOpen: (open: boolean) => void
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
        <HealthChart records={records} series={series} window={window} title={title} baselines={analysis?.baselines} indicators={analysis?.indicators} />
        <HistoryRecords records={records} open={recordsOpen} onOpenChange={setRecordsOpen} />
      </> : <p className="health-chart-empty">No recorded measurements in this range. Select a longer range to look further back.</p>
    }</Resource>
  </section>
}

function AnalyzedReadings({ crew, latest, children }: {
  crew: string; latest: Latest; children: (analysis?: CrewAnalysis) => ReactNode
}) {
  const { state } = useReplay()
  const result = useMissionData<CrewAnalysis>('/api/crew/' + encodeURIComponent(crew) + '/analysis', 0, undefined, state?.cursor_utc)
  const data = result.state === 'ready' && result.data.cursor_utc === latest.cursor_utc
    && result.data.cursor_utc === state?.cursor_utc ? result.data : undefined
  return <>
    <PrimaryReadings latest={latest} analysis={data} />
    <PersonalFindings analysis={data} state={result.state} />
    {children(data)}
  </>
}

export default function CrewHealth() {
  const [params, setParams] = useSearchParams()
  const [recordsOpen, setRecordsOpen] = useState(false)
  const metric = params.get('metric') ?? 'resting_heart_rate'
  const range = Number(params.get('days'))
  const days = ranges.find((value) => value === range) ?? 45

  function select(key: string, value: string) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      next.set(key, value)
      return next
    }, { replace: true })
  }
  return <Resource<{ items: Crew[] }> url="/api/crew">{({ items }) => {
    const selected = items.find((crew) => crew.crew_id === params.get('crew')) ?? items[0]
    if (!selected) return <p>No crew profiles loaded.</p>
    const id = encodeURIComponent(selected.crew_id)
    return <div className="mission-stack">
      <Panel title="Crew member">
        <div className="health-profile">
          <label className="data-label">Select astronaut
            <select value={selected.crew_id} onChange={(event) => select('crew', event.target.value)}>
              {items.map((crew) => <option key={crew.crew_id} value={crew.crew_id}>{crew.display_name}</option>)}
            </select>
          </label>
          <Resource<CrewProfile> url={'/api/crew/' + id}>{(profile) => <div>
            <h3>{profile.display_name}</h3>
            <p>{profile.role} · {profile.age_years} years old · {label(profile.activity_pref)} exercise preference</p>
          </div>}</Resource>
        </div>
      </Panel>
      <ResearchSummary />
      <Resource<Latest> url={'/api/observations/latest?crew_id=' + id} live>{(latest) => <AnalyzedReadings crew={selected.crew_id} latest={latest}>{(analysis) => <>
        <MeasurementHistory crew={selected.crew_id} latest={latest} analysis={analysis} metric={metric} days={days}
          setMetric={(value) => select('metric', value)} setDays={(value) => select('days', String(value))}
          recordsOpen={recordsOpen} setRecordsOpen={setRecordsOpen} />
        <OtherReadings latest={latest} select={(value) => select('metric', value)} />
      </>}</AnalyzedReadings>}</Resource>
    </div>
  }}</Resource>
}
