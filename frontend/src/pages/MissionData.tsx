import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { Dataset, Mission, Observation, Replay } from '../services/mission'
import { capitalize, formatUtc, label, metricLabel, Panel, Resource, unit } from './mission-display'

function ReadingValue({ reading }: { reading: Observation }) {
  return reading.quality === 'MISSING'
    ? <span data-tone="warn">Missing<span className="sr-only"> ({label(reading.missing_reason ?? 'reason unavailable')})</span></span>
    : <>{reading.value} <small>{unit(reading.unit)}</small></>
}

function ReadingCards({ items }: { items: Observation[] }) {
  if (!items.length) return <p>No readings in this period.</p>
  return <dl className="reading-grid">{items.map((reading) => {
    return <div className="reading-tile" key={reading.metric}>
      <dt>{metricLabel(reading.metric)}</dt>
      <dd className="reading-value"><ReadingValue reading={reading} /></dd>
      <dd><time dateTime={reading.timestamp_utc}>{formatUtc(reading.timestamp_utc)}</time></dd>
      <dd>{capitalize(label(reading.activity_context))} · {capitalize(label(reading.source))}</dd>
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
