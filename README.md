# ASTRA 2.0

ASTRA is a local, non-clinical astronaut health and mission replay prototype. A fresh mission opens at the end of Day 45 with four synthetic crew profiles. Stage 03 reveals recorded observations through Day 90 as mission time advances!

## Start on Windows

Use installed Windows Python 3.12, uv and Node.js 22.13+ (Node 22 LTS) or Node 24 or newer with npm. If Python 3.12 is installed elsewhere, set `$astraPython` to its full executable path. Initial dependency installation needs package registry access. Subsequent starts use installed dependencies and loopback.

### Backend terminal

```powershell
Set-Location './backend'
$astraPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
uv sync --locked --python $astraPython --no-managed-python
uv run --locked --offline --python $astraPython --no-managed-python uvicorn --factory astra.main:create_app --app-dir src --host 127.0.0.1 --port 8050
```

FastAPI creates or upgrades `backend/var/astra.sqlite3` and verifies and imports history automatically before accepting requests. First import logs "Historical mission dataset: imported". Restarting with the same inputs logs "already present" and reuses the import. Open [backend health](http://127.0.0.1:8050/api/health) to confirm `{"status":"ok","database_ready":true,"dataset_ready":true}`. If history is unavailable, check the startup log. If a source check fails after a successful import, the prior verified import stays available and Data & Science displays the issue.

### Frontend terminal

```powershell
Set-Location './frontend'
npm.cmd ci
npm.cmd run dev
```

Open the [ASTRA console](http://127.0.0.1:5180/). Mission Overview shows four crew members and cabin readings. Crew Health shows crew profiles, latest readings and historical samples. Mission Replay opens at the saved position. A fresh database starts at Day 45, and a backend restart pauses active playback. Data & Science shows synthetic provenance, coverage and references.

Press Ctrl+C in each terminal to stop its process. If verifying recovery, restart FastAPI and select **Retry** on any view that failed while it was down. This checkout uses ports 8050 and 5180.

## Verify replay

1. Open [ASTRA](http://127.0.0.1:5180/) and select **Mission Replay**. A fresh database opens on Day 45.
2. Open **Crew Health** and note the latest date on a chart. Return to Mission Replay and select **Next Day**. Day 46 publishes 141 records. Return to Crew Health and look for a new sample, for example Hana Tanaka's sleep duration on 15 February.
3. Step through several days, choose a speed, then use **Resume**, **Pause**, and **Resume** again. **Next Event** while paused publishes one complete timestamp group.
4. Restart the backend with the same database path and verify the saved position. Select **Reset Replay** and confirm. Check that Mission Overview and Crew Health return to the Day 45 view.
5. To rehearse in isolation, set `ASTRA_DB_PATH` to a new temporary SQLite path before starting the backend. Restore the previous environment setting when finished.

Playback runs on the backend even when you leave the replay page. Use one backend process per database. Reset preserves installed history, source files, unrelated database records, and playback speed.

## Configuration

The root `.env.example` lists settings. Set backend variables with `$env:NAME = 'value'` before starting FastAPI. Vite settings can be set in the frontend terminal or in a root `.env.local`.

- `ASTRA_ENV` is `development` or `test`. Only development enables CORS.
- `ASTRA_DB_PATH` is a SQLite file path. Relative paths resolve from `backend`. Keep it outside the source directory.
- `ASTRA_CORS_ORIGINS` is a comma-separated list of loopback frontend origins with explicit ports.
- `ASTRA_DEV_API_TARGET` is Vite's backend proxy target. `ASTRA_DEV_FRONTEND_PORT` changes Vite's port.
- `ASTRA_DATASET_DIR` points to the extracted read-only bundle. The backend prefers `data-source/ASTRA_90day_dataset_v1` when present and otherwise uses `ASTRA_90day_dataset_v1` at the project root. The latter is the current layout. Override it with `$env:ASTRA_DATASET_DIR = 'C:\path\to\ASTRA_90day_dataset_v1'`. Use the original inputs and `SHA256SUMS.txt`.

This repository includes the six runtime dataset inputs and their original SHA256SUMS.txt. The checksum list also covers files from the full source bundle. The historical importer and replay engine verify the entries for the inputs they read.

## Checks

From `backend`, run `uv run --locked --offline --python $astraPython --no-managed-python pytest -q` with the original bundle in one of the default locations. From `frontend`, run `npm.cmd run lint`, `npm.cmd run typecheck` and `npm.cmd run build`. Stop Vite before reinstalling dependencies on Windows so it releases native package files.

### Optional ASTRA Companion

Open [ASTRA Companion](http://127.0.0.1:5180/companion) for conversation, stories, quizzes and text games. It uses the existing Ollama runtime on `http://127.0.0.1:11434` with the exact model `qwen3:4b-instruct-2507-q4_K_M`. Neither the mission console nor its health features needs Ollama.

In PowerShell, run `ollama list` and check for that exact tag. If Ollama is already running, the Companion screen can verify it. For a manual local-only Ollama session, quit Ollama from the Windows taskbar first if its tray app already owns the port, then run:

```powershell
$env:OLLAMA_NO_CLOUD = '1'
ollama serve
```

Open Companion and wait for **Qwen3 · Running locally**. Pick a starter or type a message, then press Enter. Shift+Enter adds a line. The first reply may take a few seconds while Ollama loads the model. If the service becomes unavailable, keep the tab open, restart Ollama and use **Check again** and **Retry**. For an existing ASTRA backend started without reload, restart FastAPI from this checkout once to load the Companion routes.

The chat transcript stays in browser memory as you navigate within ASTRA. **New Conversation** clears it. Reloading the app or closing the tab ends the session. Ollama receives only the recreational prompt and a bounded set of chat messages over loopback. The chat is for recreation. Use ASTRA's dedicated screens for health and mission information. [Ollama local-only setup](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)

### Optional live research capture

Open [Research Prototypes](http://127.0.0.1:5180/research-prototypes) to try the synthetic samples. For local webcam and microphone inference, follow [Windows research setup and startup](docs/LIVE_RESEARCH_CAPTURE.md).
