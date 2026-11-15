import { useEffect, useState } from 'react'
import { fetchMissionData } from '../services/mission'

const minimum = 40
const maximum = 120
const format = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
const position = (bpm: number) => Math.max(0, Math.min(100, (bpm - minimum) / (maximum - minimum) * 100))

const strengths = {
  below_moderate: 'Below the moderate threshold',
  moderate: 'Moderate deviation',
  strong: 'Strong deviation',
}

type Comparison = {
  crew_id: string
  display_name: string
  median_bpm: number | null
  mad_bpm: number | null
  effective_mad_bpm: number | null
  distinct_days: number
  absolute_difference_bpm: number | null
  modified_z: number | null
  strength: keyof typeof strengths | null
}

type ComparisonSet = {
  dataset_id: string
  hypothetical_bpm: number
  method_version: string
  comparisons: Comparison[]
}

function number(value: number | null, unit = '') {
  return value === null ? 'Unavailable' : format.format(value) + unit
}

function ReferenceRail({ median, variability, bpm }: { median: number; variability: number; bpm: number }) {
  const left = position(median - variability)
  const right = position(median + variability)
  return <div className="science-scale" aria-hidden="true">
    <div className="science-scale-track">
      <span className="science-scale-band" style={{ left: left + '%', width: (right - left) + '%' }} />
      <span className="science-scale-reference" style={{ left: position(median) + '%' }} />
      <span className="science-scale-marker" style={{ left: position(bpm) + '%' }} />
    </div>
    <div className="science-scale-labels"><span>40</span><span>60</span><span>80</span><span>100</span><span>120 bpm</span></div>
  </div>
}

function ProfileComparison({ label, selection, others, members, change, bpm, calculated }: {
  label: string
  selection: Comparison
  others: string
  members: Comparison[]
  change: (id: string) => void
  bpm: number
  calculated: boolean
}) {
  return <article className="science-comparison-profile">
    <label className="data-label">{label}
      <select value={selection.crew_id} onChange={(event) => change(event.target.value)}>
        {members.map((member) => <option key={member.crew_id} value={member.crew_id} disabled={member.crew_id === others}>
          {member.display_name}
        </option>)}
      </select>
    </label>
    <div className="science-reference-value">
      <strong>{number(selection.median_bpm, ' bpm')}</strong>
      <span>Personal resting reference</span>
    </div>
    {selection.median_bpm !== null && selection.effective_mad_bpm !== null &&
      <ReferenceRail median={selection.median_bpm} variability={selection.effective_mad_bpm} bpm={bpm} />}
    <dl className="science-profile-values">
      <div><dt>Historical variability (MAD)</dt><dd>{number(selection.mad_bpm, ' bpm')}</dd></div>
      <div><dt>Effective variability</dt><dd>{number(selection.effective_mad_bpm, ' bpm')}</dd></div>
      <div><dt>Valid reference days</dt><dd>{selection.distinct_days}</dd></div>
      <div><dt>Absolute difference</dt><dd>{calculated ? number(selection.absolute_difference_bpm, ' bpm') : 'Updating…'}</dd></div>
      <div><dt>Modified Z-score</dt><dd>{calculated ? number(selection.modified_z) : 'Updating…'}</dd></div>
    </dl>
    <p className="science-comparison-result" data-tone={calculated && (selection.strength === 'strong' || selection.strength === 'moderate') ? 'warn' : 'neutral'}>
      {calculated ? (selection.strength ? strengths[selection.strength] : 'Insufficient reference data') : 'Updating comparison…'}
    </p>
  </article>
}

export function Personalization({ datasetId }: { datasetId: string }) {
  const [bpm, setBpm] = useState(70)
  const [crewA, setCrewA] = useState('')
  const [crewB, setCrewB] = useState('')
  const [result, setResult] = useState<ComparisonSet>()
  const [error, setError] = useState<string>()
  const [retry, setRetry] = useState(0)
  const comparison = result?.dataset_id === datasetId ? result : undefined
  const members = comparison?.comparisons ?? []
  const first = members.find((member) => member.crew_id === crewA) ?? members[0]
  const second = members.find((member) => member.crew_id === crewB) ?? (members[2]?.crew_id !== first?.crew_id ? members[2] : undefined)
    ?? members.find((member) => member.crew_id !== first?.crew_id)
  const calculated = comparison?.hypothetical_bpm === bpm

  useEffect(() => {
    const controller = new AbortController()
    const handle = window.setTimeout(async () => {
      try {
        const response = await fetchMissionData<ComparisonSet>('/api/data/personalization?bpm=' + bpm, controller.signal)
        if (response.dataset_id !== datasetId) throw new Error('The loaded reference is for another dataset.')
        if (!controller.signal.aborted) {
          setResult(response)
          setError(undefined)
        }
      } catch {
        if (!controller.signal.aborted) setError('The baseline comparison is unavailable. Check the ASTRA backend and try again.')
      }
    }, 90)
    return () => { window.clearTimeout(handle); controller.abort() }
  }, [bpm, datasetId, retry])

  return <div className="surface science-comparison">
    <div className="science-slider-control">
      <div><label htmlFor="science-resting-pulse">Hypothetical resting heart rate</label>
        <p id="science-slider-hint">One test value is applied to both synthetic personal references.</p></div>
      <output htmlFor="science-resting-pulse">{bpm} <small>bpm</small></output>
      <input id="science-resting-pulse" type="range" min={minimum} max={maximum} step={1}
        value={bpm} aria-valuetext={bpm + ' beats per minute'} aria-describedby="science-slider-hint"
        onChange={(event) => setBpm(Number(event.currentTarget.value))} />
    </div>
    {error && <div className="science-inline-notice"><p role="alert">{error}</p>
      <button type="button" className="data-control" onClick={() => setRetry((count) => count + 1)}>Retry comparison</button>
    </div>}
    {first && second ? <>
      <div className="science-comparison-grid">
        <ProfileComparison label="Crew member A" selection={first} others={second.crew_id} members={members}
          change={setCrewA} bpm={bpm} calculated={calculated} />
        <ProfileComparison label="Crew member B" selection={second} others={first.crew_id} members={members}
          change={setCrewB} bpm={bpm} calculated={calculated} />
      </div>
      <p className="science-rail-key"><span><i className="science-key-variation" />Median ± effective MAD</span>
        <span><i className="science-key-baseline" />Personal median</span>
        <span><i className="science-key-input" />Hypothetical reading</span></p>
      <p className="science-tiny">The shaded band shows historical variability. The result describes the statistical size of a single hypothetical deviation. It does not assign a crew monitoring state.</p>
    </> : !error && <p className="science-inline-notice" role="status">
      {comparison ? 'Two published crew references are needed for this demonstration.' : 'Loading historical references…'}
    </p>}
  </div>
}
