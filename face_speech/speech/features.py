"""Voice feature extraction: openSMILE eGeMAPSv02 and timing features."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import opensmile
import parselmouth
from scipy.signal import find_peaks
import torch


# Global cache for openSMILE instance to avoid reloading definitions
_SMILE_INSTANCE: Optional[opensmile.Smile] = None

# Global cache for Silero VAD model
_SILERO_VAD_MODEL = None
_SILERO_UTILS = None


def get_smile() -> opensmile.Smile:
    """Get or initialize singleton openSMILE instance."""
    global _SMILE_INSTANCE
    if _SMILE_INSTANCE is None:
        _SMILE_INSTANCE = opensmile.Smile(
            feature_set=opensmile.FeatureSet.eGeMAPSv02,
            feature_level=opensmile.FeatureLevel.Functionals,
        )
    return _SMILE_INSTANCE


def get_silero_vad():
    """Get or load singleton Silero VAD model."""
    global _SILERO_VAD_MODEL, _SILERO_UTILS
    if _SILERO_VAD_MODEL is None:
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
            onnx=False,
        )
        model.eval()
        _SILERO_VAD_MODEL = model
        _SILERO_UTILS = utils
    return _SILERO_VAD_MODEL, _SILERO_UTILS


def extract_egemaps(
    audio: np.ndarray,
    sr: int = 16000,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Extract 88 eGeMAPSv02 functionals and headline subset.

    Returns:
        Tuple of (headline_dict, full_egemaps_prefixed_dict).
    """
    smile = get_smile()
    if len(audio) == 0:
        return {}, {}

    try:
        df = smile.process_signal(audio, sr)
        row = df.iloc[0].to_dict()
    except Exception:
        return {}, {}

    # Full set with egemaps_ prefix
    full_egemaps = {f"egemaps_{k}": float(v) for k, v in row.items()}

    # Headline features mapped from standard eGeMAPSv02 column names
    headline = {
        "f0_mean": float(row.get("F0semitoneFrom27.5Hz_sma3nz_amean", 0.0)),
        "f0_std": float(row.get("F0semitoneFrom27.5Hz_sma3nz_stddevNorm", 0.0)),
        "jitter": float(row.get("jitterLocal_sma3nz_amean", 0.0)),
        "shimmer": float(row.get("shimmerLocaldB_sma3nz_amean", 0.0)),
        "hnr": float(row.get("HNRdBACF_sma3nz_amean", 0.0)),
        "loudness_mean": float(row.get("loudness_sma3_amean", 0.0)),
        "loudness_std": float(row.get("loudness_sma3_stddevNorm", 0.0)),
    }

    return headline, full_egemaps


def get_speech_segments(
    audio: np.ndarray,
    sr: int = 16000,
    threshold: float = 0.5,
) -> List[Dict[str, int]]:
    """Get speech timestamps [{'start': sample_idx, 'end': sample_idx}] using Silero VAD."""
    model, utils = get_silero_vad()
    get_speech_timestamps = utils[0]

    wav_tensor = torch.from_numpy(audio).float()
    timestamps = get_speech_timestamps(
        wav_tensor,
        model,
        threshold=threshold,
        sampling_rate=sr,
        min_speech_duration_ms=250,
        min_silence_duration_ms=150,
    )
    return timestamps


def count_syllable_nuclei(
    audio: np.ndarray,
    sr: int = 16000,
    silence_threshold_db: float = -25.0,
    min_dip_db: float = 4.0,
    min_pause_between_syll_s: float = 0.18,
) -> int:
    """Acoustic syllable-nuclei detection (de Jong & Wempe style).

    Detects intensity peaks that have a minimum prominence dip (min_dip_db)
    and correspond to voiced regions (valid pitch).
    """
    if len(audio) < int(sr * 0.1):  # Less than 100ms
        return 0

    # Ensure sound has non-zero amplitude
    if np.max(np.abs(audio)) < 1e-5:
        return 0

    snd = parselmouth.Sound(audio, sampling_frequency=sr)
    intensity = snd.to_intensity(minimum_pitch=50)
    pitch = snd.to_pitch(pitch_floor=75, pitch_ceiling=600)

    times = intensity.xs()
    int_vals = intensity.values[0, :]
    if len(int_vals) == 0:
        return 0

    max_int = float(np.max(int_vals))
    peak_threshold = max_int + silence_threshold_db

    # In human speech, syllables cannot occur closer than ~180ms
    min_distance_samples = max(1, int(round(min_pause_between_syll_s / intensity.dt)))
    peaks, _ = find_peaks(
        int_vals,
        height=peak_threshold,
        prominence=min_dip_db,
        distance=min_distance_samples,
    )
    if len(peaks) == 0:
        return 0

    syllable_count = 0
    for p in peaks:
        t = times[p]
        p_val = pitch.get_value_at_time(t)
        if p_val is not None and not np.isnan(p_val) and p_val > 0:
            syllable_count += 1

    return syllable_count


def extract_timing_features(
    audio: np.ndarray,
    sr: int = 16000,
    speech_segments: Optional[List[Dict[str, int]]] = None,
) -> Dict[str, float]:
    """Calculate speech timing features from VAD and syllable nuclei detection.

    Features:
        speech_ratio: speech duration / total duration
        pause_ratio: pause duration / total duration
        mean_pause_s: average duration of pause intervals
        pause_count_per_min: pause frequency scaled to per-minute
        speech_rate_syll_per_s: syllables / total window duration
        articulation_rate_syll_per_s: syllables / speech-only duration
    """
    total_duration_s = float(len(audio)) / float(sr)
    if total_duration_s <= 0:
        return {
            "speech_ratio": 0.0,
            "pause_ratio": 1.0,
            "mean_pause_s": 0.0,
            "pause_count_per_min": 0.0,
            "speech_rate_syll_per_s": 0.0,
            "articulation_rate_syll_per_s": 0.0,
        }

    if speech_segments is None:
        speech_segments = get_speech_segments(audio, sr=sr)

    total_samples = len(audio)

    # Compute speech duration
    speech_samples = sum(s["end"] - s["start"] for s in speech_segments)
    speech_duration_s = float(speech_samples) / float(sr)
    speech_duration_s = min(speech_duration_s, total_duration_s)

    speech_ratio = speech_duration_s / total_duration_s
    pause_ratio = max(0.0, 1.0 - speech_ratio)

    # Calculate pauses between speech segments
    pauses_s: List[float] = []
    last_end = 0
    for seg in speech_segments:
        start = seg["start"]
        if start > last_end:
            pause_dur = (start - last_end) / float(sr)
            if pause_dur >= 0.15:  # pause minimum threshold (150ms)
                pauses_s.append(pause_dur)
        last_end = seg["end"]

    # Final pause after last speech segment if any
    if last_end < total_samples:
        final_pause = (total_samples - last_end) / float(sr)
        if final_pause >= 0.15:
            pauses_s.append(final_pause)

    pause_count = len(pauses_s)
    mean_pause_s = float(np.mean(pauses_s)) if pauses_s else 0.0
    pause_count_per_min = float(pause_count) * (60.0 / total_duration_s)

    # Syllable nuclei detection
    syllables = count_syllable_nuclei(audio, sr=sr)

    speech_rate = float(syllables) / total_duration_s
    articulation_rate = (
        (float(syllables) / speech_duration_s) if speech_duration_s > 0.1 else 0.0
    )

    return {
        "speech_ratio": round(speech_ratio, 4),
        "pause_ratio": round(pause_ratio, 4),
        "mean_pause_s": round(mean_pause_s, 4),
        "pause_count_per_min": round(pause_count_per_min, 4),
        "speech_rate_syll_per_s": round(speech_rate, 4),
        "articulation_rate_syll_per_s": round(articulation_rate, 4),
    }
