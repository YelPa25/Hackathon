import { Camera, Mic, Pause, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { detectorLabel, featureLabel, fixtureTime } from './results'
import type { LiveResultView, Modality } from './results'
import { useResearch } from './state'

export function useCaptureAvailability() {
  const [available, setAvailable] = useState<boolean | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    const check = async () => {
      try {
        const response = await fetch('/research-api/health', {
          headers: { 'X-Astra-Research': 'local-capture' }, cache: 'no-store', signal: controller.signal,
        })
        const payload = response.ok ? await response.json() : null
        if (!controller.signal.aborted) setAvailable(payload?.available === true)
      } catch {
        if (!controller.signal.aborted) setAvailable(false)
      }
    }
    void check()
    const interval = window.setInterval(() => void check(), 5000)
    return () => { controller.abort(); window.clearInterval(interval) }
  }, [])
  return available
}

export function LiveCapture({ modality, available, view, leaveResult }: {
  modality: Modality
  available: boolean | null
  view?: LiveResultView
  leaveResult: () => void
}) {
  const { live, setResult } = useResearch()
  const {
    snapshot, preview, start, pause, selectedFeature, setSelectedFeature,
    saved, saveCalibration, forgetCalibration, storageStatus, saving,
  } = live[modality]
  const [publishedFeature, setPublishedFeature] = useState<{ view: LiveResultView; value: string }>()
  const display = view ?? snapshot
  const desiredFeature = view ? publishedFeature?.view === view ? publishedFeature.value : view.feature : selectedFeature
  useEffect(() => () => pause(), [pause])
  const camera = modality === 'facial'
  const Icon = camera ? Camera : Mic
  const active = snapshot.stage === 'active'
  const pending = snapshot.stage === 'loading' || snapshot.stage === 'permission'
  const paused = snapshot.stage === 'paused'
  const current = display.windows.at(-1)
  const feature = display.features.includes(desiredFeature) ? desiredFeature : display.features[0]
  const points = display.windows.map((sample, index) => ({ index: index + 1, value: sample.features[feature], t: sample.t }))
  const hasReadings = points.some((point) => point.value != null)

  function begin(mode: 'resume' | 'new' | 'saved') {
    leaveResult()
    void start(mode)
  }

  return <div className="research-live" id={modality + '-live'}>
    {view && <p className="research-detail">Result shown on the dashboard</p>}
    <div className="research-actions">
      {!(active || pending) && <>
        {paused && <button className="data-control" type="button" disabled={!available || saving} onClick={() => begin('resume')}>
          <Play size={16} aria-hidden="true" /> Resume capture
        </button>}
        {saved && <button className="data-control" type="button" disabled={!available || saving} onClick={() => begin('saved')}>
          Use saved calibration
        </button>}
        <button className="data-control" type="button" disabled={!available || saving} onClick={() => begin('new')}>
          <Icon size={16} aria-hidden="true" /> {paused || saved ? 'New calibration' : camera ? 'Start camera' : 'Start microphone'}
        </button>
      </>}
      {(active || pending) && <button className="data-control" type="button" onClick={pause}>
        <Pause size={15} aria-hidden="true" /> {pending ? 'Cancel capture' : 'Pause capture'}
      </button>}
    </div>
    {!(active || pending) && (saved || (paused && snapshot.windows.at(-1)?.baseline.ready)) &&
      <div className="research-calibration-options">
        <p className="research-detail">Saved calibration stays in this browser. Use it only with the same person and device.</p>
        <div className="research-actions">
          {paused && snapshot.windows.at(-1)?.baseline.ready && <button className="data-control" type="button"
            onClick={() => void saveCalibration()} disabled={!available || saving}>
            {saving ? 'Saving…' : saved ? 'Replace saved calibration' : 'Save my calibration'}
          </button>}
          {saved && <button className="data-control" type="button" onClick={forgetCalibration} disabled={saving}>
            Remove saved calibration
          </button>}
        </div>
      </div>}
    {storageStatus && <p className="research-detail" role="status">{storageStatus}</p>}
    <p className={active ? 'research-state' : 'research-detail'} role="status">
      {snapshot.stage === 'idle' && available !== true
        ? available === null ? 'Checking local capture service…' : 'Live capture unavailable. Start the local research service to enable it.'
        : snapshot.detail}
    </p>
    {camera && <video ref={preview} className="research-preview" hidden={!active} muted playsInline aria-label="Local camera preview" />}
    {active && !current && <p className="research-detail">
      {camera ? 'Keep your face in frame. The first feature window takes about 10 seconds.' : 'The first speech window takes about 15 seconds plus processing time.'}
    </p>}
    {current && <div className="research-readout">
      <p className="research-state" data-tone={current.state === 'invalid' ? 'warn' : undefined}>
        {current.state === 'calibrating' && current.baseline.ready ? 'Calibration complete' : detectorLabel[current.state]}
      </p>
      {current.state === 'invalid' && <p className="research-detail">
        {current.baseline.ready ? 'Calibration is complete. ' : ''}
        The latest sample had too little usable signal to score.
        {active && (camera ? ' Keep your face in frame with steady lighting.' : ' Speak clearly near the microphone in a quiet room.')}
      </p>}
      {current.state === 'calibrating' && current.baseline.ready && <p className="research-detail">
        The next usable sample can be scored.
      </p>}
      <div className="research-calibration">
        <label htmlFor={modality + '-live-calibration'}>
          Calibration · {current.baseline.n}/{display.target} valid windows
        </label>
        <progress id={modality + '-live-calibration'} max={display.target} value={current.baseline.n} />
      </div>
      <dl className="research-values">
        <div><dt>Signal quality</dt><dd>{Math.round(current.quality * 100)}%</dd></div>
        <div><dt>Deviation score</dt><dd>{current.score === null ? 'Unavailable' : current.score.toFixed(2)}</dd></div>
        <div><dt>Collected at</dt><dd><time dateTime={current.t}>{fixtureTime.format(new Date(current.t))} UTC</time></dd></div>
      </dl>
      {feature && <div className="research-series">
        <label className="data-label research-trend">Feature trend
          <select value={feature} onChange={(event) => view
            ? setPublishedFeature({ view, value: event.target.value })
            : setSelectedFeature(event.target.value)}>
            {display.features.map((key) => <option key={key} value={key}>{featureLabel(key)}</option>)}
          </select>
        </label>
        {hasReadings ? <div className="research-chart" role="img"
          aria-label={featureLabel(feature) + ' by recent capture window. Missing values appear as gaps.'}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <LineChart data={points} margin={{ left: 0, right: 12, top: 12, bottom: 4 }}>
              <XAxis dataKey="index" minTickGap={24} tick={{ fill: 'var(--color-muted)', fontSize: 11 }} />
              <YAxis width={42} tick={{ fill: 'var(--color-muted)', fontSize: 11 }} domain={['auto', 'auto']} />
              <Tooltip allowEscapeViewBox={{ x: false, y: false }}
                labelFormatter={(_, items) => items[0] ? fixtureTime.format(new Date(items[0].payload.t)) + ' UTC' : ''}
                contentStyle={{ background: '#102033', borderColor: '#2b435b' }} formatter={(value) => [value, featureLabel(feature)]} />
              <Line dataKey="value" stroke="var(--color-cyan)" strokeWidth={2} dot={points.length === 1} connectNulls={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div> : <p className="research-detail">Usable samples will appear here.</p>}
        {hasReadings && <p className="research-detail">
          Latest feature value · {current.features[feature] ?? 'Unavailable for this sample'}
        </p>}
      </div>}
      {(current.state === 'watch' || current.state === 'alert') && current.contributors.length > 0 && <div className="research-contributors">
        <h3>Contributing features</h3>
        <ul>{current.contributors.map((item) => <li key={item.feature}>
          {featureLabel(item.feature)} · {item.direction === 'up' ? 'Above' : 'Below'} calibration baseline
        </li>)}</ul>
      </div>}
      {!view && !active && !pending && current.score !== null && <button type="button" className="data-control"
        onClick={() => setResult({
          modality, window: current, source: 'Live local capture', subject: 'Local participant',
          view: { kind: 'live', windows: display.windows, features: display.features, target: display.target, feature },
        })}>
        Show result on dashboards
      </button>}
    </div>}
  </div>
}
