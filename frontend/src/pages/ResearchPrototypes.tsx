import { AudioLines, Camera, Play, Square } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import demo from '../research/fixtures/detector-demo.json'
import { detectorLabel, featureLabel, fixtureTime, modalityTitle } from '../research/results'
import type { Modality, ResearchDemo, ResultView, SampleView, Scenario } from '../research/results'
import { useResearch } from '../research/state'
import { LiveCapture, useCaptureAvailability } from '../research/LiveCapture'
import '../styles/research.css'

const fixture: ResearchDemo = demo as ResearchDemo

function MonitoringPanel({ modality, available, view, leaveResult }: {
  modality: Modality
  available: boolean | null
  view?: ResultView
  leaveResult: () => void
}) {
  const { setResult, samples, setSample } = useResearch()
  const pinnedSample = view?.kind === 'sample' ? view : undefined
  const sample = pinnedSample ?? samples[modality]
  const { scenario, step, open } = sample
  function editSample(update: Partial<SampleView>) {
    setSample(modality, { ...sample, ...update })
    if (pinnedSample) leaveResult()
  }
  const [running, setRunning] = useState(false)
  const Icon = modality === 'facial' ? Camera : AudioLines
  const source = fixture.modalities[modality]
  const windows = source.scenarios[scenario]
  const current = windows[step]
  const feature = sample.feature || Object.keys(windows[0].features)[0]
  const finished = step === windows.length - 1
  const active = running && !finished && !pinnedSample
  const subject = modality === 'facial' ? 'Facial demo session' : 'Voice demo session'

  useEffect(() => {
    if (!active) return
    const timer = window.setTimeout(() => setSample(modality, { step: step + 1 }), 220)
    return () => window.clearTimeout(timer)
  }, [active, modality, setSample, step])

  const points = windows.slice(0, step + 1).map((sample, index) => ({
    window: index + 1, value: sample.features[feature],
  }))

  return <section className="surface data-panel research-panel" aria-labelledby={modality + '-title'}>
    <header className="panel-heading">
      <span className="panel-symbol"><Icon size={20} aria-hidden="true" /></span>
      <h2 id={modality + '-title'}>{modalityTitle[modality]}</h2>
    </header>
    <p>{modality === 'facial' ? 'Explore changes in facial movement features.' : 'Explore changes in speech timing and acoustic features.'}</p>
    <LiveCapture modality={modality} available={available} view={view?.kind === 'live' ? view : undefined} leaveResult={leaveResult} />
    <details id={modality + '-sample'} className="research-sample" open={open} onToggle={(event) => {
      if (event.currentTarget.open !== open) editSample({ open: event.currentTarget.open })
    }}>
      <summary>Last saved sample</summary>
    <div className="research-controls">
      <label className="data-label">Demo input
        <select disabled={active} value={scenario} onChange={(event) => {
          setRunning(false)
          editSample({ step: -1, scenario: event.target.value as Scenario, open: true })
        }}>
          <option value="fatigue_ramp">Gradual feature shift</option>
          <option value="sensor_dropout">Signal dropout</option>
        </select>
      </label>
      <div className="research-actions">
        <button type="button" className="data-control" disabled={active} onClick={() => {
          editSample({ step: step < 0 || finished ? 0 : step, open: true })
          setRunning(true)
        }}><Play size={15} aria-hidden="true" /> {step < 0 ? 'Play sample' : finished ? 'Replay sample' : 'Resume sample'}</button>
        <button type="button" className="data-control" disabled={!active} onClick={() => setRunning(false)}>
          <Square size={15} aria-hidden="true" /> Stop
        </button>
      </div>
    </div>
    <div className="research-readout">
      <p className="research-state" role="status">{active || finished ? 'Last saved sample' : current ? 'Stopped' : 'Ready'}</p>
      <p>{current ? detectorLabel[current.state] : 'Play a sample to see calibration and detector results.'}</p>
      {current && <>
        <div className="research-calibration">
          <label htmlFor={modality + '-calibration'}>Calibration · {current.baseline.n}/{source.target} valid windows</label>
          <progress id={modality + '-calibration'} max={source.target} value={current.baseline.n} />
        </div>
        <dl className="research-values">
          <div><dt>Signal quality</dt><dd>{Math.round(current.quality * 100)}%</dd></div>
          <div><dt>Deviation score</dt><dd>{current.score === null ? 'Unavailable' : current.score.toFixed(2)}</dd></div>
          <div><dt>Sample time</dt><dd><time dateTime={current.t}>{fixtureTime.format(new Date(current.t))} UTC</time></dd></div>
        </dl>
        <div className="research-series">
          <label className="data-label">Feature trend
            <select value={feature} onChange={(event) => editSample({ feature: event.target.value })}>
              {Object.keys(current.features).map((key) => <option key={key} value={key}>{featureLabel(key)}</option>)}
            </select>
          </label>
          <div className="research-chart" role="img" aria-label={featureLabel(feature) + ' by sample window. Missing values appear as gaps.'}>
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <LineChart data={points} margin={{ left: 0, right: 12, top: 12, bottom: 4 }}>
                <XAxis dataKey="window" tick={{ fill: 'var(--color-muted)', fontSize: 11 }} tickCount={5} />
                <YAxis width={42} tick={{ fill: 'var(--color-muted)', fontSize: 11 }} domain={['auto', 'auto']} />
                <Tooltip labelFormatter={(value) => 'Window ' + value} contentStyle={{ background: '#102033', borderColor: '#2b435b' }}
                  formatter={(value) => [value, featureLabel(feature)]} />
                <Line dataKey="value" stroke="var(--color-cyan)" strokeWidth={2} dot={points.length === 1}
                  connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <p className="research-detail">Window {step + 1} of {windows.length} · {current.features[feature] ?? 'Current value unavailable'}</p>
        {current.contributors.length > 0 && (current.state === 'watch' || current.state === 'alert') && <div className="research-contributors">
          <h3>Contributing features</h3>
          <ul>{current.contributors.map((item) => <li key={item.feature}>
            {featureLabel(item.feature)} · {item.direction === 'up' ? 'Above' : 'Below'} calibration baseline ({Math.abs(item.z).toFixed(1)} robust z)
          </li>)}</ul>
        </div>}
        <button type="button" className="data-control" disabled={active || current.state === 'calibrating' || current.state === 'invalid'}
          onClick={() => setResult({ modality, window: current, source: fixture.source, subject,
            view: { ...sample, kind: 'sample', feature, open: true },
          })}>
          Show result on dashboards
        </button>
      </>}
    </div>
    </details>
  </section>
}

export default function ResearchPrototypes() {
  const available = useCaptureAvailability()
  const { result, setResult } = useResearch()
  const [params, setParams] = useSearchParams()
  const published = params.get('result') === '1' ? result : null
  const anchor = published ? published.modality + '-' + published.view.kind : null

  useEffect(() => {
    if (!anchor) return
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(anchor)?.scrollIntoView({ block: 'start' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [anchor])

  function leaveResult() {
    if (params.has('result')) setParams({}, { replace: true })
  }

  return <div className="mission-stack">
    <div className="research-intro">
      <div>
        <strong>Experimental feature monitoring</strong>
        <p>Choose a device for a local session or play a synthetic sample. Capture starts only when you ask.</p>
      </div>
      {result && <div>
        <p role="status">Dashboard result: {modalityTitle[result.modality]}.</p>
        <button className="data-control" type="button" onClick={() => setResult(null)}>Remove dashboard result</button>
      </div>}
    </div>
    <div className="research-grid">
      <MonitoringPanel modality="facial" available={available} view={published?.modality === 'facial' ? published.view : undefined} leaveResult={leaveResult} />
      <MonitoringPanel modality="speech" available={available} view={published?.modality === 'speech' ? published.view : undefined} leaveResult={leaveResult} />
    </div>
  </div>
}
