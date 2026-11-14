import { useState } from 'react'
import type { ReplaySpeed } from '../services/mission'
import { useReplay } from '../services/replay-state'
import { formatExactUtc, Panel } from './mission-display'
import '../styles/replay.css'

export function MissionReplay() {
  const { state, error, pending, offline, send } = useReplay()
  const [confirmReset, setConfirmReset] = useState(false)
  if (!state) return <Panel title="Mission timeline">
    <p role={error ? 'alert' : 'status'}>{error ?? 'Loading the published mission time…'}</p>
  </Panel>

  const running = state.status === 'RUNNING'
  const complete = state.status === 'COMPLETE'
  const atStart = state.mission_day === state.historical_days
  const status = complete ? 'Completed' : running ? 'Playing' : atStart ? 'Ready' : 'Paused'
  const progress = state.mission_day - state.historical_days
  const activity = state.latest_activity
  const disabled = pending || offline
  const remaining = state.mission_days - state.mission_day
  return <div className="mission-stack replay-console">
    <Panel title="Mission timeline">
      <div className="replay-head">
        <div>
          <p className="mission-day">Day {state.mission_day} <small>of {state.mission_days}</small></p>
          <p><time dateTime={state.cursor_utc}>{formatExactUtc(state.cursor_utc)}</time></p>
        </div>
        <span className="replay-status" role="status"><span className="status-dot" aria-hidden="true" />{status}</span>
      </div>
      <progress aria-label="Replay progress" value={progress} max={state.mission_days - state.historical_days} />
      <div className="replay-progress-meta">
        <span>{state.visible_count.toLocaleString()} observations available</span>
        <span>{remaining ? remaining + ' days remaining after today' : 'Final mission day'}</span>
      </div>
      <div className="replay-controls" aria-busy={pending}>
        <div className="replay-buttons">
          {running
            ? <button className="data-control replay-primary" disabled={disabled} onClick={() => void send('PAUSE')}>Pause</button>
            : <button className="data-control replay-primary" disabled={disabled || complete} onClick={() => void send('PLAY')}>
              {atStart ? 'Play' : 'Resume'}
            </button>}
          <button className="data-control" disabled={disabled || running || complete} onClick={() => void send('NEXT_DAY')}>Next Day</button>
          <button className="data-control" disabled={disabled || running || complete} onClick={() => void send('NEXT_EVENT')}>Next Event</button>
          <button className="data-control" disabled={disabled || atStart && !running} onClick={() => setConfirmReset(true)}>Reset Replay</button>
        </div>
        <label className="data-label">Playback speed
          <select value={state.speed} disabled={disabled} onChange={(event) => void send('SET_SPEED', Number(event.target.value) as ReplaySpeed)}>
            <option value={5}>Slow · 5 s per day</option>
            <option value={2}>Normal · 2 s per day</option>
            <option value={0.5}>Fast · 0.5 s per day</option>
          </select>
        </label>
      </div>
      {confirmReset && <div className="replay-reset">
        <p>Return to the end of Day {state.historical_days} and hide the observations revealed since then?</p>
        <button className="data-control" disabled={disabled} onClick={async () => {
          await send('RESET')
          setConfirmReset(false)
        }}>Confirm Reset</button>
        <button className="data-control" onClick={() => setConfirmReset(false)}>Cancel</button>
      </div>}
      {pending && <p role="status">Updating replay…</p>}
      {(error || state.playback_error) && <p className="replay-error" role="alert" data-tone="warn">{error ?? state.playback_error}</p>}
    </Panel>
    <Panel title="Latest replay activity">
      {activity ? <dl className="replay-facts">
        <div><dt>Mission day</dt><dd>{activity.mission_day}</dd></div>
        <div><dt>Revealed observations that day</dt><dd>{activity.observation_count.toLocaleString()}</dd></div>
        <div><dt>Crew records</dt><dd>{activity.crew_count.toLocaleString()}</dd></div>
        <div><dt>Cabin records</dt><dd>{activity.cabin_count.toLocaleString()}</dd></div>
        <div><dt>Recorded time range</dt><dd>{activity.first_utc && activity.last_utc
          ? <>{formatExactUtc(activity.first_utc)} – {formatExactUtc(activity.last_utc)}</>
          : 'No observations in this interval'}</dd></div>
      </dl> : <p>Historical observations are available through Day {state.historical_days}. Play or step to reveal the next recorded observations.</p>}
      <p className="dataset-note">Research-informed synthetic astronaut data.</p>
    </Panel>
  </div>
}
