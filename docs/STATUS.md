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
