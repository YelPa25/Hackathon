"""Synthetic record generators in the real contract formats for evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

# Per-feature bounds: (min, max). None means unbounded.
_FACIAL_BOUNDS: Dict[str, Tuple[Optional[float], Optional[float]]] = {
    "expressiveness": (0.0, None),
    "au_activation_rate": (0.0, 1.0),  # fraction in [0, 1]
    "head_pose_std": (0.0, None),
    "au1_mean": (0.0, 5.0),
    "au2_mean": (0.0, 5.0),
    "au4_mean": (0.0, 5.0),
    "au5_mean": (0.0, 5.0),
    "au6_mean": (0.0, 5.0),
    "au9_mean": (0.0, 5.0),
    "au12_mean": (0.0, 5.0),
    "au15_mean": (0.0, 5.0),
    "au17_mean": (0.0, 5.0),
    "au20_mean": (0.0, 5.0),
    "au25_mean": (0.0, 5.0),
    "au26_mean": (0.0, 5.0),
}


def _clamp(val: float, lo: Optional[float], hi: Optional[float]) -> float:
    if lo is not None and val < lo:
        return lo
    if hi is not None and val > hi:
        return hi
    return val


def generate_facial_record(
    timestamp: datetime,
    baseline_means: Dict[str, float],
    deviations: Dict[str, float] = None,
    noise_scale: float = 0.05,
    quality: float = 1.0,
    is_valid: bool = True,
    rng: np.random.Generator = None,
) -> Dict[str, Any]:
    """Generate a synthetic facial extractor record."""
    if rng is None:
        rng = np.random.default_rng()
    if deviations is None:
        deviations = {}

    features = {}
    for k, base_val in baseline_means.items():
        dev = deviations.get(k, 0.0)
        noise = rng.normal(0.0, noise_scale * (base_val + 0.01))
        val = base_val + dev + noise
        lo, hi = _FACIAL_BOUNDS.get(k, (0.0, None))
        val = _clamp(val, lo, hi)
        features[k] = round(float(val), 4)

    return {
        "modality": "facial",
        "t": timestamp.isoformat(),
        "features": features,
        "quality": round(float(quality), 2),
        "valid": is_valid,
    }


# Shared latent projection matrix for realistic speech embeddings
_SPEECH_LATENT_U: np.ndarray = np.random.default_rng(1234).normal(0.0, 1.0, (1024, 6))


def generate_speech_record(
    timestamp: datetime,
    baseline_means: Dict[str, float],
    deviations: Dict[str, float] = None,
    noise_scale: float = 0.05,
    quality: float = 1.0,
    is_valid: bool = True,
    embedding_shift: float = 0.0,
    rng: np.random.Generator = None,
) -> Dict[str, Any]:
    """Generate a synthetic speech extractor record."""
    if rng is None:
        rng = np.random.default_rng()
    if deviations is None:
        deviations = {}

    features = {}
    for k, base_val in baseline_means.items():
        dev = deviations.get(k, 0.0)
        noise = rng.normal(0.0, noise_scale * (abs(base_val) + 0.01))
        val = base_val + dev + noise
        features[k] = round(float(val), 4)

    # 1024-dim embedding generated from a low-rank latent representation + noise
    z_latent = rng.normal(0.0, 1.0, 6)
    if embedding_shift != 0.0:
        z_latent += embedding_shift * 2.5

    emb_vec = (z_latent @ _SPEECH_LATENT_U.T) * 0.1 + rng.normal(0.0, 0.02, 1024)
    vectors = {"6": [round(float(x), 5) for x in emb_vec]}

    return {
        "modality": "speech",
        "t": timestamp.isoformat(),
        "mode": "continuous",
        "features": features,
        "embedding": {"layers": [6], "vectors": vectors},
        "quality": round(float(quality), 2),
        "valid": is_valid,
    }


def make_facial_baseline_defaults() -> Dict[str, float]:
    """Typical baseline means for facial AU features."""
    return {
        "expressiveness": 0.08,
        "au_activation_rate": 0.95,
        "head_pose_std": 0.25,
        "au1_mean": 0.05,
        "au2_mean": 0.03,
        "au4_mean": 0.20,
        "au5_mean": 0.03,
        "au6_mean": 0.02,
        "au9_mean": 0.05,
        "au12_mean": 0.03,
        "au15_mean": 0.06,
        "au17_mean": 0.10,
        "au20_mean": 0.12,
        "au25_mean": 0.02,
        "au26_mean": 0.04,
    }


def make_speech_baseline_defaults() -> Dict[str, float]:
    """Typical baseline means for speech features."""
    return {
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
        "mean_pause_s": 1.70,
    }


def generate_scenario_stream(
    modality: str,
    scenario: str,
    n_baseline: int = 40,
    n_test: int = 60,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Generate a complete evaluation stream with baseline + scenario anomaly."""
    rng = np.random.default_rng(seed)
    records = []
    base_time = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)

    is_speech = modality == "speech"
    base_means = make_speech_baseline_defaults() if is_speech else make_facial_baseline_defaults()

    # 1. Baseline calibration period (clean normal records)
    for i in range(n_baseline):
        t = base_time + timedelta(seconds=i * 30)
        if is_speech:
            rec = generate_speech_record(t, base_means, rng=rng)
        else:
            rec = generate_facial_record(t, base_means, rng=rng)
        records.append(rec)

    # 2. Test period depending on scenario
    for j in range(n_test):
        idx = n_baseline + j
        t = base_time + timedelta(seconds=idx * 30)
        devs: Dict[str, float] = {}
        emb_shift = 0.0
        qual = 1.0
        is_val = True

        if scenario == "null":
            # No change: clean normal
            pass

        elif scenario == "fatigue_ramp":
            # Gradual ramp over 60 windows
            progress = min(1.0, float(j) / 30.0)
            if is_speech:
                devs["speech_rate_syll_per_s"] = -1.2 * progress  # rate drops ~40%
                devs["articulation_rate_syll_per_s"] = -1.0 * progress
                devs["pause_ratio"] = +0.25 * progress
                devs["mean_pause_s"] = +1.5 * progress
                devs["f0_std"] = -0.025 * progress               # flat intonation
                emb_shift = 0.5 * progress
            else:
                devs["expressiveness"] = -0.05 * progress        # reduced mobility
                devs["au_activation_rate"] = -0.40 * progress
                devs["au12_mean"] = -0.02 * progress
                devs["au6_mean"] = -0.015 * progress

        elif scenario == "stress_spike":
            # Abrupt spike between windows 10 and 22, then complete recovery
            if 10 <= j < 22:
                if is_speech:
                    devs["f0_mean"] = +8.0                        # high pitch
                    devs["f0_std"] = +0.06                        # erratic pitch
                    devs["jitter"] = +0.025
                    devs["shimmer"] = +2.5
                    devs["speech_rate_syll_per_s"] = +1.5
                    emb_shift = 0.9
                else:
                    devs["au4_mean"] = +0.35                      # intense brow furrow
                    devs["au17_mean"] = +0.25                     # chin raise
                    devs["head_pose_std"] = +0.50                 # head tremor
            # After j >= 22, devs is empty (recovery)

        elif scenario == "noise_only":
            # Lower quality / SNR, shifted embeddings, but health features unchanged
            qual = 0.40  # Below 0.5 threshold or noisy
            is_val = False
            emb_shift = 0.8

        elif scenario == "sensor_dropout":
            # Sensor disconnects between windows 15 and 30
            if 15 <= j < 30:
                is_val = False
                qual = 0.0
            # Otherwise clean normal

        if is_speech:
            rec = generate_speech_record(
                t, base_means, deviations=devs, quality=qual, is_valid=is_val,
                embedding_shift=emb_shift, rng=rng
            )
        else:
            rec = generate_facial_record(
                t, base_means, deviations=devs, quality=qual, is_valid=is_val, rng=rng
            )
        records.append(rec)

    return records
