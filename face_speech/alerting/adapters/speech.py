"""Speech adapter configuration."""

from __future__ import annotations

from alerting.core.config import AlertConfig


def get_speech_config(mode: str = "continuous") -> AlertConfig:
    """Create alert configuration for speech monitoring stream.

    Args:
        mode: "checkin" (calibration N=7) or "continuous" (calibration N=20).
    """
    features = [
        "f0_mean",
        "f0_std",
        "jitter",
        "shimmer",
        "hnr",
        "loudness_mean",
        "loudness_std",
        "speech_rate_syll_per_s",
        "articulation_rate_syll_per_s",
        "pause_ratio",
        "mean_pause_s",
    ]

    feature_groups = {
        "prosody_pitch": [
            "f0_mean",
            "f0_std",
        ],
        "voice_quality": [
            "jitter",
            "shimmer",
            "hnr",
        ],
        "loudness": [
            "loudness_mean",
            "loudness_std",
        ],
        "timing_rhythm": [
            "speech_rate_syll_per_s",
            "articulation_rate_syll_per_s",
            "pause_ratio",
            "mean_pause_s",
        ],
    }

    cal_n = 7 if mode == "checkin" else 20

    return AlertConfig(
        modality="speech",
        calibration_n=cal_n,
        features=features,
        feature_groups=feature_groups,
        embedding_source="layer",
        embedding_layer="6",  # Layer 6 tested as optimal acoustic drift sensor
        drift_percentile_flag=98.0,   # raised from 95 – coarse percentile resolution at N=20
        drift_percentile_recovery=80.0,
        min_baseline_drift_samples=8,
        pca_max_components=8,
        mad_floor=1e-4,
        mad_relative_floor=0.05,      # 5 % of |median| as effective MAD floor
        z_flag_threshold=3.0,         # raised from 2.5 to reduce false flags on small calibration sets
        z_recovery_threshold=1.5,
        cusum_k=0.5,
        cusum_h=7.0,                  # raised from 5.0 – extra resistance to random CUSUM drift
        window_history_len=5,
        persist_required_flags=4,     # raised from 3 – require 4 of 5 windows to flag
        exit_consecutive_clean=5,
        cooldown_windows=5,
    )
