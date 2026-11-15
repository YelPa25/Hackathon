import { Link } from 'react-router'
import type { CrewAnalysis, Finding, MonitoringStatus } from '../services/health-analysis'
import { formatExactUtc, metricLabel, Panel, unit } from './mission-display'

const statusLabel: Record<MonitoringStatus, string> = {
  STABLE: 'Stable', WATCH: 'Watch', FLAGGED: 'Flagged', INSUFFICIENT_DATA: 'Insufficient data',
}

export function MonitoringBadge({ status }: { status: MonitoringStatus }) {
  return <span className="monitoring-badge" data-monitoring={status}>
    <span className="status-dot" aria-hidden="true" />{statusLabel[status]}
  </span>
}

export function FindingCard({ finding, crewName, method }: { finding: Finding; crewName?: string; method?: string }) {
  return <article className="native-finding">
    <div className="native-finding-heading">
      <h3>{finding.title}</h3><MonitoringBadge status={finding.status} />
    </div>
    {crewName && <p className="native-note">{crewName}</p>}
    <p>{finding.explanation}</p>
    <p><strong>To verify:</strong> {finding.verification}</p>
    <details className="native-details">
      <summary>Evidence and limitations</summary>
      <p>{finding.uncertainty}</p>
      {finding.evidence.length > 0 && <ul>{finding.evidence.map((reading) => <li key={reading.observation_id}>
        {metricLabel(reading.metric)} · {reading.value === null ? 'Missing' : reading.value + ' ' + unit(reading.unit)}
        {' · '}<time dateTime={reading.timestamp_utc}>{formatExactUtc(reading.timestamp_utc)}</time>
      </li>)}</ul>}
      {finding.habitat_comparison && <p className="native-note">
        {finding.habitat_comparison.valid_hours} valid hourly slots · Modified Z {finding.habitat_comparison.modified_z.toFixed(2)}
      </p>}
      <p className="native-note">{finding.rule_id}{method ? ' · ' + method : ''} · Synthetic</p>
    </details>
    {crewName && finding.crew_id && <Link className="native-link" to={'/crew-health?' + new URLSearchParams({ crew: finding.crew_id }) + '#personal-findings'}>
      Open Crew Health
    </Link>}
  </article>
}

export function PersonalFindings({ analysis, state }: {
  analysis?: CrewAnalysis; state: 'loading' | 'ready' | 'error'
}) {
  return <div id="personal-findings"><Panel title="Personal findings">
    {!analysis ? <p role="status">{state === 'error'
      ? 'Statistical analysis is unavailable. Stored readings and history are still available.'
      : 'Loading analysis for these readings…'}</p> : <>
      <div className="native-finding-heading">
        <MonitoringBadge status={analysis.status} />
        <p className="native-note">{analysis.coverage.current_groups} of {analysis.coverage.total_groups} primary indicator groups support a current comparison · Synthetic</p>
      </div>
      {analysis.status === 'STABLE' && <p>No detected deviation in monitored indicators.</p>}
      {analysis.findings.length > 0 && <div className="native-findings-list">{analysis.findings.map((finding) =>
        <FindingCard key={finding.rule_id + finding.title} finding={finding} method={analysis.method_version} />
      )}</div>}
    </>}
  </Panel></div>
}
