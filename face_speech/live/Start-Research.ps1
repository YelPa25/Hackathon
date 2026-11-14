param([switch]$PrepareOnly)

$ErrorActionPreference = 'Stop'
$researchRoot = Join-Path $env:LOCALAPPDATA 'ASTRAResearch'
$pythonRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311'
$python = Join-Path $pythonRoot 'python.exe'
$venvPython = Join-Path $researchRoot '.venv\Scripts\python.exe'
$launcher = Join-Path $researchRoot 'isolate.py'
$modelWorker = Join-Path $researchRoot 'worker.py'
$pipeline = Join-Path $researchRoot 'pipeline'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path

if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $venvPython)) {
    throw 'Install the separate Python and research environment using the project guide.'
}

# Only reviewed application files enter the readable worker snapshot.
foreach ($directory in 'facial','speech','alerting') {
    $source = Join-Path $PSScriptRoot "..\$directory"
    $destination = Join-Path $pipeline $directory
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    Get-ChildItem -LiteralPath $source -Recurse -File -Filter '*.py' | Where-Object {
        $_.FullName -notmatch '[\\/]__pycache__[\\/]'
    } | ForEach-Object {
        $relative = $_.FullName.Substring((Resolve-Path -LiteralPath $source).Path.Length + 1)
        $target = Join-Path $destination $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'isolate.py'),(Join-Path $PSScriptRoot 'worker.py'),(Join-Path $PSScriptRoot 'calibration.py'),(Join-Path $PSScriptRoot 'runtime-smoke.py') -Destination $researchRoot -Force
$sid = & $python -I -B $launcher --sid
if ($LASTEXITCODE -ne 0 -or $sid -notmatch '^S-1-15-2-') { throw 'Could not prepare the Windows AppContainer.' }
$grant = "*${sid}:(OI)(CI)(RX)"
foreach ($directory in $researchRoot,$pythonRoot) {
    icacls.exe $directory /grant $grant
    if ($LASTEXITCODE -ne 0) { throw 'Could not grant the worker read-only access to its runtime.' }
}
$dataDir = Join-Path $repo 'ASTRA_90day_dataset_v1'
if (!(Test-Path -LiteralPath $dataDir)) { $dataDir = Join-Path $repo 'data-source\ASTRA_90day_dataset_v1' }
$target = Join-Path $dataDir 'replay_future_HIDDEN_DAY46_to_DAY90.csv'
if (!(Test-Path -LiteralPath $target)) { $target = Join-Path $repo 'AGENTS.md' }
$probe = Join-Path $researchRoot 'runtime-smoke.py'
$database = Join-Path $repo 'backend\var\astra.sqlite3'
if (!(Test-Path -LiteralPath $database)) { $database = $target }
node -e 'const p = require("node:child_process").spawnSync(process.argv[1], process.argv.slice(2), { input: "", encoding: "utf8" }); if (p.stdout) process.stdout.write(p.stdout); if (p.stderr) process.stderr.write(p.stderr); process.exitCode = p.status ?? 1' $python '-I' '-B' $launcher $probe $target $database
if ($LASTEXITCODE -ne 0) { throw 'The Windows access probe failed. Capture remains unavailable.' }
if (!$PrepareOnly) {
    node (Join-Path $PSScriptRoot 'broker.mjs')
    exit $LASTEXITCODE
}
