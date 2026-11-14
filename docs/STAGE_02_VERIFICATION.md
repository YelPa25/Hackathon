# Stage 02 verification

## Import and preservation

The reviewed bundle `ASTRA-SYN-90D-01` v1.0.0 contains 4 synthetic crew profiles, 18 metrics and 12,491 observations across 90 UTC days. Source CSV counts match `validation_report.json`. The 6,252 historical rows include 18 missing readings. The 6,239 future rows include 49 missing readings. The archive's IDs are the disjoint union of both replay partitions. All 17 source files matched their pre-stage SHA-256 digests. The manifest has no embedded checksums. The startup importer uses the companion checksum list for the five files it reads.

The live SQLite file is `backend/var/astra.sqlite3`. Tables are `crew`, `datasets`, `metrics`, `observations` and `replay_state`. It contains 6,252 observations dated from `2040-01-01T00:00:00Z` through `2040-02-14T23:00:00Z`. The cursor is paused at `2040-02-14T23:59:59Z`. The source decimal strings and `SYNTHETIC` provenance are preserved. Missing readings use SQL null and retain their source quality and reason.

## Results

| Check | Result |
| --- | --- |
| Backend regression | PASS. In `backend`, ran `uv run --locked --offline --python $astraPython --no-managed-python pytest -q` with the installed Windows Python 3.12.10 path from the README. 15 tests passed. Coverage includes CSV row-by-row fidelity, crew, privacy, valid versus missing, paging, checksum failures, a forced transaction failure, and restart. |
| Frontend lint | PASS. In `frontend`, ran `npm.cmd run lint`. |
| TypeScript | PASS. In `frontend`, ran `npm.cmd run typecheck`. |
| Production build | PASS. In `frontend`, ran `npm.cmd run build`. The output contains no source CSVs. |
| API and SQL boundary | PASS. Direct and Vite-proxied health returned ready. Day 46 history returned an empty list. The future, full archive and evaluation CSV paths returned 404 on both servers. SQLite contained no rows after Day 45. An isolated test inserted a late row and confirmed it was still excluded from reads. SQLite `PRAGMA quick_check` returned `ok`. |
| Browser data and navigation | PASS. At 5180, Mission Overview showed four crew members and four cabin readings. Crew Health updated when selecting Maya Vega and displayed 45 dated sleep observations ending on Day 45. Mission Replay showed Day 45 paused and future observations hidden. Data & Science showed the version, 18 metrics and the source catalog. |
| Browser outage and restart | PASS. Stopped FastAPI, saw Backend unavailable and an inline error with Retry, restarted FastAPI and recovered via Retry. SQLite readiness, the original import timestamp, row count and replay cursor were verified after restart. |

Use the [Windows startup guide](../README.md) to reproduce the checks. Replay playback and personalized analysis are scheduled for later stages. Stage 02 uses a measurement table for the selected metric. The browser pass used the local development console. A full network-adapter disconnection was not run.
