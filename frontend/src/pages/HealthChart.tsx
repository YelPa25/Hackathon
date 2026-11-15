import {
  Bar, CartesianGrid, ComposedChart, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import type { Observation } from '../services/mission'
import type { Baseline, Comparison } from '../services/health-analysis'
import { capitalize, formatExactUtc, label, metricLabel, unit } from './mission-display'

export type Series = { metric: string; name: string; color: string; dashed?: boolean }
export type HistoryWindow = { from: string; to: string }

type Point = { timestamp: number; readings: Record<string, Observation>; values: Record<string, number | null> }

const formatDay = new Intl.DateTimeFormat('en-GB', { month: 'short', day: 'numeric', timeZone: 'UTC' })
const formatTick = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 })
const chartMargin = { top: 12, right: 16, bottom: 5, left: 2 }

function ChartDetails({ active, label: timestamp, points, series }: TooltipContentProps & {
  points: Map<number, Point>; series: Series[]
}) {
  const point = active ? points.get(Number(timestamp)) : undefined
  if (!point) return null
  return <div className="health-tooltip" role="status" aria-live="polite">
    <strong>{formatExactUtc(new Date(point.timestamp).toISOString())}</strong>
    <ul>{series.map(({ metric, name }) => {
      const reading = point.readings[metric]
      if (!reading) return null
      return <li key={metric}>
        <span>{name}: {reading.value === null ? 'Missing reading' : reading.value + ' ' + unit(reading.unit)}</span>
        <small>{capitalize(label(reading.activity_context))}{reading.missing_reason
          ? ' · ' + capitalize(label(reading.missing_reason.toLowerCase())) : ''}</small>
      </li>
    })}</ul>
  </div>
}

export function HealthChart({ records, series, window, title, baselines, indicators }: {
  records: Observation[]; series: Series[]; window: HistoryWindow; title: string
  baselines?: Baseline[]; indicators?: Comparison[]
}) {
  const points = new Map<number, Point>()
  for (const reading of records) {
    const timestamp = Date.parse(reading.timestamp_utc)
    const point = points.get(timestamp) ?? { timestamp, readings: {}, values: {} }
    point.readings[reading.metric] = reading
    point.values[reading.metric] = reading.value
    points.set(timestamp, point)
  }

  const arranged = [...points.values()]
  const firstValid = records.find((row) => row.value !== null)
  const gaps = arranged.filter((point) => Object.values(point.readings).some((row) => row.value === null))
  if (!firstValid) return <p>No usable measurements in this range. Missing records are listed below.</p>

  const discrete = firstValid.unit === 'score_0_4'
  const bar = firstValid.metric === 'sleep_duration' || firstValid.metric === 'exercise_duration'
  const references = series.flatMap((item) => {
    const ref = baselines?.find((candidate) => candidate.metric === item.metric && candidate.kind === 'continuous')
    return ref?.median != null ? [{ ...item, median: ref.median }] : []
  })
  const unusualIds = new Set(indicators?.flatMap((item) => item.unusual_ids))
  const unusual = records.filter((row) => row.value !== null && unusualIds.has(row.observation_id))
  const measureUnit = discrete ? 'Score (0–4)' : unit(firstValid.unit)
  return <figure className="health-figure" aria-label={title + ' history'}>
    <figcaption className="health-chart-key">
      <span>{measureUnit} · UTC</span>
      {series.length > 1 && <ul aria-label="Chart series">
        {series.map((item) => <li key={item.metric}>
          <span className="health-series-line" data-dashed={item.dashed} style={{ color: item.color }} aria-hidden="true" />
          {item.name}
        </li>)}
      </ul>}
    </figcaption>
    <div className="health-chart">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <ComposedChart data={arranged} margin={chartMargin} accessibilityLayer title={title + ' observations over time in UTC'}>
          <CartesianGrid stroke="var(--color-line)" vertical={false} strokeDasharray="3 5" />
          <XAxis dataKey="timestamp" type="number" scale="utc" domain={[Date.parse(window.from), Date.parse(window.to)]}
            allowDataOverflow tickFormatter={(stamp) => formatDay.format(stamp)} tick={{ fill: 'var(--color-muted)', fontSize: 11 }}
            tickLine={false} axisLine={{ stroke: 'var(--color-line)' }} minTickGap={24} tickCount={6} tickMargin={9} />
          <YAxis type="number" width={43} domain={discrete ? [-0.15, 4.15] : bar ? [0, 'auto'] : ['auto', 'auto']}
            ticks={discrete ? [0, 1, 2, 3, 4] : undefined} tickCount={5}
            tickFormatter={(value) => formatTick.format(value)} tick={{ fill: 'var(--color-muted)', fontSize: 11 }}
            axisLine={false} tickLine={false} tickMargin={6} />
          <Tooltip content={(props) => <ChartDetails {...props} points={points} series={series} />}
            cursor={{ stroke: 'var(--color-muted)', strokeDasharray: '3 5' }} filterNull={false} isAnimationActive={false} />
          {gaps.map((point) => <ReferenceLine key={point.timestamp} x={point.timestamp}
            stroke="var(--health-missing)" strokeDasharray="3 5" strokeOpacity={0.72} />)}
          {series.map(({ metric, name, color, dashed }) => bar
            ? <Bar key={metric} name={name} dataKey={'values.' + metric} fill={color} maxBarSize={24}
                radius={[3, 3, 0, 0]} isAnimationActive={false} />
            : <Line key={metric} name={name} dataKey={'values.' + metric} type="linear"
                stroke={discrete ? 'none' : color} strokeDasharray={dashed ? '6 4' : undefined} strokeWidth={2}
                dot={{ r: discrete ? 4 : 2.5, fill: color, stroke: discrete ? color : 'var(--color-panel)', strokeWidth: 1 }}
                activeDot={{ r: 5, fill: color, stroke: 'var(--color-panel)' }}
                connectNulls={false} isAnimationActive={false} />)}
          {references.map(({ metric, median, color }) => <ReferenceLine key={metric} y={median} stroke={color}
            strokeDasharray="3 5" strokeOpacity={0.7} ifOverflow="extendDomain" />)}
          {unusual.map((reading) => <ReferenceDot key={reading.observation_id} x={Date.parse(reading.timestamp_utc)}
            y={reading.value!} r={4.5} fill="var(--color-panel)" stroke="var(--health-missing)" strokeWidth={2} />)}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
    {(references.length > 0 || unusual.length > 0) && <p className="health-chart-caption">
      {references.length > 0 && <><span className="health-chart-reference" aria-hidden="true" />Personal reference: {references.map(({ name, median }) => name + ' ' + median + ' ' + measureUnit).join(' · ')}</>}
      {unusual.length > 0 && <><span className="health-chart-unusual" aria-hidden="true" />Strong statistical deviation</>}
    </p>}
    {(discrete || gaps.length > 0) && <p className="health-chart-caption">
      {discrete && 'Each point is one recorded score. '}
      {gaps.length > 0 && <><span className="health-gap-key" aria-hidden="true" />Dashed amber markers indicate missing readings.</>}
    </p>}
  </figure>
}

export function HistoryRecords({ records, open, onOpenChange }: {
  records: Observation[]; open: boolean; onOpenChange: (open: boolean) => void
}) {
  return <details className="health-details health-records" open={open}>
    <summary onClick={(event) => {
      // Only user activation changes the preference; remounts can emit native toggle events.
      event.preventDefault()
      onOpenChange(!open)
    }} onKeyDown={(event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return
      event.preventDefault()
      if (!event.repeat) onOpenChange(!open)
    }}>Detailed records <span>{records.length} observations</span></summary>
    <div className="observation-scroll" role="region" aria-label="Historical readings" tabIndex={0}>
      <table className="observation-table">
        <caption className="sr-only">Exact stored observations, newest first</caption>
        <thead><tr>
          <th scope="col">Observed at (UTC)</th><th scope="col">Metric</th><th scope="col">Reading</th>
          <th scope="col">Context</th><th scope="col">Source</th>
        </tr></thead>
        <tbody>{records.slice().reverse().map((reading) => <tr key={reading.observation_id}>
          <td><time dateTime={reading.timestamp_utc}>{formatExactUtc(reading.timestamp_utc).replace(/ UTC$/, '')}</time></td>
          <td>{metricLabel(reading.metric)}</td>
          <td>{reading.value === null
            ? <span data-tone="warn">Missing{reading.missing_reason ? ' · ' + label(reading.missing_reason.toLowerCase()) : ''}</span>
            : reading.value + ' ' + unit(reading.unit)}</td>
          <td>{capitalize(label(reading.activity_context))}</td>
          <td>{capitalize(label(reading.source))} · {capitalize(reading.provenance.toLowerCase())}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </details>
}
