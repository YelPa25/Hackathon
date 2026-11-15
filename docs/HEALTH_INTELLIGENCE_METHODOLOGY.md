# Native health intelligence · astra-native-v1

ASTRA compares the fictional crew's measurements with their own past observations. The native engine is deterministic, read-only and offline. It does not use trained models, an LLM, research-prototype output, generated measurements or evaluation scenario labels. A finding is a statistical change with a suggested verification, not a diagnosis, emergency classification or exposure limit.

## Reference and current comparison

- The dataset defines the initial Days 1–45 period. Every read uses the backend replay snapshot and its inclusive UTC cutoff. The reference window includes only compatible, valid historical samples; newly revealed days never recalibrate it. References are computed on request from the same snapshot as the current observations.
- One median per distinct UTC day keeps densely sampled days from outweighing sparse days. A reference requires at least **10 valid measurement days**. Continuous references use the median of daily medians and the median absolute deviation (MAD) of those medians. Ordinal references use the lower observed median within and across days. This keeps self-reports on their original integer scale.
- Continuous modified Z = **0.6745 × (current reading − reference median) / max(MAD, configured floor)**. ASTRA exposes signed and absolute differences, and a relative percent only for positive reference heart rate, BP and sleep duration. Modified Z thresholds: **2.0 moderate**, **3.5 strong**, inclusive in the direction specified below. The [NIST statistics handbook](https://itl.nist.gov/div898/handbook/eda/section3/eda35h.htm) describes the modified Z-score. Daily aggregation, floors, bands of interest and statuses are ASTRA engineering choices.
- Ordinal deviations are **1 category moderate** and **2 categories strong** in the configured direction. No Z-score, MAD, percentage or physiological slope is reported for ordinal self-reports. Fatigue, perceived stress and headache scores are higher for more reported symptoms or stress; mood and sleep quality are higher for more positive ratings. Only a valid headache score of zero records symptom absence.
- Newest missing and stale samples block a current comparison. The last valid reading, its timestamp and its age remain available for context. Missing readings stay null. Invalid, incompatible or non-finite values never contribute. Charts plot original readings and preserve explicit gaps; hollow markers identify source observations in the last 45 days that cross the strong statistical threshold. Reference lines represent historical medians.
- The latest three comparable UTC-day medians provide a rolling reference. Continuous least-squares slope uses actual elapsed time in days, with the latest valid timestamp of a day anchoring its median. A slope counts as directional only if fitted change across the window is at least twice the effective MAD. Ordinal trend compares the lower medians of the first and last three categories. Trends require at least three valid days.
- Persistence requires the current deviation and **three of the last five valid measurement days** in the relevant window to deviate in the same direction. Missing days do not count. Three strong days may produce Flagged. A strong isolated observation, moderate persistence, or a moderate current deviation with a meaningful trend can produce Watch.

## Policy by metric

| Metric | Context | Policy direction | Fresh through | Trend/persistence window | MAD floor |
| --- | --- | --- | ---: | ---: | ---: |
| `resting_heart_rate` | Rest | Both | 48 h | 7 d | 2 bpm |
| `exercise_heart_rate` | Exercise | Both | 72 h | 14 d | 5 bpm |
| `recovery_heart_rate` | Recovery | Both | 72 h | 14 d | 3 bpm |
| `systolic_bp`, `diastolic_bp` | Rest | Both, separately | 120 h | 14 d | 3 mmHg |
| `body_temperature` | Rest | Both | 120 h | 14 d | 0.12 °C |
| `spo2` | Rest | Down | 144 h | 21 d | 1 percentage point |
| `sleep_duration` | Sleep | Down | 48 h | 7 d | 0.5 h |
| `sleep_quality`, `mood` | Self-report | Down; ordinal | 48 h | 7 d | — |
| `fatigue`, `perceived_stress` | Self-report | Up; ordinal | 48 h | 7 d | — |
| `headache` | Self-report | Shared context only | 48 h for the profile; 36 h for cabin use | — | — |
| `exercise_duration` | Exercise | Activity context only | 72 h | — | — |
| `cabin_temperature` | Habitat | Both | 3 h | 6 h recent window | 0.20 °C |
| `cabin_relative_humidity` | Habitat | Both | 3 h | 6 h recent window | 1 percentage point |
| `cabin_co2_partial_pressure` | Habitat | Up | 3 h | 6 h recent window | 0.10 mmHg |
| `cabin_co2_concentration` | Habitat | Derived display only | Raw timestamp | — | — |

The floors avoid inflated scores for narrow historical spreads and are informed by observed resolution and variability. The heart-rate and pressure floors span several source increments, with more allowance during exercise. The temperature and sleep floors exceed the 0.01-unit source precision. The oxygen floor is one whole reported percentage point. Cabin floors exceed source resolution and limit small excursions. Freshness allows some margin beyond the observed measurement cadence; it does not certify a sensor. BP cards pair systolic and diastolic only when time, source and context agree. Exercise duration remains available in the activity view without generating a standalone concern. No respiratory rate or radiation dose is derived.

## Context and monitoring status

| Rule | Evidence required |
| --- | --- |
| `SLEEP_FATIGUE` | Reduced sleep duration or quality and increased reported fatigue within 36 hours. |
| `CARDIO_RECOVERY` | Increased resting heart rate and reduced sleep or increased reported fatigue within 36 hours of the HR observation. |
| `CARDIO_THERMAL` | Increased resting heart rate and body temperature within 24 hours. |
| `SHARED_CO2_HEADACHE` | Eligible cabin CO₂ change and at least two different crew members with latest valid positive, opted-in headache reports in the past 36 hours. A later valid zero or loss of consent supersedes a previous report. Missing reports do not count as a zero or an opt-in. |
| `MONITORING_COVERAGE` | Too few primary groups or no current comparable resting heart rate. List known coverage alongside any concern that can still be supported. |

Personal contextual rules require both signals to reach their moderate thresholds and either one persistent series or one strong observation. One persistent series or two strong observations permits Flagged; otherwise the supported combination is Watch. Suppress single findings covered by the same combination if this does not hide a higher priority. Suppress a sleep/fatigue pattern when already fully covered by cardiovascular and recovery evidence.

For habitat findings, require a current valid measurement and at least four distinct valid hourly slots in the last six hours. Compare the median of those hourly medians with the fixed historical daily-median reference. This is a multi-hour statistical summary; it is not a measured one-hour average. Primary CO₂ requires an upward moderate signal; cabin temperature and humidity require a strong signal. The derived ppm representation is not independent evidence. A shared CO₂ advisory replaces its standalone CO₂ finding rather than creating duplicates. A cabin advisory never overrides crew status and reports only the eligible aggregate count and cabin evidence. Timing cannot establish cause.

**Flagged > Watch > Stable** where adequate coverage exists. Stable requires at least **3 of 6** comparable primary groups, including resting heart rate. A BP group requires both current components from the same session. Cabin and research results never change individual status. A supported concern takes precedence over gaps; otherwise insufficient coverage returns **Insufficient data**. Stable means no configured deviation was detected in the available monitored indicators. It cannot establish medical safety.

Mission Overview builds its own summaries from shareable observations only. Crew Health can include the chosen subject's private ratings. An authorized opted-in headache can affect the shared aggregate, but the aggregate does not expose subject IDs, private readings, exact symptom times or references to private rows. This is a local prototype without per-user authentication. Subject scoping is not production privacy protection.

## Evaluation boundary

This configuration was set after examining only historical observations. The separate [Stage 04 verification report](STAGE_04_VERIFICATION.md) describes the complete replay evaluation and coverage, plus manually compared synthetic annotations. Dataset NASA/CDC references inform measurement selection and interpretation, not the fictional observations or these decision thresholds. No clinical accuracy, sensitivity or readiness has been established.
