# Stage 03 verification

## Data and verification

The Stage 02.5 checkpoint is `232b9be`. The full source has 12,491 observations (6,252 through Day 45 and 6,239 in the private replay partition). The first partition has 18 explicit missing values, and the replay partition has 49. The provided checksum list and all 16 files it covers matched their originals after testing.

The default app uses `backend/var/astra.sqlite3`. It was migrated in place and remains paused at `2040-02-14T23:59:59Z` with 6,252 observations. The backend and frontend health checks succeeded at ports 8050 and 5180.

| Check | Result |
| --- | --- |
| Backend | PASS. `uv run --locked --offline --python $astraPython --no-managed-python pytest -q` in backend with the installed Python 3.12 interpreter. 21 tests passed. |
| Source equivalence | PASS. Tests advance through each of the 45 replay days, verify daily and cumulative counts, and compare every published future SQLite row with its exact normalized source fields. The tests cover missing values, timestamp ties, UTC order, concurrent revision conflicts, and the Day 90 terminal state. |
| Reset and restart | PASS. Tests verified preservation of non-replay records, an in-place schema upgrade, recovery from invalid source and mid-batch failure, restart from a running state, and pause/resume. |
| Frontend | PASS. `npm.cmd run lint`, `npm.cmd run typecheck`, and `npm.cmd run build`. The production output contains no CSVs. |
| Browser replay | PASS. Isolated frontend on 5183 and backend on 8053. Opened Day 45 and inspected Hana's sleep chart. Next Day published 141 Day 46 observations (45 crew and 96 cabin). The chart's newest sample changed from 14 February to 15 February. Verified Next Day, Next Event, Pause at Day 50, Resume, and a live Mission Overview refresh to Day 51. Data & Science displayed the revealed count. |
| Browser restart and reset | PASS. Stopped the isolated API at Day 51, saw connection loss and disabled controls, restarted the same database with 7,081 observations, and reset to Day 45. The health chart and overview returned to the historical cutoff. The default development database was left at its original cursor. |
| Data boundary | PASS. Tests checked future queries on every replay day. A live Day 46 query at Day 45 was empty on both servers. Direct and proxied requests for the future, archive and evaluation CSVs returned 404. |

Playback uses daily timed increments. Next Event allows finer steps at each recorded timestamp, including complete simultaneous groups. Verification used one local FastAPI worker. Use the [README walkthrough](../README.md#verify-replay) to reproduce the browser run.

## Detailed records during playback

Reproduced the table closing on a live data refresh. Crew Health now keeps the disclosure state when the history table is replaced. Verified successive updates in an isolated browser replay, including closing the table and reopening it with Enter. Frontend lint, TypeScript, and production build passed.
