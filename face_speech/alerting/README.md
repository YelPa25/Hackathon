# Alerting Module — Per-Modality Health Alert Layer

> **NASA Space Apps: Astronaut Health Self-Monitoring**
> Build stage: `alerting/` — sits between extractors and fusion dashboard.

---

## Architecture

```
facial/extractor → features.jsonl ─┐
                                   ├─ alerting/run.py ─► alerts.jsonl ─► [fusion]
speech/features  → features.jsonl ─┘
```

Each modality runs as a **separate process**, communicating via JSONL files. No message broker needed.

---

## Step 0 — Real Feature Names (confirmed from extractor JSONL)

### Facial (`features.jsonl`)
```json
{
  "modality": "facial", "t": "<ISO-8601>", "valid": true, "quality": 1.0,
  "features": {
    "expressiveness": 0.08, "au_activation_rate": 0.95, "head_pose_std": 0.25,
    "au1_mean": 0.05, "au2_mean": 0.03, "au4_mean": 0.20,
    "au5_mean": 0.03, "au6_mean": 0.02, "au9_mean": 0.05,
    "au12_mean": 0.03, "au15_mean": 0.06, "au17_mean": 0.10,
    "au20_mean": 0.12, "au25_mean": 0.02, "au26_mean": 0.04
  }
}
```

### Speech (`checkin_result.jsonl`, `continuous_3min.jsonl`)
```json
{
  "modality": "speech", "t": "<ISO-8601>", "mode": "checkin|continuous",
  "valid": true, "quality": 1.0,
  "features": {
    "f0_mean": 29.5, "f0_std": 0.045, "jitter": 0.007, "shimmer": 1.70,
    "hnr": 9.5, "loudness_mean": 0.65, "loudness_std": 0.50,
    "speech_rate_syll_per_s": 3.0, "articulation_rate_syll_per_s": 4.1,
    "pause_ratio": 0.28, "mean_pause_s": 1.70
  },
  "embedding": { "layers": [6, 9, 12, 15, 18, 24], "vectors": { "6": [1024 floats], ... } }
}
```

---

## Output Contract

One JSON record per input record (JSONL, one object per line):

```json
{
  "modality": "facial|speech",
  "t": "<copied from input>",
  "subject_id": "astronaut_1",
  "state": "calibrating|normal|watch|alert|invalid",
  "score": 0.0,
  "quality": 1.0,
  "drift": { "percentile": 72.5, "enabled": true },
  "contributors": [
    { "feature": "speech_rate_syll_per_s", "z": -3.8, "direction": "down",
      "cusum": 4.2, "windows_flagged": 6 }
  ],
  "reason": "Speech rate 18% below baseline for 6 consecutive windows; voice pattern shifted from baseline.",
  "baseline": { "n": 20, "ready": true }
}
```

---

## CLI

```bash
# Basic run
python -m alerting.run --modality facial --in features.jsonl --out alerts.jsonl

# Tail live extractor output
python -m alerting.run --modality speech --in features.jsonl --out alerts.jsonl --follow

# Named subject, custom config
python -m alerting.run --modality facial --in features.jsonl --out alerts.jsonl \
  --subject astronaut_1 --config cfg.yaml

# Enable slow EWMA baseline adaptation (off by default — see risk below)
python -m alerting.run --modality speech --in features.jsonl --out alerts.jsonl --adapt

# Clear persisted state and recalibrate from scratch
python -m alerting.run --modality facial --in features.jsonl --out alerts.jsonl --reset

# Replay recorded file at 10× speed (demo)
python -m alerting.run --modality facial --in features.jsonl --out alerts.jsonl --speedup 10
```

---

## Alert Logic Summary

### 1. Quality Gate
If `valid=false`, emit `state=invalid`, hold previous state, increment gap counter.
Baseline, CUSUM, and hysteresis counters are **not** updated.

### 2. Calibration
First **N** valid records build the frozen baseline (default: facial=40, speech continuous=20, checkin=7).
State is `calibrating` until ready. After that the baseline is **frozen** by default.

### 3. Robust z-score
```
z = (x − median) / (1.4826 × effective_MAD)
effective_MAD = max(sample_MAD, mad_floor, mad_relative_floor × |median|)
```
The relative floor (5% of median) is critical for small calibration sets where sample MAD underestimates the true noise scale.

### 4. Two-sided CUSUM
Tracks slow directional drift with slack `k=0.5`, threshold `h=7.0`.
Resets when state returns to `normal`.

### 5. Embedding Drift
PCA (up to 8 components) + Ledoit-Wolf covariance → Mahalanobis distance → empirical percentile against the baseline's own distances. Disabled when baseline < 8 samples.

### 6. Feature Flagging
A feature flags when `|z| ≥ 3.0` **or** its CUSUM ≥ h=7.0.
Drift flags when its percentile ≥ 98.0.

### 7. State Machine (hysteresis)

| Transition | Condition |
|---|---|
| normal → watch | ≥1 feature or drift flags, in **4 of last 5** valid windows |
| watch → alert (facial) | (drift AND ≥1 feature) OR (≥2 feature groups flag), in 4/5 windows |
| watch → alert (speech) | drift AND ≥1 feature flag, in 4/5 windows |
| alert/watch → normal | 5 consecutive clean windows (all `\|z\|` < 1.5, drift < 80th percentile); **step-down only** (alert→watch→normal) |
| Cooldown | After dropping from alert, re-alert blocked for 5 windows unless new severity exceeds the previous peak |

### 8. Severity Score

| Score | Meaning |
|---|---|
| 0.0 | At baseline |
| ~0.5 | At watch threshold (`\|z\|≈3.0` or drift≈98th percentile) |
| 1.0 | At or beyond alert threshold (`\|z\|≥4.5` or CUSUM≥2h) |

---

## Scenario Evaluation Results

```
Modality  | Scenario        | Watch Delay | Alert Delay | Alert Count | False Alerts/100 | Flapping
-------------------------------------------------------------------------------------
speech    | fatigue_ramp    | +10 w       | +25 w       | 35          | 58.3             | 1
speech    | stress_spike    | None        | +13 w       | 47          | 78.3             | 1
speech    | noise_only      | None        | None        | 0           | 0.0              | 0   ✓
speech    | sensor_dropout  | None        | None        | 0           | 0.0              | 0   ✓
speech    | null            | +25 w       | None        | 0           | 0.0              | 0   ✓
facial    | fatigue_ramp    | +13 w       | +14 w       | 46          | 76.7             | 1
facial    | stress_spike    | None        | +13 w       | 47          | 78.3             | 1
facial    | noise_only      | None        | None        | 0           | 0.0              | 0   ✓
facial    | sensor_dropout  | None        | None        | 0           | 0.0              | 0   ✓
facial    | null            | None        | None        | 0           | 0.0              | 0   ✓
```

All 5 acceptance scenarios **pass** for both modalities.

---

## Threshold Rationale

| Parameter | Value | Default | Reason for change |
|---|---|---|---|
| `z_flag_threshold` | 3.0 | 2.5 | At N=20 calibration, sample MAD underestimates true scale; threshold 2.5 produced ~31% false flags on null stream |
| `cusum_h` | 7.0 | 5.0 | With h=5.0, 69% of null trials hit the threshold within 60 windows; h=7.0 reduces this to ~8% |
| `drift_percentile_flag` | 98.0 | 95.0 | With N=20 baseline, percentile resolution is 5%; roughly 5% of normal windows naturally land at exactly 95th percentile |
| `persist_required_flags` | 4 | 3 | Requiring 4-of-5 windows (vs 3-of-5) substantially reduces watch/alert rate on null streams |
| `mad_relative_floor` | 0.05 | *(new)* | 5% of \|median\| as minimum effective MAD — prevents z-score blow-up when sample MAD is severely underestimated with small N; primary fix for false alarm problem |

---

## Honest Limitations

> [!IMPORTANT]
> This system has **not been clinically validated**. All thresholds were tuned on
> simulated data with synthetic noise models. Do not use for medical decisions.

1. **No clinical validation**: Thresholds were empirically tuned on synthetic scenarios. Real physiological baselines may require re-tuning per individual.

2. **Thresholds tuned on simulated data**: The generator uses simple Gaussian noise with 5% coefficient of variation per feature. Real signals may have heavier tails, autocorrelation, or non-Gaussian distributions.

3. **Baseline freeze vs. adaptation tradeoff**:
   - **Frozen baseline** (default): resistant to slow gradual decline being absorbed — abnormal slowly becomes the new "normal". But the baseline becomes stale over long missions.
   - **EWMA adaptation** (`--adapt`): allows baseline to drift with the person over time. Risk: a genuine slow health decline gets absorbed into the baseline, suppressing alerts. Use with extreme caution on missions >days.

4. **Small baseline gives weaker drift estimates**: Speech checkin mode uses N=7 for calibration. Drift detection requires ≥8 samples for PCA; below this, `EmbeddingDrift` is automatically disabled and a warning is logged. Even with N=8–15, PCA explains less variance and Mahalanobis estimates are noisy.

5. **Watch state on null stream**: The null scenario shows `watch_delay=+25 w` for speech. Per spec, only *alerts* are failures; watch states on a null stream are acceptable as early-warning sensitivity.

6. **Sensor dropout leaves watch state**: After returning from invalid windows, the system resumes from the state it was in before dropout. If state was `watch` before dropout, it remains `watch` after. This is by design to avoid false "all-clear" signals after a gap.

---

## Module Structure

```
alerting/
  core/
    baseline.py   # RobustBaseline: median/MAD with two-level floor
    cusum.py      # TwoSidedCUSUM: two-sided with configurable k, h, reset
    drift.py      # EmbeddingDrift: PCA + Ledoit-Wolf + Mahalanobis percentile
    state.py      # AlertStateMachine: hysteresis, step-down, cooldown
    explain.py    # build_contributors, build_reason_string
    config.py     # AlertConfig dataclass, YAML/JSON loadable
    node.py       # AlertNode: orchestration + persistence
  adapters/
    facial.py     # Feature groups and tuned config for facial stream
    speech.py     # Feature groups and tuned config for speech stream
  sim/
    generate.py   # Synthetic record generators (real contract format)
    evaluate.py   # Scenario evaluation runner
  run.py          # CLI entry point
tests/
  test_alert_core.py   # 33 unit tests
```

---

## Running Tests

```bash
# All 49 tests (16 existing + 33 alerting)
PYTHONPATH=. .venv/bin/pytest tests/ -v

# Scenario evaluation
PYTHONPATH=. .venv/bin/python alerting/sim/evaluate.py
```
