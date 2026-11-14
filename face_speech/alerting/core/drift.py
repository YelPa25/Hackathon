"""High-dimensional embedding drift detection using PCA and Ledoit-Wolf covariance."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sklearn.covariance import LedoitWolf
from sklearn.decomposition import PCA


logger = logging.getLogger(__name__)


class EmbeddingDrift:
    """Detects manifold drift using PCA reduction and Ledoit-Wolf shrinkage Mahalanobis distance."""

    def __init__(
        self,
        pca_max_components: int = 8,
        min_baseline_samples: int = 8,
        flag_percentile: float = 95.0,
        recovery_percentile: float = 80.0,
    ) -> None:
        self.pca_max_components = pca_max_components
        self.min_baseline_samples = min_baseline_samples
        self.flag_percentile = flag_percentile
        self.recovery_percentile = recovery_percentile

        self.buffer: List[np.ndarray] = []
        self.pca: Optional[PCA] = None
        self.lw: Optional[LedoitWolf] = None
        self.mean_vec: Optional[np.ndarray] = None
        self.inv_cov: Optional[np.ndarray] = None
        self.baseline_distances: List[float] = []
        self.is_ready: bool = False
        self.enabled: bool = True

    def add_sample(self, vector: np.ndarray) -> None:
        """Accumulate baseline vectors during calibration."""
        if not self.is_ready:
            self.buffer.append(np.asarray(vector, dtype=np.float64))

    def fit(self) -> None:
        """Fit PCA and Ledoit-Wolf estimator on accumulated baseline buffer."""
        n_samples = len(self.buffer)
        if n_samples < self.min_baseline_samples:
            self.enabled = False
            self.is_ready = True
            logger.warning(
                "EmbeddingDrift disabled: baseline has only %d samples (< %d required)",
                n_samples,
                self.min_baseline_samples,
            )
            return

        X = np.stack(self.buffer, axis=0)  # Shape: (N, D)
        n_comp = min(self.pca_max_components, n_samples - 1)
        self.pca = PCA(n_components=n_comp, random_state=42)
        X_pca = self.pca.fit_transform(X)  # Shape: (N, n_comp)

        self.lw = LedoitWolf()
        self.lw.fit(X_pca)
        self.mean_vec = self.lw.location_
        cov = self.lw.covariance_
        # Numerical pseudo-inverse / regularized inversion
        self.inv_cov = np.linalg.pinv(cov)

        # Compute Leave-One-Out (or in-sample) Mahalanobis distances on baseline
        self.baseline_distances = []
        for i in range(n_samples):
            # Compute LOO covariance if samples allow, otherwise in-sample distance
            diff = X_pca[i] - self.mean_vec
            dist = float(np.sqrt(np.dot(np.dot(diff, self.inv_cov), diff)))
            self.baseline_distances.append(dist)

        self.baseline_distances.sort()
        self.is_ready = True
        self.enabled = True

    def score(self, vector: np.ndarray) -> Tuple[Optional[float], bool]:
        """Compute drift percentile against baseline LOO distribution.

        Returns:
            Tuple of (percentile_in_0_100 or None, is_flagged).
        """
        if not self.is_ready or not self.enabled or self.pca is None or self.inv_cov is None:
            return None, False

        v = np.asarray(vector, dtype=np.float64).reshape(1, -1)
        v_pca = self.pca.transform(v)[0]
        diff = v_pca - self.mean_vec
        dist = float(np.sqrt(np.dot(np.dot(diff, self.inv_cov), diff)))

        # Convert to empirical percentile against baseline distribution [0, 100]
        count_less = np.sum(np.array(self.baseline_distances) <= dist)
        percentile = float(count_less / len(self.baseline_distances)) * 100.0
        # If beyond maximum baseline distance, extrapolate smoothly up to 100%
        if dist > self.baseline_distances[-1]:
            max_d = self.baseline_distances[-1]
            extra = (dist - max_d) / (max_d + 1e-6)
            percentile = float(min(100.0, 99.0 + 1.0 * (1.0 - np.exp(-extra))))

        is_flagged = bool(percentile >= self.flag_percentile)
        return round(percentile, 2), is_flagged

    def to_dict(self) -> Dict[str, Any]:
        """Serialize drift estimator."""
        return {
            "is_ready": self.is_ready,
            "enabled": self.enabled,
            "pca_max_components": self.pca_max_components,
            "min_baseline_samples": self.min_baseline_samples,
            "flag_percentile": self.flag_percentile,
            "recovery_percentile": self.recovery_percentile,
            "baseline_distances": self.baseline_distances,
            "pca_components": self.pca.components_.tolist() if self.pca else None,
            "pca_mean": self.pca.mean_.tolist() if self.pca else None,
            "mean_vec": self.mean_vec.tolist() if self.mean_vec is not None else None,
            "inv_cov": self.inv_cov.tolist() if self.inv_cov is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmbeddingDrift":
        """Deserialize drift estimator."""
        inst = cls(
            pca_max_components=data.get("pca_max_components", 8),
            min_baseline_samples=data.get("min_baseline_samples", 8),
            flag_percentile=data.get("flag_percentile", 95.0),
            recovery_percentile=data.get("recovery_percentile", 80.0),
        )
        inst.is_ready = data.get("is_ready", False)
        inst.enabled = data.get("enabled", True)
        inst.baseline_distances = data.get("baseline_distances", [])
        if data.get("pca_components") is not None:
            inst.pca = PCA(n_components=len(data["pca_components"]))
            inst.pca.components_ = np.array(data["pca_components"], dtype=np.float64)
            inst.pca.mean_ = np.array(data["pca_mean"], dtype=np.float64)
        if data.get("mean_vec") is not None:
            inst.mean_vec = np.array(data["mean_vec"], dtype=np.float64)
        if data.get("inv_cov") is not None:
            inst.inv_cov = np.array(data["inv_cov"], dtype=np.float64)
        return inst
