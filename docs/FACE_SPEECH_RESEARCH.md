# Facial and speech research integration

For the subsequent opt-in Windows capture implementation, see [Live research capture](LIVE_RESEARCH_CAPTURE.md). The results below document the initial fixture phase.

Local branch: `codex/face-speech-research`, based on `main` at `03d3be4`. Upstream: [face and speech handoff at dc30f16](https://github.com/YelPa25/Hackathon/tree/dc30f16775cefe34777dcbf85d949d545ea1bf62/face_speech).

## Scope and startup

Start the existing ASTRA backend and frontend using [the Windows startup commands](../README.md#start-on-windows). An already running Vite server can pick up the integration. Open [Research Prototypes](http://127.0.0.1:5180/research-prototypes) or select it from the sidebar. No model environment is needed to play the included examples.

- In **Facial Feature Monitoring** or **Voice Feature Monitoring**, choose **Gradual feature shift** or **Signal dropout**, then select **Play sample**. **Stop** freezes the display at the current feature window. Calibration, signal quality, relative deviation, feature trends, and contributor directions come from the supplied detector's output.
- Stop at a valid, calibrated result or wait for the sample to finish, then select **Show result on dashboards**. Mission Overview and Crew Health use a separate **Experimental demonstration** card with the fixture source, demo session, and sample time. Select **Remove dashboard result** to clear it. The card uses browser memory, so refreshing clears it.
- The samples are generated feature windows for fictional demo sessions with an independent clock. The page sends no Core write requests, starts no worker, accesses no device and stores no media. The physiological prototype and Qwen are outside this integration.

## Imported source and fixture

36 upstream files were verified byte-for-byte against their Git blob IDs. These are the Python, README and integration files under `face_speech/alerting/`, `face_speech/facial/`, `face_speech/speech/`, `face_speech/tests/`, and `face_speech/requirements.txt`. This includes the standalone upstream dashboard for source review. ASTRA uses its own playback surface. Recorded media, precomputed feature streams, embeddings, persisted detector state, IDE files and weights stayed outside the import. Original detector, feature extractors, dependencies and tests were preserved.

The local Python 3.12 detector environment used `requirements-detector.txt` (NumPy 1.26.4, SciPy 1.15.3, scikit-learn 1.3.2, PyYAML 6.0.2 and pytest 9.2.0). Those packages have Windows wheels. No ASTRA dependency file was changed. The reviewed Python fixture entry point runs in a disposable directory and uses a Python audit hook to restrict file opens, network operations, and child processes. This scoped fixture harness provides no OS sandbox guarantee for native or live inference. The app never invokes it.

To reproduce the fixture verification from the project root in PowerShell:

```powershell
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('astra-face-fixture-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
Copy-Item -LiteralPath 'face_speech/alerting','face_speech/tests' -Destination $fixtureRoot -Recurse
Copy-Item -LiteralPath 'face_speech/verify_fixture.py','face_speech/requirements-detector.txt' -Destination $fixtureRoot
$researchPython = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python312/python.exe'
uv venv --no-managed-python --python $researchPython (Join-Path $fixtureRoot 'test-env')
$runner = Join-Path $fixtureRoot 'test-env/Scripts/python.exe'
uv pip install --python $runner --only-binary ':all:' -r (Join-Path $fixtureRoot 'requirements-detector.txt')
Push-Location -LiteralPath $fixtureRoot
try {
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    $env:OMP_NUM_THREADS = '1'
    $env:OPENBLAS_NUM_THREADS = '1'
    & $runner -I -B ./verify_fixture.py tests tests/test_alert_core.py
    & $runner -I -B ./verify_fixture.py fixture
} finally { Pop-Location }
```

The generated `demo.json` matches the browser fixture. JSONL detector outputs are written into the disposable directory. For a guard-controlled full-suite attempt, copy `face_speech/facial` and `face_speech/speech` there too, then use `verify_fixture.py tests --continue-on-collection-errors tests`. The three extractor files need the capture dependencies below.

## Verification and limits

| Check | Result |
| --- | --- |
| Original detector tests | 33 passed. Includes robust calibration, CUSUM, embedding drift, hysteresis, and state persistence. |
| Original extractor suite | Three files could not collect in the detector-only environment. Speech quality and timing require the package's audio imports, starting with `sounddevice`. Facial windows require OpenCV and extractor imports. |
| Original scenario evaluator | Ran 10 synthetic modality/scenario combinations. Both modalities produced deviations in the shift scenarios and zero alert windows in noise, dropout and null. Speech reported 35 watch windows in the null scenario, which limits interpretation even on fixtures. These counts are about the generated inputs. |
| Browser | Both panels loaded. Verified sample Start and Stop, calibration, signal dropout, unsafe-to-publish invalid result blocking, facial deviation and contributors, optional dashboard cards and removal, all four Core routes, and Crew Health charts. |
| Core | 21 backend tests passed. An isolated API check advanced Day 45 → 46 → 45 and verified that future rows were hidden after reset. The isolated Core served with no research endpoint or worker. Frontend lint, TypeScript and production build passed. All 17 original dataset hashes matched. |
| Live hardware and extraction | Pending. Camera preview, microphone capture, LibreFace action-unit inference, eGeMAPS and XLS-R inference, CPU extraction, GPU extraction, and hardware Stop behavior were outside fixture verification. |

For live extraction, review and approve a separate Windows runtime first. The upstream face README documents Python 3.10/3.11 for LibreFace 0.2.0 and MediaPipe 0.10.5. The requirements pin Torch/TorchVision/TorchAudio 2.0.1/0.15.1/2.0.1. The speech stack also needs OpenSMILE, audio I/O, Parselmouth, Transformers, Silero VAD and `facebook/wav2vec2-xls-r-300m`. Review capture permissions, speaker/media rights, weight licenses and hashes, runtime compatibility, and an OS boundary protecting Core data before enabling devices. Pin and load vetted local assets before enabling offline inference. The installed RTX 5090 Laptop driver was detected. CPU is the first extraction target and GPU support remains a separate check.

Before a hardware demo, approve the separate interpreter and capture packages, local weights, and permitted recording workflow. Then verify the extractor suite, local-only asset loading, capture opt-in and visible status, stop and cleanup, and operation with the network unavailable. The fixture demo is available for the current competition rehearsal.
