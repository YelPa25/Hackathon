"""Audio quality assessment: speech ratio, estimated SNR, clipping fraction."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np


def compute_clipping_fraction(
    audio: np.ndarray,
    threshold: float = 0.99,
) -> float:
    """Calculate the fraction of audio samples at or near full scale [-1.0, 1.0]."""
    if len(audio) == 0:
        return 0.0
    clipped = np.abs(audio) >= threshold
    return float(np.mean(clipped))


def estimate_snr_db(
    audio: np.ndarray,
    speech_segments: List[Dict[str, int]],
) -> float:
    """Estimate Signal-to-Noise Ratio (SNR) in dB from speech vs non-speech frame energy.

    Args:
        audio: 1D audio samples.
        speech_segments: List of dicts with 'start' and 'end' sample indices.

    Returns:
        SNR in decibels (clamped to [-10.0, 50.0]).
    """
    total_samples = len(audio)
    if total_samples == 0:
        return 0.0

    speech_mask = np.zeros(total_samples, dtype=bool)
    for seg in speech_segments:
        s = max(0, seg["start"])
        e = min(total_samples, seg["end"])
        if e > s:
            speech_mask[s:e] = True

    speech_audio = audio[speech_mask]
    noise_audio = audio[~speech_mask]

    # Calculate RMS power
    speech_energy = np.mean(speech_audio**2) if len(speech_audio) > 0 else 1e-9
    noise_energy = np.mean(noise_audio**2) if len(noise_audio) > 0 else 1e-9

    speech_energy = max(float(speech_energy), 1e-9)
    noise_energy = max(float(noise_energy), 1e-9)

    snr = 10.0 * math.log10(speech_energy / noise_energy)
    return float(np.clip(snr, -10.0, 50.0))


def compute_audio_quality(
    audio: np.ndarray,
    sr: int = 16000,
    speech_segments: Optional[List[Dict[str, int]]] = None,
    speech_ratio: Optional[float] = None,
) -> Tuple[float, bool, Dict[str, float]]:
    """Compute overall audio quality in [0.0, 1.0] and validity flag.

    Formula:
      quality = q_speech * q_snr * q_clip
      where:
        - q_speech: sigmoid-like curve on speech_ratio, optimal >= 0.2
        - q_snr: linear scale from 0 dB (quality=0) to >= 20 dB (quality=1)
        - q_clip: 1.0 - 10 * clipping_fraction (punishes clipping > 1%)

    Validity requirement:
      valid = (quality >= 0.5) and (speech_duration_s >= 5.0)

    Returns:
        Tuple of (quality_score, is_valid, quality_metrics_dict).
    """
    if speech_segments is None:
        from speech.features import get_speech_segments
        speech_segments = get_speech_segments(audio, sr=sr)

    total_samples = len(audio)
    total_duration_s = float(total_samples) / float(sr) if sr > 0 else 0.0

    speech_samples = sum(s["end"] - s["start"] for s in speech_segments)
    speech_duration_s = float(speech_samples) / float(sr) if sr > 0 else 0.0

    if speech_ratio is None:
        speech_ratio = (
            (speech_duration_s / total_duration_s) if total_duration_s > 0 else 0.0
        )

    # 1. Speech ratio score: full score (1.0) if speech_ratio >= 0.25; linear drop below
    q_speech = float(np.clip(speech_ratio / 0.25, 0.0, 1.0))

    # 2. SNR score: 0 dB -> 0.0, 20 dB -> 1.0
    snr_db = estimate_snr_db(audio, speech_segments)
    q_snr = float(np.clip(snr_db / 20.0, 0.0, 1.0))

    # 3. Clipping score: penalize if clipping exceeds 0.5%
    clipping_frac = compute_clipping_fraction(audio, threshold=0.99)
    q_clip = float(np.clip(1.0 - (clipping_frac * 20.0), 0.0, 1.0))

    quality = round(float(q_speech * q_snr * q_clip), 4)

    # Valid if quality >= 0.5 and at least 5s of speech
    is_valid = bool(quality >= 0.5 and speech_duration_s >= 5.0)

    metrics = {
        "snr_db": round(snr_db, 2),
        "clipping_fraction": round(clipping_frac, 5),
        "speech_duration_s": round(speech_duration_s, 2),
    }

    return quality, is_valid, metrics
