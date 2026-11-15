import type { ReactNode } from 'react'
import { ResearchSummary } from '../research/ResearchSummary'
import { Link } from 'react-router'
import { FindingCard, MonitoringBadge } from './HealthFindings'
import type { Mission, Observation } from '../services/mission'
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
          {mission.crew_monitoring?.[crew.crew_id] && <>
            <MonitoringBadge status={mission.crew_monitoring[crew.crew_id].status} />
            <span>{mission.crew_monitoring[crew.crew_id].headline}</span>
            {mission.crew_monitoring[crew.crew_id].status !== 'INSUFFICIENT_DATA' &&
              !mission.crew_monitoring[crew.crew_id].coverage.sufficient && <span>Limited monitoring coverage</span>}
          </>}
        </Link>
      </li>)}</ul>
    </Panel>
    <Panel title="Health intelligence">
      <p className="native-note">Native statistical monitoring · Shareable crew readings · Synthetic</p>
      {!mission.analysis_available ? <p role="status">Statistical analysis is unavailable. Stored readings remain available.</p>
        : !mission.health_findings.length ? <p>No current concerns detected in available shared readings.</p>
        : <div className="native-findings-list">{mission.health_findings.map((finding) =>
          <FindingCard key={finding.crew_id} finding={finding}
            crewName={mission.crew_summaries.find((crew) => crew.crew_id === finding.crew_id)?.display_name}
            method={mission.analysis_method_version ?? undefined} />)}</div>}
    </Panel>
    <Panel title="Latest valid cabin readings">
      <ReadingCards items={mission.cabin_readings} missing={mission.cabin_latest_missing} />
      <p className="dataset-note">CO₂ concentration in ppm is derived from an assumed cabin pressure of 760 mmHg. Partial pressure is the primary CO₂ reading.</p>
      {!!mission.cabin_findings?.length && <div className="native-findings-list">{mission.cabin_findings.map((finding) =>
        <FindingCard key={finding.rule_id + finding.title} finding={finding} method={mission.analysis_method_version ?? undefined} />
      )}</div>}
    </Panel>
  </div>}</Resource>
}
