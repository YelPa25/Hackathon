# ASTRA 2.0 architecture

ASTRA is an offline, non-clinical prototype for a fictional four-person transit. It opens at the close of Day 45 with 45 days of recorded history. Crew can replay Days 46–90 and inspect how personal measurements and cabin conditions change. All mission readings and crew profiles in this release are research-informed synthetic data. The dataset's NASA and CDC references explain measurement choices and published context. They do not validate the synthetic individuals, a clinical decision process, or correlations as causal effects.

## Boundaries

- React, TypeScript, Vite, Tailwind CSS and Recharts render the four screens. Their API client reads backend DTOs. Browser state holds presentation preferences and requested filters.
- Python 3.12, FastAPI and Pydantic validate requests and ingest source data. Use Python's SQLite driver and SQL migrations. A single local backend owns the mission clock, measurements and analysis. The normal demo listens on loopback and uses the built frontend with same-origin API requests. During development Vite proxies the API locally.
- The dataset directory is immutable runtime input, outside the frontend's public assets and static mount. Configure its path for the checked-out layout. Startup reads the crew profiles, metric dictionary, manifest and historical partition. It verifies the allowlisted source files before publication. Only the replay service can read the future partition and select the next scheduled batch. Observation, baseline, trend and UI services have no source-file fallback. Distribute no runtime support for the evaluation CSV, full archive, generator, workbook or review summaries. Use selected validation metadata only for static provenance documentation, without future aggregates or event labels in live screens.
- SQLite holds dataset metadata, crew, dictionary, a singleton replay state and revealed observations. Add a stable source ID key and indexes for timestamp and per-subject metric queries. A lightweight source adapter validates the CSV and maps it to internal DTOs. Keep future rows in the source partition until the replay writer is about to publish a batch. A read-time cutoff independently protects every query.
- Deploy no cloud service. Use installed Windows Python 3.12 with a venv. If using uv, select the installed interpreter with `--no-managed-python`. Network access is for initial setup and optional official source links. The app requires no LLM. Any later approved AI access must use the same cutoff and privacy rules.

## Data flow

1. Atomically install verified metadata and historical rows, initialize the cursor to Day 45 UTC close, and start paused. Persist checksums for runtime inputs. On restart, reopen the existing dataset state and pause any prior playback. Failing validation leaves the last committed state available and reports a dataset error. A bootstrap failure blocks mission reads.
2. Replay chooses a UTC cutoff, parses and validates only the rows needed for publication, then writes revealed rows and advances the cursor in one transaction. Use the same transaction for reset. A failed write leaves the prior cursor and observations intact. Repeating an operation with a stale revision fails before writing. Group simultaneous rows in one batch and use source IDs for ties.
3. Read the replay cursor and observations in one database snapshot. The common read service adds `timestamp_utc <= cursor` even though only published rows belong in SQLite. Mission cards, cabin summaries, crew charts, insights and any later export or AI context use that service. Paginated reads guard against revision changes. The browser can poll replay state and refresh affected panels once per new revision.
4. Use fixed Day 1–45 references keyed by crew, metric and activity context. Compute robust references from valid visible rows. Use only revealed data for trends, current comparisons and any cabin association. Keep the analysis deterministic and independent of the frontend. Compute on demand for this dataset size. Assess sufficiency and show meaningful gaps. Store policy settings as versioned code or local configuration, with no generator targets or event truth inputs.

## Screen specification

Use one shell with exactly four primary navigation entries. Use premium dark navy surfaces, restrained cyan accents, high-contrast text and amber for follow-up or measurement quality. Every chart names the metric, unit and UTC range, marks gaps and uses accessible labels. Keep the current mission day and synthetic status visible. Support keyboard navigation and a readable single-column layout on narrow screens.

| Screen | Information and actions |
| --- | --- |
| Mission Overview | Show the simulated clock, playback state, four crew summaries, latest available cabin metrics and concise findings. Distinguish missing and stale data from valid readings. Link directly to a selected astronaut in Crew Health. |
| Crew Health | Select an astronaut and metric or activity context. Show the latest reading with time, source and quality, visible history, the personal reference and a short explanation of any change or coverage gap. Keep private self-reports in the selected profile's view. |
| Mission Replay | Start at Day 45 and show play, pause, next timestamp, next day and reset. List revealed events in chronological order. Show that future records are locked without exposing their contents, timestamps or scenario labels. Speed selection can follow core verification. |
| Data & Science | Show dataset ID, version, synthetic provenance, methodology, limitations, metric dictionary and reviewed NASA/CDC source links. Explain space radiation, isolation and confinement, distance from Earth, altered gravity, and hostile or closed environments. Keep this view useful offline. |

Scope ends at measurements, trends and explainable findings. Guided medical assessment, medical cases and checklists, Earth reporting and communications, biometric emotion recognition, mandatory LLMs and unvalidated disease prediction are excluded.
