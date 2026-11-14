# Speech Analysis Module (NASA Space Apps: Astronaut Health Self-Monitoring)

## Step 0 API Verification, Findings & Licenses

Before writing code, each speech library API was directly inspected and benchmarked:

### 1. openSMILE (eGeMAPSv02 Functionals)
- **API Call:**
  ```python
  smile = opensmile.Smile(
      feature_set=opensmile.FeatureSet.eGeMAPSv02,
      feature_level=opensmile.FeatureLevel.Functionals,
  )
  df = smile.process_signal(signal_1d_float32, 16000)
  ```
- **Output:** Exactly **88 audio functionals**.
- **Headline Mapping:**
  - `f0_mean`: `F0semitoneFrom27.5Hz_sma3nz_amean`
  - `f0_std`: `F0semitoneFrom27.5Hz_sma3nz_stddevNorm`
  - `jitter`: `jitterLocal_sma3nz_amean`
  - `shimmer`: `shimmerLocaldB_sma3nz_amean`
  - `hnr`: `HNRdBACF_sma3nz_amean`
  - `loudness_mean`: `loudness_sma3_amean`
  - `loudness_std`: `loudness_sma3_stddevNorm`
  - The remaining 88 features are emitted under the `egemaps_` prefix (e.g. `egemaps_HammarbergIndex_sma3_amean`).

### 2. Facebook Wav2Vec2 XLS-R 300M (`facebook/wav2vec2-xls-r-300m`)
- **API & Hidden States:**
  - Model instantiated via `Wav2Vec2Model.from_pretrained('facebook/wav2vec2-xls-r-300m')`.
  - Architecture: 24 Transformer encoder layers, hidden dimension $D = 1024$.
  - Passing `output_hidden_states=True` yields 25 hidden states: index 0 is CNN feature projection, indices 1 to 24 correspond to encoder layers 1 to 24.
  - Per-window processing: mean-pooled across time frames for selected layers (default `[6, 9, 12, 15, 18, 24]`).
  - Pooling choice: We mean-pool across all window frames using `torch.inference_mode()` with 30-second chunking. This avoids temporal frame misalignment with VAD while remaining bounded in memory and fast on CPU.

### 3. Silero VAD
- **API:**
  - Loaded via `torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True)`.
  - `get_speech_timestamps(wav_tensor, model, sampling_rate=16000, threshold=0.5, min_speech_duration_ms=250, min_silence_duration_ms=150)`.
  - Returns `[{'start': int, 'end': int}]` sample index intervals.

### 4. Parselmouth (Praat) Syllable Nuclei
- Acoustic syllable nuclei detection following de Jong & Wempe:
  - Praat intensity contour (`snd.to_intensity(minimum_pitch=50)`) + Praat pitch tracking (`snd.to_pitch(pitch_floor=75, pitch_ceiling=600)`).
  - Vowel peaks identified where intensity exceeds relative silence threshold (`-25 dB`) with prominence $\ge 4.0\text{ dB}$, minimum peak separation $\ge 180\text{ ms}$, and active voicing (`pitch > 0`).

### 5. Dependency Licenses
- **`opensmile` (audresample, audinterface):** Non-commercial / academic license for the underlying openSMILE binary; research/evaluation permitted. Commercial deployment requires audEERING commercial licensing.
- **`transformers` (Hugging Face) & PyTorch:** Apache 2.0 / BSD 3-Clause (Permissive commercial use).
- **`facebook/wav2vec2-xls-r-300m`:** Apache 2.0 (Permissive commercial use).
- **`silero-vad`:** MIT License (Permissive commercial use).
- **`praat-parselmouth`:** GNU GPL v3 (Praat wrapper).
- **`sounddevice` / `soundfile`:** MIT / BSD 3-Clause.

---

## Architecture & Code Structure

```text
speech/
  ├── __init__.py      # stream_windows generator and process_window pipeline
  ├── audio.py         # load_audio, resampling, microphone capture (sounddevice), window slicing
  ├── features.py      # openSMILE eGeMAPSv02 functionals + Silero VAD & Parselmouth timing features
  ├── embedding.py     # Wav2Vec2 XLS-R loader and per-layer mean pooling
  ├── quality.py       # SNR estimation, clipping fraction, quality score & validity check
  ├── run.py           # CLI with checkin/continuous modes and NPZ embedding export
  └── README.md        # Documentation, benchmarks, licenses, and honest limitations
tests/
  ├── test_quality.py  # Unit tests for SNR, clipping, speech duration, and quality formula
  └── test_timing.py   # Unit tests for syllable nuclei, speech/pause ratios, and articulation rates
```

---

## Output Contract

Each window yields one JSON-serializable dictionary adhering strictly to the contract:

```json
{
  "modality": "speech",
  "t": "2026-11-14T15:06:12.282998+00:00",
  "mode": "checkin",
  "features": {
    "f0_mean": 29.423,
    "f0_std": 0.041,
    "jitter": 0.0068,
    "shimmer": 1.730,
    "hnr": 9.384,
    "loudness_mean": 0.639,
    "loudness_std": 0.511,
    "speech_ratio": 0.7109,
    "pause_ratio": 0.2891,
    "mean_pause_s": 1.7344,
    "pause_count_per_min": 10.0,
    "speech_rate_syll_per_s": 2.9333,
    "articulation_rate_syll_per_s": 4.1260,
    "egemaps_F0semitoneFrom27.5Hz_sma3nz_amean": 29.423,
    "...": "all 88 eGeMAPSv02 features..."
  },
  "embedding": {
    "layers": [6, 9, 12, 15, 18, 24],
    "vectors": {
      "6": [0.0123, -0.0456, "... 1024 floats ..."],
      "9": ["..."],
      "12": ["..."],
      "15": ["..."],
      "18": ["..."],
      "24": ["..."]
    }
  },
  "quality": 1.0,
  "valid": true
}
```

### Quality & Validity Metric
$$\text{quality} = q_{\text{speech}} \times q_{\text{SNR}} \times q_{\text{clipping}}$$
- **$q_{\text{speech}}$:** $\min(1.0, \frac{\text{speech\_ratio}}{0.25})$.
- **$q_{\text{SNR}}$:** $\text{clamp}(\frac{\text{SNR}_{\text{dB}}}{20.0}, 0.0, 1.0)$.
- **$q_{\text{clipping}}$:** $\max(0.0, 1.0 - 20 \times \text{clipping\_fraction})$.
- **Validity:** A window is marked `valid: true` if and only if:
  $$\text{quality} \ge 0.5 \quad \text{AND} \quad \text{speech\_duration} \ge 5.0\text{ s}$$

---

## Measured Performance & CPU Benchmark

- **Hardware:** Apple Silicon (macOS arm64, CPU build)
- **30-second window processing time:**
  - VAD + Timing + Syllables: ~0.18 s
  - openSMILE 88 functionals: ~0.08 s
  - XLS-R 300M (6 layers, mean-pooled): ~1.80 s
  - **Total 30s window processing time: ~2.1 s** (target: well under 30 s; running $\approx 14\times$ faster than real-time on CPU).
- Continuous mode on 3-minute audio (`sample_3min.wav`): produced 6 windows in **14.7 seconds total**.

---

## Usage

### 1. Check-in Mode (Pre-recorded file)
```bash
python -m speech.run --source sample.wav --mode checkin --out checkin.jsonl
```

### 2. Standardized Check-in Recording from Microphone
Prompts astronaut with standard reading passage (*"When the sunlight strikes raindrops..."*), records 30 seconds from mic, saves WAV, and processes the record:
```bash
python -m speech.run --record --source checkin.wav --window 30 --out checkin.jsonl
```

### 3. Continuous Mode (Microphone or Long File)
```bash
# Long file
python -m speech.run --source sample_3min.wav --mode continuous --window 30 --out continuous.jsonl --embeddings-npz embeddings.npz

# Live microphone stream
python -m speech.run --source mic --mode continuous --window 30 --out live_mic.jsonl
```

### 4. Run Unit Tests
```bash
pytest tests/test_quality.py tests/test_timing.py -v
```

---

## Limitations & Honest Notes

1. **Acoustic Syllable Nuclei Approximation:**
   - The de Jong & Wempe heuristic relies on relative intensity peaks and pitch voicing without phonetic alignment. Highly whispered speech, creaky voice, or harsh background vibration can lead to over/under-counting syllables.
2. **Microphone Sensitivity, Distance & Spacecraft Noise:**
   - Acoustic parameters (loudness, jitter, shimmer, HNR) shift significantly with microphone model, mouth distance, and environmental fan/equipment hum. Astronaut monitoring relies on *longitudinal change against personal baseline*, requiring consistent microphone placement.
3. **XLS-R Embedding Confounders:**
   - XLS-R embeddings capture phonetic content, speaker identity, and acoustic channel characteristics in addition to cognitive/fatigue state. When used as a drift detector, comparing check-ins with identical reading passages is recommended to isolate voice state from linguistic variation.
4. **No Clinical Diagnosis:**
   - This module extracts objective physical and acoustic indicators; it does not classify emotion labels or diagnose psychiatric conditions.
