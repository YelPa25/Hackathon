# ASTRA 2.0 Stage 01 verification

The console remains a four-screen application with a sidebar and live status bar. The design audit below uses the 12 findings from the accepted Stage 01 report. Classifications are **Layout**, **Landing page** or **Empty state**.

| # | Original finding | Classification | Resolution or justification |
| --- | --- | --- | --- |
| 1 | `cta` on the screen | Empty state | Stage 01 offers navigation and status. The screen has no dataset or replay action to trigger. The four real destinations remain available. |
| 2 | `off-grid` on the ASTRA 2.0 wordmark | Layout | The brand and navigation links share the same icon column, label gap and inset. Measured wordmark and navigation label left edges match. |
| 3 | `moment-none` | Landing page | A separate showcase section would add no monitoring information or action. The console uses a short route entrance that respects reduced motion. |
| 4 | `hero-screen` | Landing page | The title and useful cards fit together within the first viewport. Screen height follows the content. |
| 5 | `section-height` | Landing page | Workspace content follows the status bar with ordinary page padding. It can grow as the screen gains monitoring data. |
| 6 | `one-heading` on the empty-state heading | Empty state | The page title is the only H1. The empty state and readiness panel have named H2 headings that explain their contents and support heading navigation. |
| 7 | `container-edges` on the status bar | Layout | The status row and main content now use the same fluid width, gutters and maximum width inside the workspace. Their edges match on a wide desktop. |
| 8 | `container-edges` on the screen content | Layout | Every screen uses the shared workspace width. The card grid starts on the title edge and stacks on narrower screens. All four pages fit at 320 CSS pixels. |
| 9 | `container-edges` on the React root | Landing page | The React mount contains the skip link, sidebar, status bar and main landmark. The checker expects the top-level structure of a marketing page. |
| 10 | `container-edges` on the readiness card heading | Layout | The readiness and empty-state cards now share their header height, padding and icon treatment. Heading top and card bottom alignment were measured in the browser. The readiness heading belongs to its own column. |
| 11 | `container-edges` on the empty-state card heading | Layout | The empty-state heading follows the same card header grid. Each heading is inset from its card edge for readability. |
| 12 | `container` reporting no `.wrap` | Landing page | The shared workspace width controls the status row and screen content within the sidebar layout. Browser checks measured matching edges and verified responsive widths. |

The mobile menu returns focus to its button on Escape and transfers focus to the main landmark when a destination is chosen, including the currently active one. The skip link also focuses main. The menu button has a 44 px minimum target width. System fonts are declared directly and load locally.

## SQLite and stage scope

The [roadmap](ROADMAP.md) specifies local SQLite readiness in Stage 01 and assigns the first application schema to Stage 02 historical ingest. The [architecture](ARCHITECTURE.md) describes the intended SQLite data model. Stage 01 initializes the file and probes SQLite with `PRAGMA schema_version` and `SELECT 1`. A read-only inspection of `backend/var/astra.sqlite3` returned `(1,)` for the probe and zero tables. Live health returned `database_ready: true` and `dataset_ready: false`. The correction pass preserved all 17 source file hashes.

## Verification

| Check | Result |
| --- | --- |
| Dependency lock | PASS. Ran `npm.cmd ci --include=dev --no-audit --no-fund` after stopping Vite. An earlier attempt hit a Windows file lock on a native CSS dependency held by Vite. |
| Frontend lint | PASS. Ran `npm.cmd run lint` with ESLint, TypeScript, and React Hooks rules. |
| TypeScript | PASS. Ran `npm.cmd run typecheck`. It also passed within the final production build. |
| Production build | PASS. Ran `npm.cmd run build`. |
| Backend tests | PASS. Six passed via `uv run --locked --offline --python $astraPython --no-managed-python pytest -q` in `backend`, using installed Windows Python 3.12. |
| Routes, layout and accessibility | PASS. Verified all four screens and empty states, active navigation, keyboard focus and no horizontal overflow at 1600, 1366, 768, 390 and 320 CSS pixels. At 1800 pixels the wordmark, shared workspace edges and card header and bottom alignment checked within 1 pixel. |
| Connectivity | PASS. Stopped FastAPI and observed Backend unavailable and SQLite status unknown. Restarted FastAPI and observed Backend connected and SQLite ready without a reload. |
| Browser log | PASS. The browser log inspection returned no warnings or errors. The backend outage was deliberate. |
| Design gate | OPEN. Final output was `GATE: OPEN 11 (rounds used up)`. The wordmark flag dropped from FAIL to WARN. The remaining FAILs are rows 1 and 3–12 above. There were no waivers. Warnings concern social sharing metadata for the local console and the centered brand icon inside its icon column. |
| Full network disconnection | NOT RUN. The outage test stopped FastAPI. The Windows network connection was not disabled. |

The console uses [Vite on 5180](http://127.0.0.1:5180/) and [FastAPI on 8050](http://127.0.0.1:8050/api/health). See [Windows startup](../README.md).

The 11 open gate checks are dashboard exceptions verified by the layout and keyboard checks above. No functional blockers remain for Stage 01 review. Stage 02 is pending approval.

Changed files: `frontend/src/app/App.tsx`, `frontend/src/styles/global.css`, `frontend/eslint.config.js`, `frontend/package.json`, `frontend/package-lock.json`, `README.md`, `docs/STATUS.md` and this report.
