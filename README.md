# ASTRA 2.0

ASTRA is a local, non-clinical astronaut health and mission replay prototype. Stage 01 provides the four-screen shell and a live backend and SQLite status. The interface shows empty states until the later import stage.

## Start on Windows

Use installed Windows Python 3.12, uv and Node.js 22.13+ (Node 22 LTS) or Node 24 or newer with npm. The commands below use the Python.org per-user installation path. If Python 3.12 is installed elsewhere, set `$astraPython` to its full executable path. Initial dependency installation requires access to the package registries. Subsequent starts use installed dependencies and loopback.

### Backend terminal

```powershell
Set-Location './backend'
$astraPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
uv sync --locked --python $astraPython --no-managed-python
uv run --locked --offline --python $astraPython --no-managed-python uvicorn --factory astra.main:create_app --app-dir src --host 127.0.0.1 --port 8050
```

Open the [health endpoint](http://127.0.0.1:8050/api/health) to see `{"status":"ok","database_ready":true,"dataset_ready":false}`. SQLite is created at `backend/var/astra.sqlite3` by default.

### Frontend terminal

```powershell
Set-Location './frontend'
npm.cmd ci
npm.cmd run dev
```

Open the [ASTRA console](http://127.0.0.1:5180/). The navigation has Mission Overview, Crew Health, Mission Replay and Data & Science. The top bar checks FastAPI through the Vite proxy. Mission Overview also displays the SQLite result. To verify recovery, stop FastAPI with Ctrl+C, wait for **Backend unavailable**, then start FastAPI again.

Press Ctrl+C in each terminal to stop its process. This checkout uses ports 8050 and 5180 to avoid conflicts with services already on 8000 and 5173.

## Configuration

The root `.env.example` lists settings. Set backend variables with `$env:NAME = 'value'` in the backend terminal before starting it. The backend reads process environment variables. Frontend settings can be set in the frontend terminal or in a root `.env.local` file read by Vite.

- `ASTRA_ENV` is `development` or `test`. Only development enables CORS.
- `ASTRA_DB_PATH` is a SQLite file path. Relative paths resolve from `backend`. Keep the database outside the source dataset.
- `ASTRA_CORS_ORIGINS` is a comma-separated list of loopback frontend origins with explicit ports.
- `ASTRA_DEV_API_TARGET` is Vite's backend proxy target. Adjust it if the FastAPI port changes. `ASTRA_DEV_FRONTEND_PORT` changes Vite's port.
- `ASTRA_DATASET_DIR` is reserved for the later import stage. The current dataset is in `ASTRA_90day_dataset_v1` at the root. Use that relative path or the full path when configuring the future importer. The backend accepts the setting in Stage 01 and performs no import.

## Checks

Run `uv run --locked --offline --python $astraPython --no-managed-python pytest -q` from the backend terminal with the variable above set. Run `npm.cmd run lint` for ESLint and `npm.cmd run build` for TypeScript validation and the production build. Stop Vite before reinstalling dependencies on Windows so it releases native package files.
