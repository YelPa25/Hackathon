# Live research capture on Windows

## Start the existing installation

ASTRA uses the normal backend at port 8050 and Vite at port 5180. The optional research service listens at 127.0.0.1 port 8051. Keep the three terminals open.

In a PowerShell terminal at the ASTRA-Hackathon project root, run:

```powershell
.\face_speech\live\Start-Research.ps1
```

Wait for **ASTRA Research broker on 127.0.0.1:8051**. Open [Research Prototypes](http://127.0.0.1:5180/research-prototypes). Use the `127.0.0.1` URL because the broker checks the browser origin.

1. Select **Start camera** or **Start microphone** and allow access when the browser asks. Face the webcam in good light or speak at a comfortable pace in a quiet room. The camera preview and active microphone label indicate capture.
2. A first facial window takes about ten seconds. A speech window collects fifteen seconds before processing. A usable window advances calibration. Signal gaps do not count.
3. **Pause capture** or leaving Research Prototypes releases the device. The browser keeps the chart and the local worker retains calibration for up to 15 minutes. **Resume capture** turns the device back on with your permission and continues the session. The worker discards an incomplete window on resume. A reload ends the paused session. **New calibration** starts a fresh session.
4. After calibration, pause and select **Save my calibration** to keep the fitted statistics in this browser. After a reload, select **Use saved calibration** with the same participant and device. The worker checks the analysis version and scores the first usable window. A new capture starts fresh detection history. **Remove saved calibration** deletes that modality's saved profile. ASTRA stores fitted statistics, an opaque device hash and a save timestamp in the browser. Raw media and earlier scoring history stay out of the saved profile.
5. After the detector scores a usable window, pause and select **Show result on dashboards**. **View Research Prototypes** reopens the exact published result and feature chart. Synthetic playback retains its position. Live capture stays paused until you resume. Dashboard cards stay in browser memory until you remove them or reload.

A complete first calibration requires 40 valid facial windows of about ten seconds each or 20 valid fifteen-second voice windows. Budget about seven minutes for the camera and about five minutes plus processing of the last sample for voice when all samples pass the quality checks. The microphone collects the next full window during inference. The recording duration, quality checks, feature extraction and detector thresholds remain the same. Facial movement and voice changes are experimental observations of feature deviation.

If a device prompt was denied, enable it in browser site settings and check Windows camera or microphone privacy settings. The synthetic samples are available without the research service. Use Ctrl+C in the research terminal to stop it.

## Runtime and weights

This setup is optional and intended for local research use under the upstream terms. Read the [third-party notices](../THIRD_PARTY_NOTICES.md#optional-local-runtimes-and-models) before installing LibreFace or openSMILE. For the competition demonstration, the synthetic feature samples work with the normal Core setup and require no live capture packages or device access.

This installation uses system Python 3.11.9, a separate environment at `%LOCALAPPDATA%\ASTRAResearch\.venv`, and the Windows CPU builds of PyTorch 2.0.1, TorchVision 0.15.2 and TorchAudio 2.0.2. The original teammate manifest remains intact. `requirements-windows.txt` contains the compatible research dependencies, including PyArrow 17.0.0. Newer PyArrow was blocked by Windows application control. LibreFace uses the AU submodules directly, with the same AU checkpoint as the teammate branch. Gaze and expression classification are outside the live configuration.

On a fresh Windows machine, install the official Python 3.11 interpreter and create an optional environment:

```powershell
winget install --id Python.Python.3.11 --exact --source winget --scope user
$researchRoot = Join-Path $env:LOCALAPPDATA 'ASTRAResearch'
$researchBase = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
uv venv --no-managed-python --python $researchBase (Join-Path $researchRoot '.venv')
$researchPython = Join-Path $researchRoot '.venv\Scripts\python.exe'
uv pip install --python $researchPython --link-mode copy --only-binary ':all:' 'torch==2.0.1+cpu' 'torchvision==0.15.2+cpu' 'torchaudio==2.0.2+cpu' --index 'https://download.pytorch.org/whl/cpu' --default-index 'https://pypi.org/simple' --index-strategy unsafe-best-match
uv pip install --python $researchPython --link-mode copy --only-binary ':all:' -r .\face_speech\live\requirements-windows.txt
uv pip install --python $researchPython --link-mode copy --only-binary ':all:' --no-deps 'libreface==0.2.0'
```

Copy these pinned files under `%LOCALAPPDATA%\ASTRAResearch\models`. The worker checks their full SHA-256 hashes before loading.

| Relative model path | Source |
| --- | --- |
| `libreface/AU_Recognition/weights/combined_resnet.pt` | [LibreFace 0.2.0 upstream checkpoint](https://drive.google.com/file/d/1CbnBr8OBt8Wb73sL1ENcrtrWAFWSSRv0/view), as linked by the installed package. See [USC terms](https://github.com/ihp-lab/LibreFace/blob/main/LICENSE.rst). The worker accepts only SHA-256 `d7d11d9f029afef0d36306f91f5e67fd20531390864ab014e08683dbaca3954b`. The 45.3 MB upstream download matched the worker pin during the release rehearsal. |
| `torch/hub/checkpoints/resnet18-f37072fd.pth` | [Official TorchVision CPU checkpoint](https://download.pytorch.org/models/resnet18-f37072fd.pth). |
| `silero/silero_vad.jit`, `silero/utils_vad.py` | [Pinned Silero release source](https://github.com/snakers4/silero-vad/tree/6478567951ae5c9979ad7b234185b5515f4be7a1/src/silero_vad). The JIT file is in its `data` directory. |
| `xls-r/config.json`, `xls-r/pytorch_model.bin` | [Pinned Meta XLS-R weights](https://huggingface.co/facebook/wav2vec2-xls-r-300m/tree/1a640f32ac3e39899438a2931f9924c02f080a54), about 1.27 GB. |

## Isolation

The browser handles opt-in and device access. The Vite proxy forwards bounded samples to the separate loopback service. The broker relays one sample at a time over inherited pipes into a Windows AppContainer with zero capabilities. It grants the worker read and execute access to the separate runtime and interpreter directories and uses a one-process Windows Job to terminate the model worker when its launcher closes. Raw device buffers are transient. The research service exposes no file, dataset, replay or Core API access. The Core application has no dependency on this service.

Startup verifies the worker token and tries to access the private replay CSV and default SQLite database. It also probes the live Core socket and an external TCP address. The observed loopback probe timed out, and the external connection was denied. Smart App Control stayed enabled.

## Verification

- Original teammate suite, 49 passed with Windows CPU packages in the separate environment. ASTRA backend regression suite, 21 passed.
- Frontend ESLint, TypeScript and production build passed. All four Core routes and the health endpoint returned 200. The hidden CSV returned 404, and the research broker rejected foreign origins and requests missing its local capture header.
- A headless Chrome browser drove Start and Stop with an instrumented camera and microphone stream. The real CPU extractors processed a public-domain NASA photograph and generated speech, each reaching the first valid calibration window with 100% signal quality. A separate Chrome device test returned insufficient-signal states on its built-in test streams. The device tracks ended on Stop, and navigation ended the active camera track. Width checks passed at 1440, 768 and 390 CSS pixels. Generated input verifies transport and inference. Physical device output and full live calibration are pending a participant's test. [Camera fixture provenance](https://scikit-image.org/docs/0.25.x/api/skimage.data.html#skimage.data.astronaut).
- The voice model took about 6 seconds to load and 4 seconds to process a 15-second input in a direct loopback test. Timings depend on the machine.
- All 16 entries in the supplied source checksum list matched. The source directory contains those 16 files plus the checksum list.
- The frontend skill's first gate run returned `GATE: FAIL 14`, largely on landing-page geometry, a full-screen hero and illustration requirements. The product retains the existing console layout. Browser layout and capture checks were used for this feature.

## Capture reliability and chart spacing

- The capture browser retries brief transport failures. The broker accepts each numbered sample once and can return the same result if its response was lost. A persistent failure, a worker exit, or a disconnected device ends capture with the reason shown in the panel. Stop and route exit release the device.
- The feature selector and chart occupy separate rows, and chart content is clipped to its frame. Missing or invalid windows remain gaps. The voice readout distinguishes a completed baseline from a low-quality current sample. A low-quality sample has no deviation score.
- A Chrome regression with input fixtures verified that the camera stayed active and advanced through three valid windows across a dropped request and a lost response. The retry returned the same calibration window. Chart spacing was checked at 1413, 768, and 390 CSS pixels. A separate loopback test using the real facial worker passed a partial upload cancellation, duplicate concurrent submission, and explicit Stop.
- Frontend lint, TypeScript, production build, and all 21 Core tests passed. The design gate still reports the same 14 findings related to the existing console layout and landing-page requirements. The exact cause of the original webcam stop was not recorded, and this fix has been tested using synthetic device input.

## Session restore and calibration timing

- The real workers completed 40 facial and 20 speech windows with an accelerated fixture feed. A fresh worker for each modality loaded the fitted profile and scored its first usable window. Version mismatches and invalid statistics were rejected. Feed times are compute checks. They exclude real recording time.
- A timed Chrome capture produced consecutive voice results 15.02 seconds apart. Previously a 15-second sample was followed by about four seconds of processing before the next recording began. At the observed pace, pipelining saves roughly 75 seconds across 20 usable windows. Actual time also depends on signal quality.
- A trial with a 5-second camera window changed the measured head-motion variability in the motion fixture. A trial with 9-second voice windows accepted two of three generated samples, while all three 15-second samples passed. These small fixture comparisons did not establish equivalent detection reliability. The standard window lengths remain the defaults.
- The 21 Core regression tests, 49 teammate tests, frontend lint, TypeScript and production build passed.
- The full browser regression reopened the exact synthetic voice result from Crew Health and the exact live facial result from Mission Overview. It retained camera calibration across pause and navigation, kept the camera off on return, and exercised saved calibration load after reload, save and removal. Browser streams used local test fixtures. The frontend design gate remained open on the same 14 console layout findings.
