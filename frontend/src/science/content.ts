import { Atom, Earth, Gauge, Radio, Users } from 'lucide-react'
import type { MonitoringStatus } from '../services/health-analysis'

export const sections = [
  ['dataset', 'Dataset'],
  ['spaceflight', 'Spaceflight hazards'],
  ['methodology', 'Methodology'],
  ['personalization', 'Personalization'],
  ['indicators', 'Indicators'],
  ['validation', 'Validation'],
  ['research', 'References'],
  ['ai-engineering', 'AI-assisted engineering'],
  ['limitations', 'Limitations'],
] as const

// Published inventory for this verified bundle, from the dataset validation report.
export const publishedBundle = { id: 'ASTRA-SYN-90D-01', version: '1.0.0', crew: 4, observations: 12491 }

export const nasaHazards = 'https://www.nasa.gov/hrp/hazards/'

export const hazards = [
  {
    name: 'Space radiation', icon: Atom, scope: 'Outside monitoring scope',
    detail: 'The dataset contains no radiation dose or dosimeter readings. ASTRA does not infer exposure from other measurements.',
    boundary: 'Future work could connect direct radiation dosimetry.',
  },
  {
    name: 'Isolation and confinement', icon: Users, scope: 'Well-being observations',
    detail: 'Sleep, fatigue, mood and stress can be viewed over time. Research Prototypes explores facial movement and voice features. The local Companion offers recreational conversation.',
    boundary: 'Feature deviations do not identify emotions or mental health conditions. Companion has no validated psychological benefit.',
  },
  {
    name: 'Distance from Earth', icon: Radio, scope: 'Local operation',
    detail: 'Local storage and deterministic analysis keep Core available without cloud AI. The optional Qwen Companion also runs locally.',
    boundary: 'The offline checks cover this prototype on a workstation. Flight qualification is future work.',
  },
  {
    name: 'Gravity fields', icon: Earth, scope: 'Cardiovascular references',
    detail: 'Personal references separate resting, exercise and recovery heart rates. Blood pressure and exercise duration provide additional longitudinal context.',
    boundary: 'ASTRA has no gravity exposure measurements and cannot isolate the effects of microgravity.',
  },
  {
    name: 'Hostile or closed environments', icon: Gauge, scope: 'Cabin observations',
    detail: 'ASTRA monitors synthetic cabin CO₂, temperature and relative humidity. Eligible opted-in headache reports can add context to a CO₂ finding.',
    boundary: 'Timing can suggest an association. The system does not establish causes or control the cabin.',
  },
]

export const stages = [
  ['Acquire', 'Read authorized observations through the published mission time.'],
  ['Personalize', 'Build a fixed reference for each crew member, metric and context.'],
  ['Detect', 'Check the size, direction and persistence of changes.'],
  ['Contextualize', 'Look for related changes within defined time windows.'],
  ['Explain', 'Show the finding, the evidence and a way to verify it.'],
] as const

export const monitoringStates: { status: MonitoringStatus; description: string }[] = [
  { status: 'STABLE', description: 'No configured concern was detected in the adequately monitored indicators.' },
  { status: 'WATCH', description: 'An unusual reading or pattern warrants attention or measurement verification.' },
  { status: 'FLAGGED', description: 'A sufficiently supported statistical concern warrants review.' },
  { status: 'INSUFFICIENT_DATA', description: 'Missing history, missing readings or stale measurements limit the assessment.' },
]

export const metricGroups = [
  { title: 'Cardiovascular', metrics: ['resting_heart_rate', 'exercise_heart_rate', 'recovery_heart_rate', 'systolic_bp', 'diastolic_bp'] },
  { title: 'Physical condition', metrics: ['body_temperature', 'spo2'] },
  { title: 'Sleep and well-being', metrics: ['sleep_duration', 'sleep_quality', 'fatigue', 'mood', 'perceived_stress', 'headache'] },
  { title: 'Physical activity', metrics: ['exercise_duration'] },
  { title: 'Habitat environment', metrics: ['cabin_temperature', 'cabin_relative_humidity', 'cabin_co2_partial_pressure', 'cabin_co2_concentration'] },
]

export const metricNotes: Record<string, [name: string, use: string, limit: string]> = {
  resting_heart_rate: ['Resting heart rate', 'Compares resting readings with the personal reference and can support recovery and thermal patterns.', 'Exercise and recovery readings have separate references.'],
  exercise_heart_rate: ['Exercise heart rate', 'Compares exercise-session readings with that crew member’s exercise reference.', 'An exercise comparison does not account for every change in workload.'],
  recovery_heart_rate: ['Recovery heart rate', 'Tracks changes in the recovery context against a separate personal reference.', 'This is a sampled recovery reading, not a continuous recovery curve.'],
  systolic_bp: ['Systolic blood pressure', 'Compared independently. Displays as a pair with diastolic only when time, source and context match.', 'Intermittent cuff readings leave gaps between measurements.'],
  diastolic_bp: ['Diastolic blood pressure', 'Compared independently. Displays as a pair with systolic only when time, source and context match.', 'An unmatched reading remains a single observation.'],
  body_temperature: ['Body temperature', 'Checks personal changes and can add context to an increased resting heart rate.', 'A change is statistical evidence and has no diagnostic classification.'],
  spo2: ['Oxygen saturation (SpO₂)', 'Checks for decreases relative to the personal reference.', 'Intermittent finger readings cannot describe changes between samples.'],
  sleep_duration: ['Sleep duration', 'Checks shorter sleep and its timing relative to fatigue or changes in resting heart rate.', 'The synthetic measure combines a wearable estimate and self-report.'],
  sleep_quality: ['Sleep quality', 'Compares decreases in ordered rating categories, with 4 the best rating.', 'This is a subjective report. Its categories have no measured spacing.'],
  fatigue: ['Fatigue', 'Compares increases in ordered rating categories and can support recovery patterns.', 'A high self-reported rating alone cannot explain its cause.'],
  mood: ['Mood', 'Compares decreases in ordered rating categories, with 4 most positive.', 'A mood change is not a psychological assessment.'],
  perceived_stress: ['Perceived stress', 'Compares increases in ordered rating categories.', 'The rating is voluntary and subjective.'],
  headache: ['Headache', 'A valid positive report can contribute to a shared cabin finding when the crew member opts in.', 'A missing report differs from a valid zero. Shared findings disclose an aggregate count.'],
  exercise_duration: ['Exercise duration', 'Provides session context. It is not scored as a standalone concern.', 'The duration is voluntary and does not measure exercise intensity.'],
  cabin_temperature: ['Cabin temperature', 'Compares a median from recent valid hourly slots with the historical cabin reference.', 'Sensor gaps can prevent a current comparison.'],
  cabin_relative_humidity: ['Cabin relative humidity', 'Compares recent valid hourly slots with the historical cabin reference.', 'The prototype does not use this comparison for environmental control.'],
  cabin_co2_partial_pressure: ['Cabin CO₂ partial pressure', 'Primary CO₂ measure for the recent cabin comparison and eligible symptom associations.', 'A statistical deviation cannot establish symptom causation or compliance with an exposure limit.'],
  cabin_co2_concentration: ['Derived cabin CO₂ concentration', 'Displays an estimate in ppm from partial pressure and the assumed cabin pressure.', 'Both CO₂ values describe the same observation. They provide one line of evidence.'],
}

export const referenceNotes: Record<string, { title?: string; contribution: string; limit: string }> = {
  'NASA-SLEEP': {
    contribution: 'The generator used the published in-flight mean of 7.33 hours and standard deviation of 1.16 hours as an aggregate comparison for synthetic sleep duration.',
    limit: 'The published sample was 19 crew members and 2,137 nights. ASTRA did not import their individual records or fit its profiles to them.',
  },
  'NASA-CO2': {
    contribution: 'The technical brief informed the choice of cabin CO₂ measurements and how ASTRA describes uncertainty around reported headache associations.',
    limit: 'ASTRA did not fit a symptom prediction model or use the brief’s exposure standard as a severity rule.',
  },
  'NASA-STDM': {
    title: 'Spaceflight Standard Measures: Characterizing How Humans Adapt in Space',
    contribution: 'The Standard Measures program informed the measurement categories, check-ins and instrument choices.',
    limit: 'It did not supply the numeric distributions or authorize the synthetic values.',
  },
  'CDC-NHANES': {
    title: 'NHANES 2017–2018: Blood Pressure (BPX_J)',
    contribution: 'The codebook supplied terrestrial blood-pressure and pulse definitions, measurement protocols and context for the synthetic profiles.',
    limit: 'The team did not download individual-level XPT rows or fit the synthetic profiles to NHANES microdata.',
  },
}

export const methodReferences = [
  {
    source_id: 'NIST-OUTLIERS', organization: 'NIST/SEMATECH',
    title: 'Detection of Outliers', url: 'https://itl.nist.gov/div898/handbook/eda/section3/eda35h.htm',
    contribution: 'The handbook describes the modified Z-score as a robust way to label potential outliers using the median and MAD.',
    limit: 'ASTRA chose its own metric directions, variability floors and persistence requirements for this prototype.',
  },
  {
    source_id: 'NASA-HAZARDS', organization: 'NASA Human Research Program',
    title: '5 Hazards of Human Spaceflight', url: nasaHazards,
    contribution: 'The overview supplies the five hazard categories used to organize ASTRA’s human spaceflight context.',
    limit: 'The hazard framework does not evaluate the prototype or its monitoring coverage.',
  },
]

export const verification = [
  ['Dataset integrity', '16 listed SHA-256 checks passed. Import checks verify schema, unique IDs, the data split and blank values for missing observations.'],
  ['Chronological replay', 'Verified Days 45–90, reset, restart persistence and exclusion of future timestamps. Stage 04 evaluated 184 crew snapshots.'],
  ['Native analysis', 'Tests covered fixed references, variability floors, trends, persistence, contextual rules, and missing or stale readings. All four profiles had sufficient history for 12 of 14 personal policies.'],
  ['Privacy and separation', 'Tests checked shareable and private scopes, opt-in cabin aggregation, and that Companion receives the supplied conversation only.'],
  ['Offline operation', 'Local SQLite and native analysis ran without cloud services. A cloud-disabled Ollama instance completed real local chat. Core remained available when that instance stopped.'],
  ['Software quality', '72 backend tests, including 29 Companion tests, and 49 facial and speech prototype tests passed. Frontend lint, TypeScript and production build passed.'],
] as const
