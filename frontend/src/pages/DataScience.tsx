import { ArrowDown, ArrowRight, ArrowUpRight, Check, ChevronDown, Cpu, Radar, Terminal, Timer } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Dataset, Metric } from '../services/mission'
import { useReplay } from '../services/replay-state'
import { MonitoringBadge } from './HealthFindings'
import { formatExactUtc, label, metricLabel, Resource, unit } from './mission-display'
import { Personalization } from '../science/Personalization'
import { hazards, methodReferences, metricGroups, metricNotes, monitoringStates, nasaHazards, publishedBundle, referenceNotes, sections, stages, verification } from '../science/content'
import '../styles/science.css'

const integer = new Intl.NumberFormat('en-US')
const count = (value: number) => integer.format(value)
const oneDay = 86_400_000

function ScienceSection({ id, title, description, children }: {
  id: string
  title: string
  description?: string
  children: ReactNode
}) {
  return <section id={id} className="science-section" tabIndex={-1} aria-labelledby={id + '-title'}>
    <header className="science-section-heading">
      <h2 id={id + '-title'}>{title}</h2>
      {description && <p>{description}</p>}
    </header>
    {children}
  </section>
}

function MissionTimeline({ dataset }: { dataset: Dataset }) {
  const { state, offline } = useReplay()
  const replay = state?.dataset_id === dataset.dataset_id ? state : dataset.replay
  const to = Date.parse(replay.cursor_utc) + 1000
  const elapsed = (to - Date.parse(dataset.mission_start_utc)) / oneDay
  const historical = dataset.historical_days / dataset.mission_days * 100
  const expectedTotal = dataset.dataset_id === publishedBundle.id && dataset.version === publishedBundle.version
    ? publishedBundle.observations : null
  const hiddenCount = expectedTotal === null ? null : Math.max(0, expectedTotal - replay.visible_count)
  const revealed = Math.max(0, Math.min(100 - historical, elapsed / dataset.mission_days * 100 - historical))
  return <figure className="surface science-timeline">
    <figcaption className="science-timeline-caption">
      <div><h3>What ASTRA can see</h3>
        <p>{offline ? 'Last confirmed mission time' : 'Published mission time'} · <time dateTime={replay.cursor_utc}>{formatExactUtc(replay.cursor_utc)}</time></p></div>
      <span className="science-day"><Timer size={16} aria-hidden="true" />Day {replay.mission_day} of {dataset.mission_days}</span>
    </figcaption>
    <div className="science-timeline-track" aria-hidden="true">
      <span className="science-period-history" style={{ width: historical + '%' }} />
      <span className="science-period-revealed" style={{ width: revealed + '%' }} />
      <span className="science-period-future" />
      <i style={{ left: (historical + revealed) + '%' }} />
    </div>
    <div className="science-timeline-axis" aria-hidden="true">
      <span>Day 1</span><span style={{ left: historical + '%' }}>Day {dataset.historical_days}</span><span>Day {dataset.mission_days}</span>
    </div>
    <ul className="science-timeline-key">
      <li><i className="science-period-history" /><div><strong>Historical reference</strong>
        <p>Days 1–{dataset.historical_days} establish personal references and variability.</p></div></li>
      <li><i className="science-period-revealed" /><div><strong>Revealed replay</strong>
        <p>{count(Math.max(0, replay.visible_count - dataset.historical_count))} replay observations available now.</p></div></li>
      <li><i className="science-period-future" /><div><strong>Unrevealed replay</strong>
        <p>{hiddenCount === null ? 'Future readings appear as replay advances.'
          : hiddenCount === 0 ? 'All replay observations are revealed.'
          : `${count(hiddenCount)} replay observations remain hidden.`}</p></div></li>
    </ul>
    <p className="science-tiny">ASTRA evaluates observations through the published mission time. The initial references stay fixed as replay publishes new readings.</p>
  </figure>
}

function DatasetOverview({ dataset }: { dataset: Dataset }) {
  const known = dataset.dataset_id === publishedBundle.id && dataset.version === publishedBundle.version
  const { state } = useReplay()
  const replay = state?.dataset_id === dataset.dataset_id ? state : dataset.replay
  const facts = [
    { label: 'Mission duration', value: count(dataset.mission_days), unit: 'days' },
    { label: 'Fictional crew', value: known ? count(publishedBundle.crew) : '—' },
    { label: 'Published bundle total', value: known ? count(publishedBundle.observations) : '—' },
    { label: 'Monitored indicators', value: count(dataset.metrics.length) },
  ]
  return <ScienceSection id="dataset" title="A synthetic mission dataset"
    description="Research-informed observations for a fictional crew, with a fixed historical window and a chronological replay.">
    <dl className="science-stats">
      {facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt>
        <dd>{fact.value}{fact.unit && <small> {fact.unit}</small>}</dd></div>)}
    </dl>
    <div className="science-dataset-inventory">
      <div><span>Initially available history</span><strong>{count(dataset.historical_count)}</strong></div>
      {known && <div><span>Replay in published bundle</span><strong>{count(publishedBundle.observations - dataset.historical_count)}</strong></div>}
      <div><span>Currently revealed, including history</span><strong>{count(replay.visible_count)}</strong></div>
      <div><span>Missing within Days 1–{dataset.historical_days} only</span><strong>{count(dataset.historical_missing_count)}</strong></div>
    </div>
    <MissionTimeline dataset={dataset} />
    <details className="science-disclosure science-provenance">
      <summary><span><strong>Dataset provenance</strong><small>{dataset.dataset_id} · v{dataset.version} · Synthetic</small></span><ChevronDown aria-hidden="true" size={18} /></summary>
      <div className="science-disclosure-body">
        <p>NASA and CDC publications informed what the generator measures and how the fictional profiles are described. Published sleep aggregates were used for comparison. The team did not fit the generator to raw human data or individual astronaut medical records.</p>
        <p>The four profiles illustrate the software workflow. They are not a clinically representative sample. Bundle totals describe inventory, including flagged missing rows. The running app publishes only observations at or before its replay cutoff.</p>
        {dataset.source_status !== 'VERIFIED' && <p role="status" data-tone="warn">
          {dataset.source_status === 'INVALID' ? 'Source integrity check failed.' : 'Source bundle unavailable.'} The last verified import is available.
        </p>}
      </div>
    </details>
  </ScienceSection>
}

function HazardOverview() {
  return <ScienceSection id="spaceflight" title="Designed around the challenges of human spaceflight"
    description="NASA’s Human Research Program identifies five hazards. ASTRA covers selected observations within that framework.">
    <div className="science-hazards">
      {hazards.map(({ name, icon: Icon, scope, detail, boundary }) => <article key={name} className="surface science-hazard">
        <span className="science-hazard-icon"><Icon size={21} aria-hidden="true" /></span>
        <div><span className="science-card-label">{scope}</span><h3>{name}</h3><p>{detail}</p><p className="science-boundary">{boundary}</p></div>
      </article>)}
    </div>
    <a className="science-link" href={nasaHazards}>NASA’s five hazards of human spaceflight <ArrowUpRight size={16} aria-hidden="true" /></a>
  </ScienceSection>
}

function Methodology({ historicalDays }: { historicalDays: number }) {
  const details = [
    <p>ASTRA reads authorized observations in a single replay snapshot, preserving UTC timestamps, units, collection context and quality. Shared views exclude private readings. Missing observations stay missing.</p>,
    <>
      <p>During Days 1–{historicalDays}, ASTRA takes one median per distinct UTC day, then the median of those daily values. A reference needs at least 10 valid days. Rest, exercise and recovery retain separate references. Ordered self-report categories use lower medians.</p>
      <dl className="science-equations">
        <div><dt>Reference</dt><dd>median(daily medians)</dd></div>
        <div><dt>Median absolute deviation</dt><dd>MAD = median(|daily median − reference|)</dd></div>
        <div><dt>Effective variability</dt><dd>effective MAD = max(MAD, metric floor)</dd></div>
      </dl>
    </>,
    <>
      <dl className="science-equations"><div><dt>Modified Z-score</dt><dd>0.6745 × (reading − reference) ÷ effective MAD</dd></div></dl>
      <ul className="science-bullets">
        <li>ASTRA’s engineering thresholds are |Z| ≥ 2.0 for a moderate deviation and |Z| ≥ 3.5 for a strong deviation in the configured direction. Sleep duration and oxygen saturation are compared downward. Resting pulse can deviate either way.</li>
        <li>A rolling median uses the last three valid day aggregates. A continuous trend fits a slope against actual elapsed days. It counts as directional when the fitted change reaches twice the effective MAD.</li>
        <li>Persistence requires a current deviation and three of the last five valid measurement days in the same direction within that metric’s window. Three strong days can produce Flagged.</li>
        <li>Ordered ratings compare category changes, with one category moderate and two strong. Older readings stay visible as context. Missing or stale newest readings block the current comparison.</li>
      </ul>
      <details className="science-policy">
        <summary>Continuous variability floors and windows <ChevronDown size={15} aria-hidden="true" /></summary>
        <div className="science-policy-scroll"><table>
          <thead><tr><th scope="col">Measurement</th><th scope="col">MAD floor</th><th scope="col">Trend or cabin window</th></tr></thead>
          <tbody>{[
            ['Rest / exercise / recovery heart rate', '2 / 5 / 3 bpm', '7 / 14 / 14 days'],
            ['Systolic and diastolic pressure', '3 mmHg each', '14 days'],
            ['Body temperature', '0.12 °C', '14 days'],
            ['Oxygen saturation', '1 percentage point', '21 days'],
            ['Sleep duration', '0.5 h', '7 days'],
            ['Cabin temperature / humidity / CO₂', '0.20 °C / 1 pp / 0.10 mmHg', '6 hours'],
          ].map(([metric, floor, window]) => <tr key={metric}><th scope="row">{metric}</th><td>{floor}</td><td>{window}</td></tr>)}</tbody>
        </table></div>
      </details>
    </>,
    <>
      <div className="science-context-flow">
        <div><strong>Physiology · sleep · self-report · cabin</strong>Compare compatible changes in their time windows.</div>
        <ArrowRight size={19} aria-hidden="true" />
        <div><strong>Contextual finding</strong>Show the observations that occurred together.</div>
      </div>
      <p>Reduced sleep and increased fatigue, or increased resting pulse plus reduced sleep or fatigue, are compared within 36 hours. Resting pulse and increased body temperature use a 24-hour window. A contextual finding requires two moderate signals and evidence of persistence or a strong result.</p>
      <p>Cabin CO₂ uses valid readings across at least four distinct hourly slots in a six-hour window. An unusual rise can be associated with valid, opted-in positive headache reports from at least two crew members within the past 36 hours. Coincidence supports a finding, without establishing a cause.</p>
    </>,
    <p>Deterministic rules return a monitoring state with source evidence, uncertainty and a suggested measurement check. A finding can coexist with limited coverage. Companion and the research prototypes do not contribute to the native state.</p>,
  ]
  return <ScienceSection id="methodology" title="From observation to explanation"
    description="Each step reveals the method or engineering decision behind it. The native analysis runs locally with no language model.">
    <ol className="science-pipeline">
      {stages.map(([title, summary], index) => <li key={title}>
        <details className="science-disclosure surface">
          <summary><span className="science-step">{String(index + 1).padStart(2, '0')}</span>
            <span><strong>{title}</strong><small>{summary}</small></span><ChevronDown size={18} aria-hidden="true" /></summary>
          <div className="science-disclosure-body">{details[index]}</div>
        </details>
      </li>)}
    </ol>
    <div className="surface science-monitoring">
      <h3>Monitoring states</h3>
      <dl>{monitoringStates.map(({ status, description }) => <div key={status}>
        <dt><MonitoringBadge status={status} /></dt><dd>{description}</dd>
      </div>)}</dl>
      <p>Stable requires at least three comparable primary indicator groups, including resting heart rate. A supported concern remains visible alongside missing information. These states describe statistical findings with no clinical urgency rating.</p>
    </div>
  </ScienceSection>
}

function MetricEntry({ metric, assumedPressure }: { metric: Metric; assumedPressure: number }) {
  const note = metricNotes[metric.metric]
  const measurementUnit = metric.unit === 'score_0_4' ? '0–4 ordinal scale' : unit(metric.unit)
  return <details className="science-metric">
    <summary><span><strong>{note?.[0] ?? metricLabel(metric.metric)}</strong>
      <small>{measurementUnit}{metric.metric === 'cabin_co2_concentration' && ' · Derived'}</small></span><ChevronDown size={16} aria-hidden="true" /></summary>
    <div className="science-disclosure-body">
      <p>{metric.description}.</p>
      <p className="science-tiny">Collection cadence: {metric.measurement_cadence === 'intermittent_or_daily'
        ? 'intermittent or daily, depending on the measure' : label(metric.measurement_cadence)}
        {metric.unit === 'score_0_4' ? ' · Subjective self-report' : ''}.</p>
      {note && <><p>{note[1]}</p><p className="science-boundary">{note[2]}</p></>}
      {metric.metric === 'cabin_co2_concentration' &&
        <p>ppm = (partial pressure ÷ assumed {assumedPressure} mmHg cabin pressure) × 1,000,000.</p>}
    </div>
  </details>
}

function Indicators({ dataset }: { dataset: Dataset }) {
  const assigned = new Set(metricGroups.flatMap((group) => group.metrics))
  const groups = [...metricGroups, { title: 'Other indicators', metrics: dataset.metrics.filter((m) => !assigned.has(m.metric)).map((m) => m.metric) }]
  return <ScienceSection id="indicators" title="Monitored indicators"
    description={count(dataset.metrics.length) + ' measures in five groups. Open a group and a measure to see its definition, cadence and role.'}>
    <div className="science-dictionary">
      {groups.map(({ title, metrics }) => {
        const entries = metrics.flatMap((id) => dataset.metrics.filter((m) => m.metric === id))
        if (!entries.length) return null
        return <details key={title} className="surface science-disclosure science-metric-group">
          <summary><span><strong>{title}</strong><small>{entries.length} {entries.length === 1 ? 'measure' : 'measures'}</small></span><ChevronDown size={18} aria-hidden="true" /></summary>
          <div>{entries.map((metric) => <MetricEntry key={metric.metric} metric={metric} assumedPressure={dataset.cabin_total_pressure_assumed_mmhg} />)}</div>
        </details>
      })}
    </div>
  </ScienceSection>
}

function Verification() {
  return <ScienceSection id="validation" title="System validation"
    description="Software checks and synthetic replay results from the Stage 03–05 verification reports, captured in checkpoint e1480d0.">
    <dl className="surface science-verification">
      {verification.map(([title, result]) => <div key={title}>
        <dt><Check size={17} aria-hidden="true" />{title}</dt><dd>{result}</dd>
      </div>)}
    </dl>
    <p className="science-tiny">These are recorded test results. They do not measure clinical accuracy, sensitivity or specificity. Camera and microphone capture were outside the Stage 05 browser check.</p>
  </ScienceSection>
}

function Research({ dataset }: { dataset: Dataset }) {
  const references = [
    ...dataset.references.map((entry) => ({
      ...entry,
      title: referenceNotes[entry.source_id]?.title ?? entry.title,
      contribution: referenceNotes[entry.source_id]?.contribution ?? entry.use,
      limit: referenceNotes[entry.source_id]?.limit,
    })),
    ...methodReferences,
  ]
  return <ScienceSection id="research" title="Research references"
    description="The original sources informed measurement choices and statistical methods. Expand a reference to see how ASTRA used it.">
    <div className="science-references">
      {references.map(({ source_id, title, organization, url, contribution, limit }) =>
        <details key={source_id} className="surface science-disclosure">
          <summary><span><small>{organization}</small><strong>{title}</strong></span><ChevronDown size={18} aria-hidden="true" /></summary>
          <div className="science-disclosure-body"><p>{contribution}</p>{limit && <p className="science-boundary">{limit}</p>}
            <a className="science-link" href={url}>Open original reference <span className="sr-only">{title}</span><ArrowUpRight size={16} aria-hidden="true" /></a>
          </div>
        </details>,
      )}
    </div>
  </ScienceSection>
}

function AiEngineering() {
  return <ScienceSection id="ai-engineering" title="AI-Assisted Engineering"
    description="The project team combined scientific research and engineering with extensive support from OpenAI’s ChatGPT and Codex.">
    <div className="science-ai-grid">
      <article className="surface science-ai-card">
        <span className="science-card-label">Development tool</span><h3>OpenAI ChatGPT</h3>
        <p>Supported concept development, architecture discussions, scientific exploration and dataset strategy. Helped compare analytical methods, plan implementation, review ideas, troubleshoot, and prepare interface concepts, documentation and presentation material.</p>
      </article>
      <article className="surface science-ai-card">
        <span className="science-card-label">Development tool</span><h3>OpenAI Codex</h3>
        <p>Helped translate the team’s requirements into the backend, frontend and statistical engine. Supported feature integration, debugging, refactoring, tests, Git, documentation and regression verification in the repository.</p>
      </article>
      <article className="surface science-ai-card science-ai-runtime">
        <span className="science-card-label">Optional onboard runtime</span><h3>Qwen · ASTRA Companion</h3>
        <p>Local Ollama runs <code>qwen3:4b-instruct-2507-q4_K_M</code> for chat, stories, quizzes, games and creative activities. Its inputs are the chat and a recreational prompt. It has no access to health records or controls for mission replay or application state.</p>
      </article>
    </div>
    <div className="surface science-runtime">
      <div><Terminal size={21} aria-hidden="true" /><h3>During development</h3><p>ChatGPT and Codex supported planning and implementation under team direction.</p></div>
      <ArrowRight className="science-runtime-arrow" size={21} aria-hidden="true" />
      <div><Cpu size={21} aria-hidden="true" /><h3>Onboard at runtime</h3><p>Deterministic native analysis, optional local Qwen and independent research prototypes. Native analysis runs without ChatGPT, Codex, OpenAI API access or cloud inference.</p></div>
    </div>
    <p>The team set the architecture, selected the methods, reviewed implementations and made the final engineering decisions. Responsibility for design and evaluation stayed with the team.</p>
  </ScienceSection>
}

function Limitations() {
  return <ScienceSection id="limitations" title="Evidence boundaries and future work"
    description="ASTRA is a research and engineering prototype. Clinical validation and flight qualification remain future work.">
    <div className="science-limitations">
      <article className="surface">
        <h3>What the demo can support</h3>
        <ul className="science-bullets">
          <li>Four fictional profiles, 45 initial history days and project-defined thresholds support a synthetic software demonstration. Intermittent readings and missing data limit coverage.</li>
          <li>The cabin view describes timing associations. The dataset has no radiation dose measurements.</li>
          <li>Facial and acoustic feature monitoring is experimental. Qwen Companion is recreational. Neither supplies clinical or psychological assessments.</li>
          <li>Private findings are scoped in the app and opt-in cabin data is aggregated. The local demo has no individual authentication or production access controls.</li>
        </ul>
      </article>
      <article className="surface">
        <h3>What to investigate next</h3>
        <ul className="science-bullets">
          <li>Connect real sensor streams and direct radiation dosimetry.</li>
          <li>Evaluate detection parameters against longitudinal human measurements.</li>
          <li>Introduce subject authentication and evaluate the system under realistic mission conditions.</li>
        </ul>
      </article>
    </div>
  </ScienceSection>
}

export default function DataScience() {
  return <div className="science">
    <div className="surface science-intro">
      <span className="science-intro-icon"><Radar size={27} aria-hidden="true" /></span>
      <div><p className="science-kicker">Research and engineering prototype</p>
        <h2>Monitoring change on a long transit</h2>
        <p>ASTRA explores autonomous, personalized health monitoring for long-duration human spaceflight. Research-informed synthetic data, longitudinal analysis and onboard computing make it possible to inspect how observations become evidence.</p>
        <a className="science-link" href="#dataset">Explore the dataset <ArrowDown size={16} aria-hidden="true" /></a>
      </div>
    </div>
    <nav className="science-nav" aria-label="Data and Science sections">
      {sections.map(([id, label]) => <a key={id} href={'#' + id}>{label}</a>)}
    </nav>
    <Resource<Dataset> url="/api/data">{(dataset) => <>
      <DatasetOverview dataset={dataset} />
      <HazardOverview />
      <Methodology historicalDays={dataset.historical_days} />
      <ScienceSection id="personalization" title="Same reading, different significance"
        description="Compare one hypothetical resting heart rate with the actual historical references of two fictional crew members.">
        <Personalization datasetId={dataset.dataset_id} />
      </ScienceSection>
      <Indicators dataset={dataset} />
      <Verification />
      <Research dataset={dataset} />
      <AiEngineering />
      <Limitations />
    </>}</Resource>
  </div>
}
