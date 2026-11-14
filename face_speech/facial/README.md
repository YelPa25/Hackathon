# Facial Analysis Module (NASA Space Apps: Astronaut Health Self-Monitoring)

## Step 0 API Verification & Findings

Before implementation, the `libreface` package (version 0.2.0) was inspected and benchmarked directly in Python:
- **Environment & Dependency Compatibility:** `libreface` pins `mediapipe==0.10.5` which is compatible with Python 3.10 and 3.11 (Python 3.12+ dropped binary wheels for `mediapipe 0.10.5`). Furthermore, `libreface`'s dependency `timm==1.0.9` requires `huggingface-hub<1.0` (installed `0.36.2`) to download model weights. Building `dlib` requires `cmake`.
- **API Signatures & Return Structure:**
  - High-level function: `libreface.get_facial_attributes_image(image_path, model_choice='joint_au_detection_intensity_estimator', device='cpu', weights_download_dir='./weights_libreface')`.
  - Returned keys:
    - `detected_aus`: dict mapping AU names (`au_1`, `au_2`, `au_4`, `au_6`, `au_7`, `au_10`, `au_12`, `au_14`, `au_15`, `au_17`, `au_23`, `au_24`) to binary flags `0` or `1`.
    - `au_intensities`: dict mapping AU intensity keys (`au_1_intensity`, `au_2_intensity`, `au_4_intensity`, `au_5_intensity`, `au_6_intensity`, `au_9_intensity`, `au_12_intensity`, `au_15_intensity`, `au_17_intensity`, `au_20_intensity`, `au_25_intensity`, `au_26_intensity`) to continuous floats in $[0, 5]$.
    - `pitch`, `yaw`, `roll`: head pose angles in degrees computed via solvePnP on 3D face mesh coordinates.
    - `gaze_yaw`, `gaze_pitch`: eye gaze direction angles.
    - `facial_expression`: discrete categorical label (`Neutral`, `Happiness`, `Sadness`, `Surprise`, `Fear`, `Disgust`, `Anger`, `Contempt`).
- **Disk I/O & Memory Optimization:**
  - Default `get_facial_attributes_image` takes a file path string and writes intermediate cropped files (`_aligned.png`, `_landmark.npy`) to `./tmp`.
  - To achieve high real-time throughput from camera streams without disk bottlenecks, `facial/extractor.py` wraps the internal alignment routine (`image_align`) and PyTorch solvers (`solver_inference_image_task_combine`) directly with in-memory PIL/NumPy buffers.
- **Model Loading Lifecycle:**
  - Standard `libreface` convenience functions instantiate PyTorch models on every single call. `facial/extractor.py` loads the ResNet AU models and MediaPipe Face Mesh once at initialization and reuses them across all incoming frames.

---

## Architecture & Code Structure

```text
facial/
  ├── __init__.py      # Package exports (LibreFaceExtractor, WindowAggregator, stream_windows)
  ├── extractor.py     # LibreFace & MediaPipe wrapper: frame BGR -> per-frame feature dict
  ├── windows.py       # Aggregation & quality logic (pure functions, contract formatting, generator)
  ├── run.py           # CLI & OpenCV capture loop with real-time throttling and FPS logging
  └── README.md        # Findings, usage, limitations, and future roadmap
tests/
  └── test_windows.py  # Unit tests for aggregation and quality scoring using synthetic frames
requirements.txt       # Pinned dependencies
```

---

## Output Contract

Each window yields one JSON-serializable dictionary adhering to the fixed contract:

```json
{
  "modality": "facial",
  "t": "2026-11-14T13:13:40.306461+00:00",
  "features": {
    "au1_mean": 0.0467,
    "au1_std": 0.0012,
    "au2_mean": 0.0258,
    "au2_std": 0.0007,
    "au4_mean": 0.2490,
    "au4_std": 0.0089,
    "au5_mean": 0.0241,
    "au5_std": 0.0003,
    "au6_mean": 0.0190,
    "au6_std": 0.0003,
    "au9_mean": 0.0508,
    "au9_std": 0.0007,
    "au12_mean": 0.0265,
    "au12_std": 0.0008,
    "au15_mean": 0.0544,
    "au15_std": 0.0011,
    "au17_mean": 0.0946,
    "au17_std": 0.0016,
    "au20_mean": 0.1122,
    "au20_std": 0.0034,
    "au25_mean": 0.0136,
    "au25_std": 0.0003,
    "au26_mean": 0.0305,
    "au26_std": 0.0002,
    "expressiveness": 0.0623,
    "head_pose_std": 0.1594,
    "au_activation_rate": 1.0
  },
  "quality": 1.0,
  "valid": true
}
```

### Quality & Validity Metric
$$\text{quality} = \left(\frac{N_{\text{detected}}}{N_{\text{total}}}\right) \times \text{penalty}_{\text{brightness}}$$
- **Brightness Penalty Heuristic:**
  - Mean grayscale brightness is evaluated per frame in $[0, 255]$.
  - Optimal lighting: $[40, 215] \implies 1.0$.
  - Underexposed (dark): $[0, 40) \implies \frac{\text{brightness}}{40.0}$.
  - Overexposed (bright): $(215, 255] \implies \frac{255.0 - \text{brightness}}{40.0}$.
- **Window Validity:** A window is marked `valid: true` if and only if $\text{quality} \ge 0.5$.

---

## Measured Performance & Benchmarks

- **Hardware:** Apple Silicon (macOS aarch64, CPU inference)
- **Average extraction latency:** **~24.90 ms** per frame
- **Maximum CPU throughput:** **~40.15 fps** (substantially exceeding real-time requirements at the default 5 fps sampling rate)
- **Webcam Real-Time Mode:** With target rate `--fps 5`, frame capture sleeps dynamically to maintain exact real-time pacing without CPU pegging.

---

## Usage

### 1. Installation
Ensure Python 3.10 is installed:
```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run CLI on Video File
```bash
python -m facial.run --source sample.mp4 --window 10 --fps 5 --out features.jsonl
```

### 3. Run CLI on Webcam
```bash
python -m facial.run --source 0 --window 30 --fps 5 --out features.jsonl
```

### 4. Run Unit Tests
```bash
pytest tests/test_windows.py -v
```

### 5. Python API Generator
```python
from facial.windows import stream_windows

for record in stream_windows(source=0, window_sec=30.0, fps=5.0):
    print(record["t"], record["quality"], record["valid"])
```

### Exit Handling (Ctrl+C & Video End)
- By default, partial windows at stream termination (Ctrl+C or end of video) are **discarded** to prevent incomplete statistical windows.
- To flush and emit partial windows on termination, pass `--flush-on-exit`.

---

## Known Limitations & Proposed Additions

1. **No Eye Closure / Blink Rate / PERCLOS in LibreFace:**
   - LibreFace detects upper/lower facial action units (e.g. AU4 brow lowerer, AU6 cheek raiser, AU12 lip corner puller) and gaze angles, but does **not** compute eye blink rate, eye aspect ratio (EAR), or percentage of eyelid closure over the pupil (PERCLOS).
   - In astronaut health monitoring, blink rate and PERCLOS are vital fatigue and drowsiness indicators.
   - **Proposed Future Extension:** Integrate Google MediaPipe Face Landmarker mesh coordinates directly (landmarks 33, 160, 158, 133, 153, 144 for right eye and 362, 385, 387, 263, 373, 380 for left eye) to compute the Eye Aspect Ratio:
     $$\text{EAR} = \frac{\|p_2 - p_6\| + \|p_3 - p_5\|}{2 \|p_1 - p_4\|}$$
     Tracking dips below threshold $\approx 0.2$ over time yields instantaneous blink frequency and PERCLOS.
2. **Subject Motion Blur & Extreme Head Pose:**
   - LibreFace's ResNet AU models depend on a frontal aligned crop. Head yaw or pitch beyond $\pm 45^\circ$ causes MediaPipe landmark jitter or loss of face detection, reducing the window `quality` metric below 0.5.
3. **Lighting Extremes:**
   - Very dark spacecraft environments or harsh direct sunlight degrade AU detection; the brightness penalty automatically accounts for this by downgrading window quality.
