export type MonitoringStatus = 'STABLE' | 'WATCH' | 'FLAGGED' | 'INSUFFICIENT_DATA'
export type Coverage = { current_groups: number; required_groups: number; total_groups: number; sufficient: boolean }
export type MonitoringSummary = { status: MonitoringStatus; coverage: Coverage; headline: string }

export type Evidence = {
  observation_id: string; metric: string; timestamp_utc: string; value: number | null
  unit: string; source: string; context: string; quality: 'VALID' | 'MISSING'; provenance: 'SYNTHETIC'
}

export type Baseline = {
  metric: string; context: string; unit: string; kind: 'continuous' | 'ordinal' | 'context_only'
  availability: 'AVAILABLE' | 'INSUFFICIENT_DATA' | 'NOT_APPLICABLE'
  median: number | null; mad: number | null; effective_mad: number | null
  valid_sample_count: number; distinct_days: number; required_days: number
  calibration_start_utc: string; calibration_end_utc: string
}

export type Comparison = {
  metric: string; context: string; status: MonitoringStatus | null
  availability: 'CURRENT' | 'STALE' | 'MISSING' | 'UNAVAILABLE'
  current: Evidence | null; latest_valid: Evidence | null; age_hours: number | null; freshness_hours: number
  difference: number | null; absolute_difference: number | null; relative_percent: number | null
  modified_z: number | null; direction: 'UP' | 'DOWN' | 'FLAT' | null
  trend_direction: 'UP' | 'DOWN' | 'FLAT' | null; slope_per_day: number | null
  rolling_median: number | null; trend_window_days: number; recent_days: number
  persistent_days: number; strong_days: number; unusual_ids: string[]
}

export type Finding = {
  rule_id: string; type: 'SINGLE_METRIC' | 'CONTEXTUAL' | 'CABIN' | 'SHARED_CABIN' | 'DATA_QUALITY'
  crew_id: string | null; status: MonitoringStatus; title: string; explanation: string; uncertainty: string
  verification: string; evidence: Evidence[]; shared_report_count: number | null
  habitat_comparison: {
    metric: string; unit: string; window_median: number; historical_median: number; effective_mad: number
    modified_z: number; window_hours: number; valid_hours: number
  } | null
}

export type CrewAnalysis = {
  crew_id: string; revision: number; cursor_utc: string; method_version: string; provenance: 'SYNTHETIC'
  status: MonitoringStatus; coverage: Coverage; baselines: Baseline[]; indicators: Comparison[]
  blood_pressure: Evidence[]; findings: Finding[]; cabin_findings: Finding[]
}
