export type Modality = 'facial' | 'speech'
export type Scenario = 'fatigue_ramp' | 'sensor_dropout'
export type DetectorState = 'calibrating' | 'normal' | 'watch' | 'alert' | 'invalid'

export type FeatureWindow = {
  t: string
  state: DetectorState
  quality: number
  baseline: { n: number; ready: boolean }
  score: number | null
  driftPercentile: number | null
  features: Record<string, number | null>
  contributors: { feature: string; z: number; direction: string; cusum: number; windows_flagged: number }[]
}

export type ResearchDemo = {
  source: string
  upstream: string
  modalities: Record<Modality, { target: number; scenarios: Record<Scenario, FeatureWindow[]> }>
}

export const modalityTitle: Record<Modality, string> = { facial: 'Facial Feature Monitoring', speech: 'Voice Feature Monitoring' }
export const detectorLabel: Record<DetectorState, string> = {
  calibrating: 'Calibrating',
  normal: 'Within calibration range',
  watch: 'Feature shift',
  alert: 'Sustained feature deviation',
  invalid: 'Insufficient signal',
}

const featureNames: Record<string, string> = {
  expressiveness: 'Facial expressiveness',
  au_activation_rate: 'Facial muscle activation rate',
  head_pose_std: 'Head motion variability',
  au4_mean: 'Brow furrow (AU4)',
  au6_mean: 'Cheek raise (AU6)',
  au12_mean: 'Lip corner pull (AU12)',
  speech_rate_syll_per_s: 'Speech rate (syllables/s)',
  articulation_rate_syll_per_s: 'Articulation rate (syllables/s)',
  pause_ratio: 'Pause ratio',
  mean_pause_s: 'Average pause duration (s)',
  f0_mean: 'Pitch (F0)',
  f0_std: 'Pitch variability',
  hnr: 'Harmonics-to-noise ratio',
  jitter: 'Voice jitter',
  shimmer: 'Voice shimmer',
}

export function featureLabel(name: string) {
  return featureNames[name] ?? name.replaceAll('_', ' ')
}

export const fixtureTime = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium', timeStyle: 'medium', timeZone: 'UTC',
})

export type DemoSummary = {
  modality: Modality
  window: FeatureWindow
  source: string
  subject: string
  view: ResultView
}

export type SampleView = { scenario: Scenario; step: number; feature: string; open: boolean }

export type LiveResultView = {
  kind: 'live'
  windows: FeatureWindow[]
  features: string[]
  target: number
  feature: string
}

export type ResultView = LiveResultView | ({ kind: 'sample' } & SampleView)
