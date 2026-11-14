# NASA Space Apps: Astronaut Health Self-Monitoring Pipeline
## Engineering Summary & Integration Guide for Teammates

This document outlines the architecture, input/output data contracts, statistical anomaly detection methodology, and integration points for the **Per-Modality Health Monitoring & Alerting Layer**.

---

## 1. System Architecture & Where This Module Sits

```
┌─────────────────────────────────┐
│       EXTRACTOR LAYER           │
│  - facial/  (LibreFace AUs)     │
│  - speech/  (eGeMAPS + XLS-R)   │
│  - [future: physical sensors]   │
└────────────────┬────────────────┘
                 │ Extractor JSONL
                 ▼
┌─────────────────────────────────┐
│     ALERTING LAYER (THIS WORK)  │
│  - Robust Individual Baseline   │
│  - Two-Sided CUSUM              │
│  - Mahalanobis Embedding Drift  │
│  - Hysteresis State Machine     │
└────────────────┬────────────────┘
                 │ Contract Alerts JSONL
                 ▼
┌─────────────────────────────────┐
│        FUSION / DASHBOARD       │
│  - Cross-modality fusion        │
│  - Mission Control UI           │
└─────────────────────────────────┘
```

The pipeline operates in an asynchronous, decoupled manner. Modules communicate via standard JSONL (JSON Lines) files over filesystem tails (`--follow`), meaning:
- **No message broker (Redis/Kafka) required**.
- Extractors append records to an input file; the alert node consumes each record and emits a standardized alert record.
- Any crash or restart cleanly resumes without recalibration via state persistence.

---

## 2. Ingest Data Contracts (What Alerting Expects from Extractors)

Every extractor must emit a single JSON object per line with the following standard schema:

### Facial Extractor Output Contract (`features.jsonl`)
```json
{
  "modality": "facial",
  "t": "2026-11-14T16:56:36.554408+00:00",
  "quality": 0.85,
  "valid": true,
  "features": {
    "expressiveness": 0.2289,
    "au_activation_rate": 0.68,
    "head_pose_std": 0.6546,
    "au1_mean": 0.0703,
    "au1_std": 0.0154,
    "au2_mean": 0.0628,
    "au2_std": 0.017,
    "au4_mean": 1.3641,
    "au4_std": 0.3007,
    "au5_mean": 0.0672,
    "au6_mean": 0.0438,
    "au9_mean": 0.0882,
    "au12_mean": 0.108,
    "au15_mean": 0.1628,
    "au17_mean": 0.1063,
    "au20_mean": 0.0918,
    "au25_mean": 0.419,
    "au26_mean": 0.1629
  }
}
```

### Speech Extractor Output Contract (`speech.jsonl`)
```json
{
  "modality": "speech",
  "t": "2026-11-14T15:06:12.282998+00:00",
  "mode": "continuous",
  "quality": 0.95,
  "valid": true,
  "features": {
    "f0_mean": 29.5,
    "f0_std": 0.045,
    "jitter": 0.007,
    "shimmer": 1.70,
    "hnr": 9.5,
    "loudness_mean": 0.65,
    "loudness_std": 0.50,
    "speech_rate_syll_per_s": 3.0,
    "articulation_rate_syll_per_s": 4.1,
    "pause_ratio": 0.28,
    "mean_pause_s": 1.70
  },
  "embedding": {
    "layers": [6],
    "vectors": {
      "6": [0.012, -0.045, "... 1024 floats ..."]
    }
  }
}
```

---

## 3. Emitted Output Contract (What Fusion / UI Receives)

The alerting node outputs a unified, schema-validated record for each processed window:

```json
{
  "modality": "facial",
  "t": "2026-11-14T16:58:14.777133+00:00",
  "subject_id": "Astronaut_1",
  "state": "normal",
  "score": 0.52,
  "quality": 0.85,
  "drift": {
    "percentile": 25.0,
    "enabled": true
  },
  "contributors": [
    {
      "feature": "au_activation_rate",
      "z": -2.34,
      "direction": "down",
      "cusum": 1.84,
      "windows_flagged": 2
    },
    {
      "feature": "au4_mean",
      "z": 1.25,
      "direction": "up",
      "cusum": 0.92,
      "windows_flagged": 0
    }
  ],
  "reason": "All physiological and behavioral indicators are consistent with baseline.",
  "baseline": {
    "n": 40,
    "ready": true
  }
}
```

### Key Fields for Fusion:
- **`state`**: `"calibrating"` | `"normal"` | `"watch"` | `"alert"` | `"invalid"`
  - `"invalid"`: quality dropped below threshold (bad lighting, noise, dropout). The node preserves prior state without false alarms.
  - `"calibrating"`: gathering baseline samples.
  - `"normal"`: indicators within healthy individual range.
  - `"watch"`: single-indicator or early persistent deviation (sub-threshold).
  - `"alert"`: multi-group or embedding drift agreement confirming significant shift.
- **`score`**: Monotonic float in $[0.0, 1.0]$.
  - $\sim 0.0$: at baseline
  - $\sim 0.5$: crossing the watch threshold
  - $1.0$: critical alert threshold
- **`drift.percentile`**: $[0, 100]$ Mahalanobis embedding distance percentile relative to the astronaut's own baseline manifold.
- **`contributors`**: Top 5 ranked contributing features with direction (`"up"` or `"down"`), robust $z$-score, and cumulative deviation (CUSUM).
- **`reason`**: Neutral, clinically safe plain-language sentence (reports $\%$ deviation versus individual baseline; avoids diagnostic terms).

---

## 4. Anomaly Detection Mechanics (No Black-Box Models)

In space health monitoring, training supervised anomaly models or One-Class SVMs/Autoencoders fails due to the lack of labeled unhealthy data and high inter-individual variability. Our core design uses **robust non-parametric statistics against the astronaut's personal baseline**:

1. **Quality Gating**:
   If `valid == False` (e.g. face lost or microphone clipped), no statistics or CUSUM counters update.
2. **Robust Baseline ($z$-score)**:
   $$z = \frac{x - \text{median}}{1.4826 \times \text{effective\_MAD}}$$
   $$\text{effective\_MAD} = \max(\text{MAD},\, 10^{-4},\, 0.05 \times |\text{median}|)$$
   The relative floor ($5\%$ of median) prevents false alarm blow-up on small sample sizes.
3. **Two-Sided CUSUM**:
   Accumulates persistent subtle drift over time ($k = 0.5, h = 7.0$). Resets automatically when the astronaut returns to normal.
4. **Manifold Embedding Drift**:
   Reduces high-dimensional embeddings (AU vectors or XLS-R layer 6) via PCA ($\le 8$ components) and Ledoit-Wolf shrinkage covariance. Computes Mahalanobis distance percentile against baseline Leave-One-Out distances.
5. **Anti-Flapping & Hysteresis**:
   - Requires persistent deviation in $\ge 4$ of the last 5 valid windows to trigger.
   - Stepping down requires **5 consecutive clean windows**.
   - Direct jumps from `alert` $\to$ `normal` are strictly prohibited (must step down through `watch`).
   - Cooldown logic prevents immediate re-alerting after an episode unless severity exceeds the previous peak.

---

## 5. Adding New Modalities (e.g. Physical / Wearable Sensors)

The alerting engine is **modality-agnostic**. To plug in a new modality (e.g. `heart_rate`, `spo2`, `galvanic_skin_response`):

1. Create a configuration adapter in `alerting/adapters/<new_modality>.py`:
   ```python
   from alerting.core.config import AlertConfig

   def get_physical_config() -> AlertConfig:
       return AlertConfig(
           modality="physical",
           calibration_n=30,
           features=["hr_mean", "hrv_rmssd", "spo2_mean", "skin_temp"],
           feature_groups={
               "cardiac": ["hr_mean", "hrv_rmssd"],
               "respiratory": ["spo2_mean"],
               "autonomic": ["skin_temp"]
           },
           embedding_source="au_means",  # or custom vector source
           z_flag_threshold=3.0,
           cusum_h=7.0
       )
   ```
2. Feed your extractor records into `AlertNode(get_physical_config())`.
3. Done. The baseline, CUSUM, state machine, and explainability will automatically adapt.

---

## 6. How to Run & Test

### Command Line Alert Node (Tailing or File processing)
```bash
# Process live or recorded JSONL stream
PYTHONPATH=. .venv/bin/python -m alerting.run \
  --modality facial \
  --in live_facial.jsonl \
  --out alerts.jsonl \
  --follow
```

### Full Interactive Dashboard with Embedded Live Video
```bash
# Launch all-in-one monitor on webcam or video file
PYTHONPATH=. .venv/bin/python -m alerting.ui \
  --source 0 \
  --fps 15.0 \
  --window 5.0 \
  --port 8080
```
Open **`http://localhost:8080`** to inspect the live camera stream and telemetry.

### Running Test Suites & Scenario Evaluator
```bash
# Run unit tests (49 tests covering quality, baseline, CUSUM, hysteresis, etc.)
PYTHONPATH=. .venv/bin/pytest tests/ -q

# Run synthetic scenario benchmark (fatigue ramp, stress spike, noise, dropout, null)
PYTHONPATH=. .venv/bin/python alerting/sim/evaluate.py
```
