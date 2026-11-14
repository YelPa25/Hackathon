import type { ReactNode } from 'react'
import { ResearchSummary } from '../research/ResearchSummary'
import { Link } from 'react-router'
import type { Dataset, Mission, Observation } from '../services/mission'
import { capitalize, formatUtc, label, metricLabel, Panel, Resource, unit } from './mission-display'

export { MissionReplay } from './MissionReplay'

function ReadingValue({ reading }: { reading: Observation }) {
  return reading.quality === 'MISSING'
    ? <span data-tone="warn">Missing<span className="sr-only"> ({label(reading.missing_reason ?? 'reason unavailable')})</span></span>
    : <>{reading.value} <small>{unit(reading.unit)}</small></>
}

function ReadingCards({ items, missing }: { items: Observation[]; missing: Observation[] }) {
  if (!items.length) return <p>No readings in this period.</p>
  return <dl className="reading-grid">{items.map((reading) => {
    return <div className="reading-tile" key={reading.metric}>
      <dt>{metricLabel(reading.metric)}</dt>
      <dd className="reading-value"><ReadingValue reading={reading} /></dd>
      <dd><time dateTime={reading.timestamp_utc}>{formatUtc(reading.timestamp_utc)}</time></dd>
      <dd>{capitalize(label(reading.activity_context))} · {capitalize(label(reading.source))}</dd>
      {missing.some((sample) => sample.metric === reading.metric) && <dd data-tone="warn">Newer sample missing</dd>}
    </div>
  })}</dl>
}

export function MissionOverview({ readiness }: { readiness: ReactNode }) {
  return <Resource<Mission> url="/api/mission" live>{(mission) => <div className="mission-stack">
    <div className="overview-grid">
      <Panel title="Fictional 90-day transit">
        <p className="mission-day">Day {mission.mission_day}</p>
        <p><time dateTime={mission.cursor_utc}>{formatUtc(mission.cursor_utc)}</time></p>
        <p>{mission.replay_status === 'COMPLETE' ? 'Replay complete' : 'Observations available through the published mission time'} · Synthetic</p>
      </Panel>
      {readiness}
    </div>
    <ResearchSummary />
    <Panel title="Crew">
      <ul className="reading-grid">{mission.crew_summaries.map((crew) => <li key={crew.crew_id}>
        <Link className="reading-tile crew-link" to={'/crew-health?' + new URLSearchParams({ crew: crew.crew_id })}>
          <strong>{crew.display_name}</strong><span>{crew.role}</span>
          <span>{mission.crew_readings[crew.crew_id] ? <>
            {metricLabel(mission.crew_readings[crew.crew_id].metric)} · <ReadingValue reading={mission.crew_readings[crew.crew_id]} />
          </> : 'Reading unavailable'}</span>
          {mission.crew_readings[crew.crew_id] && <span>{formatUtc(mission.crew_readings[crew.crew_id].timestamp_utc)}</span>}
        </Link>
      </li>)}</ul>
    </Panel>
    <Panel title="Latest valid cabin readings">
      <ReadingCards items={mission.cabin_readings} missing={mission.cabin_latest_missing} />
      <p className="dataset-note">CO₂ concentration in ppm is derived from an assumed cabin pressure of 760 mmHg. Partial pressure is the primary CO₂ reading.</p>
    </Panel>
  </div>}</Resource>
}

export function DataScience() {
  return <Resource<Dataset> url="/api/data" live>{(dataset) => <div className="mission-stack">
    <Panel title="Synthetic mission dataset">
      <p className="profile-summary"><strong>{dataset.dataset_id} · v{dataset.version}</strong></p>
      <p>Research-informed synthetic observations for a fictional crew. NASA and CDC publications informed the dataset design. It contains no actual astronaut health records.</p>
      <dl className="replay-facts">
        <div><dt>Mission duration</dt><dd>{dataset.mission_days} days</dd></div>
        <div><dt>Published history</dt><dd>Days 1–{dataset.historical_days}</dd></div>
        <div><dt>Revealed observations</dt><dd>{dataset.replay.visible_count.toLocaleString()}</dd></div>
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
