# ASTRA 2.0 status

## Stage 00

Documentation complete. Implementation starts after Stage 00 review.

- Read the full `ASTRA_2_0_PROJECT_BRIEF.md`. The standalone Downloads copy and the one in `Downloads/ASTRA_2_0_Clean_Start_Pack/ASTRA2` had matching SHA-256 hashes.
- The working project contains `ASTRA_90day_dataset_v1` directly under its root. It matches the copy under the clean-start pack's `data-source` directory file for file. All 16 files listed in `SHA256SUMS.txt` matched their hashes. The contract documents both layouts through `ASTRA_DATASET_DIR`.
- Read the dataset README, import notes, manifest, validation report, metric dictionary, crew profiles and source catalog. Checked both replay CSVs without loading the evaluation-only labels. The package describes 90 fictional UTC days, January 1 through March 30, 2040, four crew members, 18 metrics and 12,491 synthetic observations, including 3,851 person and 8,640 cabin records.
- Independently checked 6,252 historical and 6,239 future rows against UTC partition boundaries, mission-day consistency, unique IDs across both files, metric units, quality, finite valid values and blank missing values. Found 18 missing rows in history and 49 in future. Timestamps are nondecreasing in both files. Same-time groups reach 16 entries and source ID order varies within groups, so the replay contract specifies a stable tie order.
- Verified Python 3.12.10 from the existing Windows installation. Application startup, offline rehearsal and replay tests are pending implementation.

No Stage 00 blockers. Stage 01 needs review of the local API skeleton and startup plan before implementation. Git checkpoints and remote changes require explicit approval.

## Stage 01

Implemented the local application foundation in ASTRA-Hackathon. The backend has a FastAPI application factory, environment settings, developer-only loopback CORS, an empty SQLite file and a live health endpoint. The frontend adds React, TypeScript, Vite, Tailwind CSS, React Router and local Lucide icons. Recharts is pinned for later use. The four screens share a responsive navigation shell and poll health through Vite. Each screen shows its own empty state.

- Frontend: [ASTRA console](http://127.0.0.1:5180/).
- Backend: [FastAPI health](http://127.0.0.1:8050/api/health).
- SQLite: `./backend\var\astra.sqlite3`.
- Defaults use 8050 and 5180 because this machine already had listeners on 8000 and 5173. The package installs use Node v26.13.1, npm 11.20.0, uv 0.12.10 and installed Python 3.12.10.

| Check | Result |
| --- | --- |
| Backend install | PASS. In `backend`, ran `uv lock --python $astraPython --no-managed-python` and `uv sync --locked --python $astraPython --no-managed-python` using the installed Python path in the README. |
| Backend tests | PASS. Ran `uv run --locked --offline --python $astraPython --no-managed-python pytest -q`. Six tests passed, covering database creation, empty schema, loss after startup, invalid SQLite, response shapes, private routes and local CORS. |
| Frontend install | PASS. Ran `npm.cmd install --no-audit --no-fund`, then verified `npm.cmd ci --no-audit --no-fund` from the generated lockfile in a fresh temporary directory. |
| Frontend type-check and build | PASS. Ran `npm.cmd run build`, which ran `tsc --noEmit` and produced the Vite bundle. |
| Frontend lint | NOT RUN. Stage 01 has no configured linter. |
| Browser behavior | PASS. Verified all four route headings, keyboard activation and current navigation state. The skip link focused the main content. The mobile menu opened with the keyboard and closed with Escape. Widths 1366, 390 and 320 CSS pixels had no horizontal overflow. |
| Connectivity | PASS. Started FastAPI with `uv run --locked --offline --python $astraPython --no-managed-python uvicorn --factory astra.main:create_app --app-dir src --host 127.0.0.1 --port 8050` and Vite with `npm.cmd run dev`. Direct and proxied health returned HTTP 200 with `database_ready: true` and `dataset_ready: false`. The same tab showed Backend unavailable when FastAPI stopped and restored Backend connected and SQLite ready after restart without refresh. |
| Dataset isolation | PASS. 100 HTTP probes across FastAPI and Vite rejected CSV paths, including the hidden future and evaluation files, static paths and Vite filesystem paths. Six later-stage API endpoints returned 404. SQLite contained zero tables. The frontend build contained no CSVs. SHA-256 matched before and after for all 17 source files. |
| Design skill gate | FAIL 12 on the final build. The site checker expected a full-screen hero, screen-aligned sections, one hero heading, a call to action, a showcase moment and a full-width container. It also flagged sidebar wordmark alignment and card headings. Warnings covered a heading, local system-font fallbacks and share metadata. The Stage 01 app keeps the requested compact sidebar, real status panels and data-empty screens. Interactive browser checks passed separately. |
| Full disconnection test | NOT RUN. The local backend was launched with offline dependency resolution and the frontend uses installed packages and same-origin requests. The Windows network adapter was not disconnected. |

Clarified the Stage 01 health codes and keys in the version 1 contracts. The dataset remains at the project root and `ASTRA_DATASET_DIR` is available for Stage 02. The project had no Git repository at start and contains no Git metadata. No stage checkpoint or remote was created.

Stage 01 is ready for functional review. Stage 02 awaits approval and begins with validation and historical ingest under the approved data boundary.

## Stage 01 correction pass

- Audited all 12 design findings in the [Stage 01 verification report](STAGE_01_VERIFICATION.md). Fixed sidebar label alignment, shared workspace edges, card header hierarchy, spacing and keyboard focus when a mobile navigation link closes the menu. The navy/cyan console retains its four empty-state screens.
- Final design checker result was `GATE: OPEN 11 (rounds used up)`. The wordmark failure cleared. The remaining checks apply landing-page layout rules to the workspace and its empty states. The report gives the rationale for every finding. No waivers were applied.
- SQLite has zero tables by design. Stage 01 initializes the database file and probes it. Stage 02 historical ingest introduces the application schema. Verified live health and a read-only inspection of the database. All 17 source file hashes matched before and after the pass.
- PASS on `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run build` and six backend tests via `uv run --locked --offline --python $astraPython --no-managed-python pytest -q`. Browser checks passed for all routes, empty states, active links, focus, responsive widths, and backend outage/recovery. Browser logs showed no warnings or errors.
- NOT RUN for full network disconnection. Connectivity testing stopped and restarted FastAPI only.

No functional blockers remain for Stage 01 review. Stage 02 awaits approval.

## Stage 02

Implemented transactional historical ingest and connected all four screens to the stored mission data. Startup installed schema version 1 in `backend/var/astra.sqlite3`. The verified import contains 6,252 observations, four crew profiles, 18 metrics and 18 explicitly missing readings. The replay cursor is paused at `2040-02-14T23:59:59Z`. An unchanged bundle reuses the committed import.

- Confirmed that all 17 source file hashes match their pre-stage values.
- Passed 15 backend tests, frontend lint, TypeScript and production build. See the [Stage 02 verification report](STAGE_02_VERIFICATION.md) for exact commands and browser checks.
- The live frontend on 5180 and FastAPI on 8050 serve Day 1–45 only. Verified crew and metric selection, cabin readings, Day 45, outage and Retry recovery, and persistence after restart.

- Polished metric labels and reading typography across the cabin and crew cards, history selector, and metric dictionary. Frontend lint, type check, and production build passed. Verified the cabin and crew labels and switched the history to SpO₂ in the browser.

Stage 03 awaits approval. It will add chronological replay controls and publication through the existing cutoff boundary.


## Stage 02.5

Stage 02 was checkpointed locally at bb5b2e1 before the Crew Health changes. Crew Health now groups primary readings into six compact cards with keyboard-accessible details. Secondary metrics stay accessible and link to history. The chart uses 7, 30, or 45 UTC calendar days of existing API data and follows all continuation tokens. Existing heart-rate metric names select resting, exercise, or recovery observations separately.

Frontend lint, TypeScript, and production build passed. An in-app browser pass verified all four crew, indicator and range changes, reading details, table expansion, missing samples, the other three screens, and layouts at 1440, 834, 390, and 320 CSS pixels. See the [Stage 02.5 verification notes](STAGE_02_VERIFICATION.md#stage-025--crew-health). The backend, database and dataset were only read for verification.

## Stage 03

Implemented backend-owned chronological replay using the 6,239 original future CSV observations. SQLite schema version 2 upgrades the existing database in place. Play, Pause, Resume, Next Day, Next Event, Reset Replay and three speeds are available in Mission Replay. The frontend polls the backend and refreshes the published snapshots.

- All 21 backend tests passed. Frontend lint, TypeScript and the production build passed.
- Verified the browser workflow in isolation through Day 51, including pause and resume, disconnection, restart, cross-page updates, and reset. The default database is still at Day 45 with 6,252 observations.
- Verified all 17 source file hashes. A Day 46 query returned no observations at the live Day 45 cursor, and direct and proxied access to private CSV paths returned 404.
- Fixed Detailed records collapsing on a playback tick. An isolated browser run confirmed the table stays open as rows refresh, stays closed when dismissed, and can be reopened by keyboard. Frontend lint, type check, and production build passed.
- See the [Stage 03 verification report](STAGE_03_VERIFICATION.md). Stage 03 is ready for review. Stage 04 awaits approval.

## Research Prototypes · Windows live capture

Research Prototypes supports opt-in webcam preview and microphone sampling. The optional loopback service starts from the repository root with `.\face_speech\live\Start-Research.ps1`. CPU models execute in a Windows AppContainer and use verified local assets. The experimental page uses the participant's wall-clock timestamps. See [live research capture](LIVE_RESEARCH_CAPTURE.md) for setup, workflow and verification.

The 49 prototype tests, 21 Core tests, frontend lint, TypeScript and production build passed. Chrome exercised both real models with generated test streams, valid calibration windows, device release and responsive layout. Physical device capture and full live calibration remain a participant check. The 16 listed source checksums matched.

Capture follow-up: the browser and broker now recover from a dropped request or lost response without clearing calibration. The chart and selector have separate bounds, and the voice readout explains when only the latest sample is unusable. Backend tests (21), frontend lint, TypeScript, build, and focused browser capture and layout checks passed. See [capture reliability and chart spacing](LIVE_RESEARCH_CAPTURE.md#capture-reliability-and-chart-spacing).

The dashboard links now reopen the published charts. Paused live sessions resume their calibration in the same browser tab, and either modality's completed calibration can be saved and reused in that browser. Pipelined speech collection produced new windows 15 seconds apart in Chrome. The shorter camera and speech windows changed the extracted measurements or input quality in fixture trials, so the standard durations remain in use. Browser workflow, both calibration round trips, the 21 Core tests, 49 teammate tests, lint, the production build and all 16 source checksums passed. See [session restore and calibration timing](LIVE_RESEARCH_CAPTURE.md#session-restore-and-calibration-timing).

The Facial and Voice panels display “Last saved sample” in the sample section title and playback status. Verified both panels in the running browser and passed focused ESLint.

## Stage 04 · Native personalized health intelligence

Implemented on `feature/native-health-intelligence` from `ff61256`. The engine reads the same replay snapshot as existing observation queries. It uses fixed historical references, analyzes only revealed data, and never writes to the database. Mission Overview shows shareable statistical findings and separate cabin evidence. Crew Health shows personal references, verification suggestions and source values on the existing charts. Data & Science explains the method and its limits. Research Prototypes stays independent. No new dependencies, models, routes in the sidebar, schema migrations, or clinical rules were added.

- **Backend: PASS.** `uv run --locked --offline --python $astraPython --no-managed-python pytest -q -s`: 43 tests, including all 46 daily replay positions, same-day future row exclusion, consent, fixed references, numeric stability, analysis-only failure, restart and reset.
- **Frontend: PASS.** `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run build`.
- **Browser: PASS.** Isolated headless Chrome on ports 15184/18054 verified the four profile references, real charts, continued updates during replay, preserved range and expanded records, reset, one shared cabin advisory on Day 62, the raw-chart fallback, Data & Science, and 390px layout. Synthetic facial and voice demos ran with live capture blocked. Physical camera and microphone capture were not repeated.
- **Research regression: PASS.** 49 tests in the separate installed prototype environment. Neither research workers nor XGBoost nor Qwen were needed for Core.
- **Integrity: PASS.** All 16 original source checksums matched. The development SQLite database was not used for test writes. No commit, merge or push.

The replay yielded 184 crew snapshots: 78 Stable, 89 Watch, 16 Flagged and 1 Insufficient data. One consolidated cabin advisory appeared at Day 62 close. Some findings recur or occur outside annotated scenarios; the detection policy has no clinical validation. Median/p95 times were 44.4/61.0 ms for crew analysis and 70.7/94.7 ms for the mission snapshot.

See [methodology](HEALTH_INTELLIGENCE_METHODOLOGY.md) for exact thresholds and supported metrics. See [verification and Windows startup](STAGE_04_VERIFICATION.md) for the historical audit, synthetic comparison, browser checks and a temporary database walkthrough. Next dependency: review Stage 04 before any checkpoint or subsequent work.
### Live dashboard verification

The Vite page on port 5180 was serving Stage 04 while the FastAPI process on port 8050 still had the previous backend loaded. Mission reads returned HTTP 200 without analysis fields and the crew analysis route returned HTTP 404. The backend was restarted from the current checkout using the existing database. Replay was paused at Day 45 before and after the restart, with revision 305 and 6,252 observations. The proxied API then returned the Stage 04 analysis. In the running browser, Mission Overview showed four Stable badges for shareable readings. Daniel Okafor’s Crew Health showed Watch on the personal snapshot and a 66 bpm resting heart rate reference. Restart FastAPI after changing backend code when running it without automatic reload.
## Stage 05 · ASTRA Companion

Added an optional recreational chat page and a separate FastAPI router for the existing Ollama installation. The service uses the exact locally installed `qwen3:4b-instruct-2507-q4_K_M` model (ID `0edcdef34593`) on Ollama 0.40.16. No weights or runtime were installed. Chat sees a recreational system prompt and the conversation supplied by the user. The browser holds the transcript in memory across route changes. New Conversation, a reload, or leaving the app clears the session. Each request uses at most six earlier complete turns within the API byte budget.

- **Real inference PASS.** Qwen produced a Titan story, a five-question astronomy quiz, an ocean fact and a word-game reply. In both the API and browser runs it recalled a prior turn. A browser privacy test exposed an unnecessary assurance in early prompt wording. The final prompt was checked with real requests about health records and dashboard readings. Both replies denied access.
- **Performance measured.** With the model unloaded, the 264-token story returned in 5.81 seconds, including 4.29 seconds to load. Warm replies took 0.03–0.60 seconds. Ollama reported 3.9 GB resident, 8,192 context and 100% GPU placement. The RTX 5090 sample reached 3,965 MiB total GPU memory and 87% utilization. During the story, automatic replay advanced to Day 46 and the mission and crew analysis returned in 78 ms combined. Measurements used a temporary SQLite database.
- **Offline and outage PASS.** The browser completed real multi-turn chat against an isolated instance of the installed runtime with cloud disabled, external HTTP proxies directed to an unavailable loopback port, and the test backend restricted to loopback. The Windows network adapter stayed enabled. Stopping the isolated Ollama listener showed the unavailable state and preserved the transcript and draft. Core mission and analysis responses and both Research Prototypes panels still worked. The main Ollama listener was unaffected.
- **Browser PASS.** Checked starters, Enter and Shift+Enter, the visible generation state, a simulated timeout followed by successful real retry, Copy, navigation with the transcript retained, New Conversation, and 390-pixel layout. The chat returns whole replies. Physical camera and microphone capture were outside this check.
- **Automated PASS.** 72 backend tests, including 29 Companion tests. All 49 facial and speech regression tests plus frontend lint, TypeScript and production build passed. All 16 original dataset checksums matched after testing.
- **Local checkout.** Before editing, verified a local ZIP checkpoint of all 24 Stage 04 working files, including the prior sample-label update, against base `ff61256`. It is under `%LOCALAPPDATA%\ASTRA\checkpoints\stage04-20261115T020307369022Z.zip`. The current branch remains `feature/native-health-intelligence`. Stage 05 is ready for review. The running app serves [ASTRA Companion](http://127.0.0.1:5180/companion) with its original database still paused at Day 45, revision 395.

## Stage 06 — Scientific foundation and data transparency

Data & Science now separates the installed synthetic bundle inventory from the live replay cutoff. It shows the five NASA hazards with ASTRA’s scope, the native method, all 18 indicators, six reviewed references, revisioned verification evidence, and development-time ChatGPT/Codex attribution separate from optional onboard Qwen. The educational comparison runs the existing baseline and scoring functions on shareable Days 1–45 resting heart rate. The input is hypothetical and is never written or used by monitoring. No native analysis policies, replay code, schema, or source files changed.

- Backend: `uv run --locked --offline --python $astraPython --no-managed-python pytest -q` passed 73 tests. The new test verifies actual reference medians, same-input differences, validation, privacy boundaries, and stability across replay.
- Frontend: `npm.cmd run lint`, `npm.cmd run typecheck`, and `npm.cmd run build` passed.
- Browser: checked 1920×1080, 1366×768 and 390×844 with no horizontal overflow. Verified section links, keyboard slider and method disclosure, crew selection, metric and source disclosures, and all 18 metric definitions. In an isolated SQLite database, Next Day published Day 46 with 6,393 observations and updated the already-open science page without closing the methodology disclosure or clearing selections. Reset restored Day 45 and 6,252 observations. The live workstation stayed at its saved paused Day 67 cursor after restart.
- Dataset: 12,491 synthetic observations for four fictional crew over 90 days, 6,252 initial and 6,239 replay records. The 18 missing readings shown on the page are limited to Days 1–45. All 16 hashes listed in the original checksum file matched after verification. Hidden CSV and evaluation content remain outside normal serving and API access.
- Validation shown on the page is labeled as recorded evidence from checkpoint `e1480d0` (including 72 backend tests and 49 research prototype tests), rather than a live execution. Stage 06 did not re-run real Qwen generation or physical camera/microphone capture; Companion readiness still reported available. This is synthetic software verification, not clinical validation or flight qualification.

Next: user visual review before Stage 07. No commit, push or merge.
