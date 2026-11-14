"""Serialize fitted research statistics, without raw windows or detection history."""

from hashlib import sha256
import json
from math import isfinite

from alerting.core.baseline import RobustBaseline
from alerting.core.drift import EmbeddingDrift


def calibration_version(config, assets, timing):
    contract = {"format": 1, "config": config.to_dict(), "assets": assets, "timing": timing}
    return sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()


def export_calibration(detector, version):
    if not detector.baseline.is_ready:
        raise ValueError("Complete calibration before saving it.")
    return {
        "version": version,
        "medians": detector.baseline.medians,
        "mads": detector.baseline.mads,
        "drift": detector.drift.to_dict(),
    }


def vector(values, size):
    if (not isinstance(values, list) or len(values) != size or
            any(type(value) not in (int, float) or not isfinite(value) for value in values)):
        raise ValueError("Saved calibration contains invalid statistics.")
    return values


def restore_calibration(detector, profile, version, embedding_size):
    config = detector.config
    if not isinstance(profile, dict) or profile.get("version") != version:
        raise ValueError("Saved calibration uses different analysis settings. Recalibrate.")
    stats = {}
    for label in ("medians", "mads"):
        values = profile.get(label)
        if not isinstance(values, dict) or set(values) != set(config.features):
            raise ValueError("Saved calibration is missing feature statistics.")
        vector(list(values.values()), len(config.features))
        stats[label] = values
    if any(value < config.mad_floor for value in stats["mads"].values()):
        raise ValueError("Saved calibration contains invalid variation estimates.")

    saved = profile.get("drift")
    if not isinstance(saved, dict) or saved.get("is_ready") is not True or type(saved.get("enabled")) is not bool:
        raise ValueError("Saved calibration is missing the fitted pattern.")
    drift = detector.drift.to_dict()
    drift.update(is_ready=True, enabled=saved["enabled"])
    if drift["enabled"]:
        components = saved.get("pca_components")
        distances = saved.get("baseline_distances")
        if (not isinstance(components, list) or not 1 <= len(components) <= config.pca_max_components or
                not isinstance(distances, list) or
                not config.min_baseline_drift_samples <= len(distances) <= config.calibration_n):
            raise ValueError("Saved calibration contains an invalid pattern.")
        dimensions = len(components)
        covariance = saved.get("inv_cov")
        if not isinstance(covariance, list) or len(covariance) != dimensions:
            raise ValueError("Saved calibration contains an invalid pattern.")
        drift.update(
            baseline_distances=vector(distances, len(distances)),
            pca_components=[vector(row, embedding_size) for row in components],
            pca_mean=vector(saved.get("pca_mean"), embedding_size),
            inv_cov=[vector(row, dimensions) for row in covariance],
            mean_vec=vector(saved.get("mean_vec"), dimensions),
        )
        if distances != sorted(distances) or distances[0] < 0:
            raise ValueError("Saved calibration contains invalid distances.")

    baseline = detector.baseline.to_dict()
    detector.baseline = RobustBaseline.from_dict({
        **baseline, **stats, "is_ready": True, "n_samples": config.calibration_n,
    })
    detector.drift = EmbeddingDrift.from_dict(drift)
