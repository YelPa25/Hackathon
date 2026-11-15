# ASTRA 2.0 contracts

Version 1. HTTP uses `/api`, UTF-8 JSON, snake_case fields and RFC 3339 UTC timestamps with `Z`. Use finite numeric values and explicit nulls. The dataset ID and observation IDs remain the strings supplied by the source.

## Dataset and normalization

Set `ASTRA_DATASET_DIR` to the extracted dataset directory. Without an override, prefer `data-source/ASTRA_90day_dataset_v1` when present and otherwise use `ASTRA_90day_dataset_v1` at the project root. Relative overrides resolve from the project root. The manifest has no embedded hashes. Verify the manifest and the other allowlisted inputs against `SHA256SUMS.txt`. Pin the five verified runtime hashes in SQLite. Only the replay writer opens the future partition. Runtime excludes the full archive and evaluation CSV.

| Input | Contract |
| --- | --- |
| `dataset_manifest.json` | Dataset ID, generator version, mission dates and duration, 45/45 split, synthetic flag, CO₂ pressure assumption, reference metadata and limitations. Only reviewable provenance fields go to the UI. |
| `crew_profiles.csv` | Four unique IDs `AST-001` to `AST-004`. Use `crew_id`, `display_name` and `role` for crew summaries, plus `age_years` and `activity_pref` for profile details. Generator seed parameters such as `rest_hr_ref_bpm`, `sys_ref_mmhg` and `sleep_tendency_h` do not enter runtime baselines. |
| `metric_dictionary.csv` | 18 unique metric keys, canonical unit, description, cadence and synthetic provenance. Validate values against the dictionary and the source's context and scope. |
| `scientific_sources.csv` | Allowlist source ID, organization, title, URL, stated use and raw-data-fit flag for citation and provenance. |
| `replay_history_DAY01_to_DAY45.csv` | 6,252 original rows. Only this partition is published at initialization. |
| `replay_future_HIDDEN_DAY46_to_DAY90.csv` | 6,239 private replay rows. Advance publishes exact observations through the requested cutoff. |
| Evaluation CSV, workbook, daily summary, full archive and generator | Developer materials. Runtime excludes these from observation input, derived findings, API payloads and static assets. Review `validation_report.json` during development. |

Both replay CSVs have the same header:

```text
observation_id,mission_id,crew_id,subject_id,scope,timestamp_utc,mission_day,metric,value,unit,activity_context,source,provenance,quality,missing_reason,privacy,share_cabin_context,note
```

| Field | Observation validation and storage |
| --- | --- |
| `observation_id`, `mission_id` | Nonempty stable ID unique across both partitions for a dataset. This release uses `SIM-...` IDs and `ASTRA-SYN-90D-01` as the mission ID. |
| `scope`, `crew_id`, `subject_id` | `person` requires an existing crew ID and matching subject ID. `cabin` requires null crew ID and subject `CABIN-01`. |
| `timestamp_utc`, `mission_day` | Parse explicit UTC. Day is 1 plus elapsed UTC calendar days from 2040-01-01. Require days 1–45 in history and 46–90 in future. Verify chronological order by timestamp. Sort equal timestamps by ID without editing the CSV. |
| `metric`, `unit`, `value` | Exact dictionary key and unit for the scope. `VALID` requires a finite value, including zero when supplied. `MISSING` requires a blank value, decoded to null, and a reason. Validate integer 0–4 scores and 0–100 percentages as representation constraints. |
| `source`, `provenance`, `quality`, `missing_reason` | Preserve original source string. Require `SYNTHETIC` in both files. Quality is `VALID` or `MISSING`. A valid row has null missing reason. Reserve provenance names `MANUAL` and `IMPORTED` for separate, future ingestion. |
| `activity_context` | Source values are `rest`, `exercise`, `recovery`, `sleep`, `self_report` and `unspecified`. Enforce heart-rate metric/context pairs. `unspecified` is present on cabin telemetry. |
| `privacy`, `share_cabin_context` | `crew`, `private_health` or `shared_environment`. Parse explicit true/false. Only eligible, opted-in valid headache reports may contribute to cabin aggregates. Scope private fields to the selected astronaut. This local demo has no per-user authentication. |
| `note` | Preserve the original column in the immutable CSV. Exclude it from runtime DTOs, queries and analysis because it can describe engineered scenarios. |

Reject malformed headers, extra or missing columns, invalid dates, unmatched subject/metric/context combinations and duplicate IDs. An exact already-published row can be treated as a retry. A repeated ID with different normalized fields is an error. Blank nullable fields never become zero. SQLite preserves the original decimal text. Observation DTOs use a JSON number or null. Retain CO₂ partial pressure in `mmHg` and derived concentration in `ppm` as related observations. Use partial pressure as the primary CO₂ signal. For any displayed conversion, label the assumed 760 mmHg cabin pressure and avoid counting both as independent evidence.

## Replay state

`ReplayState = {dataset_id, revision, status, cursor_utc, mission_day, visible_count, speed}`. Status is `PAUSED`, `RUNNING` or `COMPLETE`. Speed is real seconds per 24 simulated hours. It accepts 5 (Slow), 2 (Normal, default), or 0.5 (Fast). Increment revision on each published state change. The initial cursor is `2040-02-14T23:59:59Z` and the terminal cursor is `2040-03-30T23:59:59Z`. All dataset timestamps have whole-second precision. Counts include missing rows.

| Event or command | Behavior |
| --- | --- |
| Bootstrap or `RESET` | Publish exactly the 6,252 history rows at Day 45 and enter `PAUSED`. Reset removes only rows registered to this mission in `replay_observations`. It preserves speed, the pinned future checksum, historical rows, and unrelated records. |
| `PLAY` | From `PAUSED`, enter `RUNNING`. A monotonic backend timer advances up to 24 simulated hours per tick and publishes every due row in one transaction. |
| `PAUSE` | Stop scheduled advancement and keep the last committed cursor. |
| `NEXT_EVENT` | While paused, advance to the earliest remaining timestamp and publish the full group. The endpoint never hands the timestamp to the browser before committing. |
| `NEXT_DAY` | While paused, advance to the end of the next UTC mission day, publishing all intervening rows. |
| `SET_SPEED` | Requires a supported `speed`. While playing, start a new timer interval at that speed. |
| Terminal day | On reaching the terminal cursor, enter `COMPLETE` with 12,491 records. A next-event call while paused after the final group can close the remaining interval to Day 90 end. |
| Restart | Restore the persisted cursor and rows. A persisted `RUNNING` state becomes `PAUSED`. Wall-clock downtime never advances the mission. |

Serialize replay writes and check `expected_revision` within the write transaction. Due timer updates and pause/reset obey the same boundary. Return `409` for stale revisions and incompatible transitions. A read request or page load never drives playback. Define operational reset and completion checks without exposing the future schedule in the API.

## Endpoints

| Method and path | Request and response |
| --- | --- |
| GET `/api/health` | `{status, database_ready, dataset_ready}`. Return `200` after a successful SQLite schema/readiness check. `dataset_ready` is true when a verified historical import and its replay state are committed. On SQLite failure return `503` with `{"status":"unavailable","database_ready":false,"dataset_ready":false}`. |
| GET `/api/mission` | Mission snapshot `{revision, cursor_utc, mission_day, replay_status, synthetic, crew_summaries, crew_readings, cabin_readings, cabin_latest_missing, insights}`. Summaries use Crew and Observation DTOs. Native monitoring adds the fields below without changing those fields. |
| GET `/api/crew` | `{items: Crew[]}`, where Crew is `{crew_id, display_name, role}`. |
| GET `/api/crew/{crew_id}` | One Crew profile, including `age_years` and `activity_pref`. |
| GET `/api/observations` | Optional `crew_id`, `scope`, `metric`, `context`, `from_utc` and `to_utc`, plus `limit` (default 100, maximum 500) and `cursor`. Return `{revision, cursor_utc, items, next_cursor}`. This serves histories and the replay timeline. |
| GET `/api/observations/latest` | Same filters as history without `cursor` or `limit`. Require `crew_id` or `scope=cabin`. Return `{revision, cursor_utc, items, latest_missing, next_cursor: null}`. `items` contains the last valid reading per metric. `latest_missing` contains the newest observation per metric when it is missing. |
| GET `/api/crew/{crew_id}/analysis` | Optional `metric` and `context` filter indicator detail in a subject-scoped native analysis snapshot (below). |
| GET `/api/replay` | `ReplayState` plus `historical_days`, `mission_days`, `playback_error`, and `latest_activity`. Activity summarizes only published replay-owned rows on the current day and is null at Day 45. |
| POST `/api/replay` | Send `{command, expected_revision}` using the uppercase commands above. Add `speed` for `SET_SPEED`. Returns the same view as GET after commit. |
| GET `/api/data` | `dataset_id`, `version`, `mission_type`, `provenance`, `mission_start_utc`, `mission_days`, `historical_days`, `cabin_total_pressure_assumed_mmhg`, `initialized`, `imported_at_utc`, `historical_count`, `historical_missing_count`, `source_status`, `replay`, `metrics`, `references`. `source_status` is `VERIFIED`, `UNAVAILABLE`, or `INVALID` for the current startup check. Metrics include source dictionary fields and `scope`. References use the source catalog columns. |

Mission summaries include the latest valid shareable observation per crew member and the latest valid cabin readings. `cabin_latest_missing` contains any newer missing samples. Replay activity fields are `mission_day`, `observation_count`, `crew_count`, `cabin_count`, `first_utc`, and `last_utc`. Timestamp bounds are null for a day with no published rows. The original string array `insights` is retained empty for backwards compatibility. Use the structured native findings described below. Use `scope=cabin` for cabin history. Date ranges wholly after the cutoff return empty lists. Time filters require whole-second UTC.

Observation responses use the normalized CSV fields except `note`. Sort history and timeline by `(timestamp_utc, observation_id)` ascending with a stable continuation token bound to filters and revision. Time filters are inclusive and the replay cutoff always takes precedence. Cabin feeds and mission summaries exclude private check-ins. Access to private check-in fields requires a person query with an explicit crew ID. A cross-crew insight may show an aggregate opted-in count and cabin observation IDs, without private text, individual scores, participant IDs or flags.

Return a shared error envelope `{error: {code, message}}`, with `404` for unknown crew, `422` for invalid filters or commands, and `409` for conflicts. Read responses include a revision and cursor where relevant so clients can detect drift across requests. Treat changed pagination revisions as conflicts and restart paging from the same filter. Mission routes return `503 dataset_unavailable` before a successful bootstrap or `503 database_unavailable` when storage cannot be read. A failed source recheck leaves an earlier verified import available and surfaces the issue in `source_status`.

## Native analysis

`GET /api/mission` adds `analysis_available`, nullable `analysis_method_version`, `crew_monitoring` keyed by crew ID, `health_findings` and `cabin_findings`. Each crew summary contains `status`, `headline` and `coverage`. The API returns at most one concise concern per crew member from shareable evidence; zero or more cabin findings are separate. If analysis fails, the three collections are empty and `analysis_available` is false; the existing observations remain available.

`GET /api/crew/{crew_id}/analysis?metric=resting_heart_rate&context=rest` returns
`{crew_id, revision, cursor_utc, method_version, provenance, status, coverage, baselines, indicators, blood_pressure, findings, cabin_findings}`.
Use a known person metric and context, or omit filters for all detail. Filters narrow personal arrays and the associated findings; status, coverage and paired BP still apply to the full selected profile. Cabin findings match the mission snapshot. Unknown crew returns `404 unknown_crew`; unknown or incompatible metric scope returns `422 invalid_filters`. Failure of just the subject analysis returns `503 analysis_unavailable`. The browser cannot set a cutoff.

| Type | Fields and behavior |
| --- | --- |
| Monitoring | `STABLE`, `WATCH`, `FLAGGED`, `INSUFFICIENT_DATA`. Coverage includes `current_groups, required_groups, total_groups, sufficient`; a supported concern is retained alongside limited coverage. |
| Baseline | `metric, context, unit, kind, availability, median, mad, effective_mad, valid_sample_count, distinct_days, required_days, calibration_start_utc, calibration_end_utc`. Availability is `AVAILABLE`, `INSUFFICIENT_DATA` or `NOT_APPLICABLE`. |
| Indicator | `metric, context, current, latest_valid, availability, age_hours, freshness_hours, status, difference, absolute_difference, relative_percent, modified_z, direction, rolling_median, trend_direction, slope_per_day, trend_window_days, recent_days, persistent_days, strong_days, unusual_ids`. Current and latest valid can differ. Availability is `CURRENT`, `MISSING`, `STALE` or `UNAVAILABLE`; unsupported comparisons and context-only scores are null. `unusual_ids` are actual strongly deviating continuous observations within the last 45 days; they never include missing or unpublished samples. |
| Evidence | `observation_id, metric, timestamp_utc, value, unit, source, context, quality, provenance`. Value may be null for an explicitly missing current record. |
| Finding | `rule_id, type, crew_id, status, title, explanation, uncertainty, verification, evidence, shared_report_count, habitat_comparison`. Types: `SINGLE_METRIC`, `CONTEXTUAL`, `CABIN`, `SHARED_CABIN`, `DATA_QUALITY`. Nullable habitat comparison includes metric, unit, recent and historical medians, effective MAD, modified Z and hourly window coverage. |
| Blood pressure | `blood_pressure` is empty or the two latest valid components in systolic/diastolic order. A pair requires the same timestamp, source and activity context. |

Responses inherit the inclusive UTC replay snapshot and describe synthetic observations. Individual private inputs are absent from Mission Overview findings. A consolidated cabin finding can show only the eligible aggregate opt-in count and cabin evidence. Thresholds, cadence and limits are documented in the [methodology](HEALTH_INTELLIGENCE_METHODOLOGY.md).
## Data & Science comparison

`GET /api/data/personalization?bpm=70` is a read-only educational endpoint. `bpm` is a whole number from 40 to 120 with a default of 70; this is an interaction range, not a medical limit. The response is `{dataset_id, method_version, hypothetical_bpm, comparisons}`. Comparisons are ordered by crew ID and include `crew_id, display_name, median_bpm, mad_bpm, effective_mad_bpm, distinct_days, absolute_difference_bpm, modified_z, strength`. The strength is `below_moderate`, `moderate`, `strong`. Strength and other unavailable comparison values are null when the reference is insufficient.

The endpoint uses shareable resting heart rate from Days 1–45 within the normal replay cutoff. It returns no observation rows, timestamps or private self-reports. The hypothetical reading is never stored or used to assign a monitoring state. Invalid query values return 422 in the common error envelope; an unavailable dataset uses the existing readiness error.

## ASTRA Companion

| Method and path | Request and response |
| --- | --- |
| GET `/api/companion/status` | `{model, runtime_reachable, model_available, ready, issue}`. Returns HTTP 200 for both ready and unavailable states. `issue` is null when ready, or `ollama_unavailable`, `model_missing` or `invalid_runtime_response`. Readiness checks the listening runtime and the approved locally installed tag. |
| POST `/api/companion/chat` | Send `{message, history}`. History is optional and contains chronological complete `{role, content}` pairs (user then assistant). Success returns `{text, truncated}`. `truncated` is true if Ollama reached the generation limit. |

Reject extra fields, unsupported roles, blank messages, more than 12 history messages, user messages over 2,000 UTF-8 bytes, and more than 6,500 combined UTF-8 bytes for message and prior content. Use the common `{error: {code, message}}` envelope. Return 422 for invalid input, 429 `companion_busy` for overlapping generation, 503 `ollama_unavailable` or `model_missing`, 502 `invalid_runtime_response`, and 504 `inference_timeout`.

ASTRA sends only the recreational system prompt and the supplied conversation to the installed local `qwen3:4b-instruct-2507-q4_K_M` in Ollama. Status uses a 2-second socket timeout. Generation uses a 75-second socket timeout, 8,192-token context, and a 384-token reply limit. Responses are delivered whole. The app does not persist chat content or include it in mission or health APIs.
