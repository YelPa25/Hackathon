"""Facial adapter configuration."""

from __future__ import annotations

from alerting.core.config import AlertConfig


def get_facial_config() -> AlertConfig:
    """Create alert configuration for facial AU monitoring stream."""
    features = [
        "expressiveness",
        "au_activation_rate",
        "head_pose_std",
        "au1_mean",
        "au2_mean",
        "au4_mean",
        "au5_mean",
        "au6_mean",
        "au9_mean",
        "au12_mean",
        "au15_mean",
        "au17_mean",
        "au20_mean",
        "au25_mean",
        "au26_mean",
    ]

    feature_groups = {
        "global_activity": [
            "expressiveness",
            "au_activation_rate",
            "head_pose_std",
        ],
        "upper_face": [
            "au1_mean",
            "au2_mean",
            "au4_mean",
            "au5_mean",
        ],
        "mid_face": [
            "au6_mean",
            "au9_mean",
        ],
        "lower_face": [
            "au12_mean",
            "au15_mean",
            "au17_mean",
            "au20_mean",
            "au25_mean",
            "au26_mean",
        ],
    }

    return AlertConfig(
        modality="facial",
        calibration_n=40,  # 40 valid windows (default)
        features=features,
        feature_groups=feature_groups,
        embedding_source="au_means",
        drift_percentile_flag=98.0,   # raised from 95 – coarse percentile resolution at N=40
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
