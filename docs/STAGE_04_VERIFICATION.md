# Stage 04 verification

Branch: `feature/native-health-intelligence`, based on `ff61256` (the shared facial and speech checkpoint). All test writes run against isolated SQLite. No changes to the dataset, development SQLite records, Git history or existing prototype implementations.

## Day 1–45 historical profiling before setting the policy

Valid counts exclude explicit missing rows. Cadence is the median spacing between observed UTC days for crew, and the published hourly collection cadence for the cabin. Range, median and MAD below use raw valid samples; runtime cabin references use medians of daily medians. Resolution is the smallest distinct observed increment. The raw audit includes ordinal sample MAD only for inspection; runtime never uses it for scores.

| Subject | Metric | Context | Valid samples | Distinct days | Cadence | Median | Raw MAD | Range | Missing rows | Observed resolution |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| AST-001 | body_temperature | rest | 15 | 15 | 3.0 d | 36.6 | 0.17 | 36.18–36.79 | 0 | 0.01 |
| AST-001 | diastolic_bp | rest | 15 | 15 | 3.0 d | 75 | 3 | 68–81 | 0 | 1 |
| AST-001 | exercise_duration | exercise | 38 | 38 | 1 d | 86 | 9 | 47–115 | 0 | 1 |
| AST-001 | exercise_heart_rate | exercise | 38 | 38 | 1 d | 142 | 9 | 112–162 | 0 | 1 |
| AST-001 | fatigue | self_report | 45 | 45 | 1.0 d | 1 | 0 | 0–3 | 0 | 1 |
| AST-001 | headache | self_report | 45 | 45 | 1.0 d | 0 | 0 | 0–1 | 0 | 1 |
| AST-001 | mood | self_report | 45 | 45 | 1.0 d | 3 | 0 | 1–4 | 0 | 1 |
| AST-001 | perceived_stress | self_report | 45 | 45 | 1.0 d | 1 | 0 | 1–3 | 0 | 1 |
| AST-001 | recovery_heart_rate | recovery | 38 | 38 | 1 d | 87.5 | 3.0 | 75–100 | 0 | 1 |
| AST-001 | resting_heart_rate | rest | 43 | 43 | 1.0 d | 66 | 2 | 59–72 | 2 | 1 |
| AST-001 | sleep_duration | sleep | 45 | 45 | 1.0 d | 7.45 | 0.63 | 4.43–9.5 | 0 | 0.01 |
| AST-001 | sleep_quality | self_report | 45 | 45 | 1.0 d | 3 | 0 | 1–4 | 0 | 1 |
| AST-001 | spo2 | rest | 12 | 12 | 4 d | 98 | 1 | 96–99 | 0 | 1 |
| AST-001 | systolic_bp | rest | 15 | 15 | 3.0 d | 115 | 2 | 110–126 | 0 | 1 |
| AST-002 | body_temperature | rest | 15 | 15 | 3.0 d | 36.53 | 0.11 | 36.32–36.93 | 0 | 0.01 |
| AST-002 | diastolic_bp | rest | 13 | 13 | 3.5 d | 79 | 3 | 71–86 | 0 | 1 |
| AST-002 | exercise_duration | exercise | 37 | 37 | 1.0 d | 88 | 12 | 54–115 | 0 | 1 |
| AST-002 | exercise_heart_rate | exercise | 37 | 37 | 1.0 d | 148 | 9 | 118–177 | 0 | 1 |
| AST-002 | fatigue | self_report | 45 | 45 | 1.0 d | 1 | 1 | 0–2 | 0 | 1 |
| AST-002 | headache | self_report | 45 | 45 | 1.0 d | 0 | 0 | 0–1 | 0 | 1 |
| AST-002 | mood | self_report | 45 | 45 | 1.0 d | 3 | 0 | 1–4 | 0 | 1 |
| AST-002 | perceived_stress | self_report | 45 | 45 | 1.0 d | 1 | 0 | 1–2 | 0 | 1 |
| AST-002 | recovery_heart_rate | recovery | 37 | 37 | 1.0 d | 93 | 5 | 78–111 | 0 | 1 |
| AST-002 | resting_heart_rate | rest | 45 | 45 | 1.0 d | 71 | 2 | 63–77 | 0 | 1 |
| AST-002 | sleep_duration | sleep | 45 | 45 | 1.0 d | 7.49 | 0.91 | 5.16–9.27 | 0 | 0.01 |
| AST-002 | sleep_quality | self_report | 45 | 45 | 1.0 d | 3 | 0 | 2–4 | 0 | 1 |
| AST-002 | spo2 | rest | 12 | 12 | 4 d | 98 | 1 | 96–100 | 0 | 1 |
| AST-002 | systolic_bp | rest | 13 | 13 | 3.5 d | 120 | 3 | 113–132 | 0 | 1 |
| AST-003 | body_temperature | rest | 15 | 15 | 3.0 d | 36.73 | 0.16 | 36.14–36.97 | 0 | 0.01 |
| AST-003 | diastolic_bp | rest | 16 | 16 | 3 d | 71.5 | 2.5 | 64–85 | 0 | 1 |
| AST-003 | exercise_duration | exercise | 38 | 38 | 1 d | 90 | 11 | 58–115 | 0 | 1 |
| AST-003 | exercise_heart_rate | exercise | 38 | 38 | 1 d | 139 | 7.5 | 109–172 | 0 | 1 |
| AST-003 | fatigue | self_report | 45 | 45 | 1.0 d | 1 | 1 | 0–2 | 0 | 1 |
| AST-003 | headache | self_report | 45 | 45 | 1.0 d | 0 | 0 | 0–1 | 0 | 1 |
| AST-003 | mood | self_report | 45 | 45 | 1.0 d | 3 | 0 | 2–4 | 0 | 1 |
| AST-003 | perceived_stress | self_report | 45 | 45 | 1.0 d | 1 | 0 | 1–2 | 0 | 1 |
| AST-003 | recovery_heart_rate | recovery | 38 | 38 | 1 d | 81.5 | 2.5 | 68–90 | 0 | 1 |
| AST-003 | resting_heart_rate | rest | 44 | 44 | 1 d | 59 | 2 | 52–64 | 1 | 1 |
| AST-003 | sleep_duration | sleep | 45 | 45 | 1.0 d | 7.61 | 0.54 | 4.67–9.5 | 0 | 0.01 |
| AST-003 | sleep_quality | self_report | 45 | 45 | 1.0 d | 3 | 0 | 2–4 | 0 | 1 |
| AST-003 | spo2 | rest | 12 | 12 | 4 d | 98 | 0.5 | 97–99 | 0 | 1 |
| AST-003 | systolic_bp | rest | 16 | 16 | 3 d | 112.5 | 4.5 | 103–123 | 0 | 1 |
| AST-004 | body_temperature | rest | 15 | 15 | 3.0 d | 36.44 | 0.10 | 36.24–36.94 | 0 | 0.01 |
| AST-004 | diastolic_bp | rest | 16 | 16 | 3 d | 75 | 3 | 71–81 | 0 | 1 |
| AST-004 | exercise_duration | exercise | 35 | 35 | 1.0 d | 86 | 9 | 55–115 | 0 | 1 |
| AST-004 | exercise_heart_rate | exercise | 35 | 35 | 1.0 d | 144 | 7 | 118–159 | 0 | 1 |
| AST-004 | fatigue | self_report | 45 | 45 | 1.0 d | 1 | 1 | 0–3 | 0 | 1 |
| AST-004 | headache | self_report | 45 | 45 | 1.0 d | 0 | 0 | 0–1 | 0 | 1 |
| AST-004 | mood | self_report | 45 | 45 | 1.0 d | 3 | 0 | 2–4 | 0 | 1 |
| AST-004 | perceived_stress | self_report | 45 | 45 | 1.0 d | 1 | 0 | 0–2 | 0 | 1 |
| AST-004 | recovery_heart_rate | recovery | 35 | 35 | 1.0 d | 87 | 2 | 69–99 | 0 | 1 |
| AST-004 | resting_heart_rate | rest | 45 | 45 | 1.0 d | 62 | 2 | 57–71 | 0 | 1 |
| AST-004 | sleep_duration | sleep | 45 | 45 | 1.0 d | 7.68 | 0.81 | 3.89–9.5 | 0 | 0.01 |
| AST-004 | sleep_quality | self_report | 45 | 45 | 1.0 d | 3 | 1 | 1–4 | 0 | 1 |
| AST-004 | spo2 | rest | 12 | 12 | 4 d | 98 | 1 | 96–99 | 0 | 1 |
| AST-004 | systolic_bp | rest | 16 | 16 | 3 d | 120 | 5 | 111–126 | 0 | 1 |
| CABIN-01 | cabin_co2_concentration | unspecified | 1076 | 45 | 1 h | 1746 | 189.5 | 1114–2719 | 4 | 1 |
| CABIN-01 | cabin_co2_partial_pressure | unspecified | 1078 | 45 | 1 h | 1.33 | 0.14 | 0.85–2.07 | 2 | 0.01 |
| CABIN-01 | cabin_relative_humidity | unspecified | 1076 | 45 | 1 h | 44.33 | 1.20 | 38.58–50.12 | 4 | 0.01 |
| CABIN-01 | cabin_temperature | unspecified | 1075 | 45 | 1 h | 22.62 | 0.24 | 21.7–23.65 | 5 | 0.01 |

All four subjects have sufficient history for **12 of 14** personal policies. Headache and duration of exercise are context only; no baseline applies. Three of four cabin metrics have sufficient daily history; derived CO₂ ppm is display only. Personal resting HR references, in source crew ID order, are **66, 71, 59 and 62 bpm**. Blood pressure and temperature cadence inform longer windows; oxygen saturation has the longest interval. Many ordinal MADs are zero, supporting explicit category comparison instead of Z-scoring.

## Retrospective synthetic annotation comparison

Rules were fixed before using the evaluation-only annotations. They were compared offline with the endpoint results; the annotations were never mounted or read by runtime. These labels describe some constructed scenarios, not an exhaustive ground truth for the effect of measurement variation.

| Annotation | Observed behavior at daily close and limitations |
| --- | --- |
| Cabin gap on Day 56 | No cabin excursion advisory at daily close. The gap is a within-day expected loss of readings, not an end-of-day environmental change. Full replay used daily closes plus a separate same-day cutoff test; it did not establish the cabin gap's recognition at each timestamp. |
| CO₂ excursion and opted-in headache cluster on Days 61–63 | Cabin reference shift on Day 61, one consolidated advisory on Day 62, none at Day 63 close. The configured recent-window rule does not cover the full annotated interval. Individual headache records do not appear in the advisory. |
| AST-004 wearable gap on Days 67–69 | The missing measurements remain missing; other indicator findings can coexist. They do not replace the unavailable heart-rate comparison. |
| AST-002 sleep disruption on Days 73–79 | A sleep/fatigue and cardiovascular recovery pattern appeared on Day 75, and the cardiovascular/recovery pattern continued through Day 79. The paired rule did not flag the onset on Day 73. |
| AST-004 small HR trend on Days 50–61 | A cardiovascular/recovery pattern appeared on Day 57. This is not sustained detection of the engineered mild HR shift; the rule requires meaningful magnitude and corroboration and can leave weak signals below the finding threshold. |

There were Watch results on the initial snapshot and during ordinary-looking windows. Some isolated and subjective-category changes contribute repeated daily findings, so the raw totals overstate distinct episodes. The simulation does not provide an exhaustive label set for estimating false alert rates. The thermal pattern is exercised in a controlled fixture, not observed at the evaluated daily snapshots. The sample count and evaluation are not evidence of clinical validity.

## Full replay and automated verification

The full replay test starts at Day 45 (6,252 observations), reads the mission plus all four crew analyses at every end-of-day position through Day 90 (12,491 observations), and compares returned evidence with exact source values, UTC timestamps, context, quality and IDs. Fixed references, finite numbers, privacy, source checksums, identical snapshots, restart, and reset were checked. The timestamp test advances only to the first event of Day 46 and inserts a later row into test SQLite to verify that the read-time cutoff independently excludes it. No task used the development database for test writes.

| Replay measure | Result |
| --- | --- |
| Crew analysis snapshots (46 × 4) | 184 |
| Personal statuses | 78 Stable, 89 Watch, 16 Flagged, 1 Insufficient data |
| Mission card statuses (shareable inputs only) | 128 Stable, 54 Watch, 0 Flagged, 2 Insufficient data |
| Personal findings | 161 single metric, 10 sleep/fatigue, 9 cardiovascular/recovery, 0 cardiovascular/thermal, 4 limited-coverage notices |
| Cabin findings | 1 standalone reference shift and 1 shared advisory |
| Unavailable personal comparisons | 4 resting HR comparisons due to the newest sample being missing; the rest of that person's coverage and findings still applied |
| Crew analysis latency | 44.4 ms median, 61.0 ms p95 |
| Mission snapshot latency | 70.7 ms median, 94.7 ms p95 |

Timings are from local FastAPI TestClient requests in one test run, including SQLite reads, analysis and JSON serialization. They are not browser render times. Native analysis runs synchronously outside the replay event loop in FastAPI's normal threadpool; no application-wide cache or analysis write is used.

- Backend regression and analytical tests: `uv run --locked --offline --python $astraPython --no-managed-python pytest -q -s`, **43 passed**. The existing 21-test suite is included; one assertion that the planned analysis route did not exist was retired. The evaluation test prints its counters and per-day findings.
- Unchanged research prototype tests: from project root set `$env:PYTHONPATH = (Resolve-Path 'face_speech').Path`, then run `& '%LOCALAPPDATA%/ASTRAResearch/.venv/Scripts/python.exe' -m pytest face_speech/tests -q`, **49 passed** in the separate installed environment.
- In `frontend`: `npm.cmd run lint`, `npm.cmd run typecheck` and `npm.cmd run build` all passed.
- SHA-256: all 16 entries in the original source bundle checksum list matched before and after verification. None of the source files, replay tables, or Research Prototypes implementations was edited.

## Browser verification

Isolated headless Chrome used Vite on 15184 and FastAPI on 18054 with a fresh temporary SQLite database. Mission Overview, Crew Health for all four profiles, Mission Replay and Data & Science loaded. Charts showed real measurements and continuous personal reference lines. Automatic playback advanced records and analysis, and reset restored Day 45. Changing or refreshing data no longer overwrites the preference to keep Detailed records expanded. Chrome also verified keyboard operation of Detailed records, switching to the sleep chart, the 390px layout, raw readings/charts when the subject analysis request was blocked, one consolidated Day 62 cabin advisory, and removal of the advisory after reset. The hidden future CSV returned 404.

Both synthetic face and voice walkthroughs produced visible results with the optional live broker blocked. Existing prototype unit tests passed separately. Physical camera and microphone capture were not repeated.

## Verify on your Windows checkout

Keep your current mission if you prefer. To start from Day 45 without altering it, stop the current backend and launch it with a temporary test database. If the existing Vite frontend is already running, leave it open.

```powershell
Set-Location './backend'
$astraPython = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python312/python.exe'
$env:ASTRA_DB_PATH = Join-Path $env:TEMP ('astra-stage04-review-' + [guid]::NewGuid() + '.sqlite3')
uv run --locked --offline --python $astraPython --no-managed-python uvicorn --factory astra.main:create_app --app-dir src --host 127.0.0.1 --port 8050
```

1. Open [Mission Overview](http://127.0.0.1:5180/) and look for **Health intelligence** and the crew monitoring badges. Research results, if any, remain labeled Experimental.
2. Open **Crew Health**. Select an astronaut, inspect the resting heart rate card and chart, and expand **Statistical details**, **Evidence and limitations** or **Detailed records**. The reference dashed line stays fixed. Missing data stays missing.
3. Go to **Mission Replay**, then choose **Next Day** or **Play**. While playing, return to Crew Health: dated source records and findings refresh without changing the selected crew member, metric, range or expanded table.
4. For the shared result, pause and step to Day 62. **Mission Overview → Latest valid cabin readings** shows one **Possible shared cabin contributor** advisory. It gives aggregate consent and CO₂ evidence without attributing symptoms to individual crew. Reset in the test DB to verify it disappears.
5. Stop the test backend with Ctrl+C, then run `Remove-Item Env:ASTRA_DB_PATH` in that PowerShell terminal before restarting the normal backend. If you had a custom database override, restore that value instead.

## File inventory

| Area | Added | Updated |
| --- | --- | --- |
| Backend | `backend/src/astra/health_models.py`, `health_statistics.py`, `health_engine.py` | `backend/src/astra/models.py`, `routes.py` |
| Tests | `backend/tests/test_intelligence.py`, `test_intelligence_replay.py` | `backend/tests/test_health.py` |
| UI | `frontend/src/pages/HealthFindings.tsx`, `frontend/src/services/health-analysis.ts`, `frontend/src/styles/health-intelligence.css` | `frontend/src/main.tsx`, `frontend/src/pages/CrewHealth.tsx`, `HealthChart.tsx`, `MissionData.tsx`, `frontend/src/services/mission.ts` |
| Docs | `docs/HEALTH_INTELLIGENCE_METHODOLOGY.md`, `docs/STAGE_04_VERIFICATION.md` | `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/ROADMAP.md`, `docs/STATUS.md`, `docs/RESEARCH_PROTOTYPES_INTEGRATION.md` |