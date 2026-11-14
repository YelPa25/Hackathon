"""Robust baseline modeling using Median and Median Absolute Deviation (MAD)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np


class RobustBaseline:
    """Robust baseline estimating feature medians and scale via MAD.

    Two-level MAD floor:
    1. Absolute floor ``mad_floor`` (default 1e-4): prevents division by zero
       for constant or near-constant features.
    2. Relative floor ``mad_relative_floor`` (default 0.05): ensures the
       effective MAD is at least 5% of |median|. This prevents z-score
       blow-up when the calibration sample size is small and the sample MAD
       underestimates the true noise scale.
    """

    def __init__(
        self,
        features: List[str],
        calibration_n: int = 40,
        mad_floor: float = 1e-4,
        mad_relative_floor: float = 0.05,
    ) -> None:
        self.features = list(features)
        self.calibration_n = calibration_n
        self.mad_floor = mad_floor
        self.mad_relative_floor = mad_relative_floor

        self.buffer: List[Dict[str, float]] = []
        self.medians: Dict[str, float] = {}
        self.mads: Dict[str, float] = {}
        self.is_ready: bool = False
        self.n_samples: int = 0
        # mad_relative_floor may not be present in old serialised state files
        if not hasattr(self, "mad_relative_floor"):
            self.mad_relative_floor = 0.05

    def add_sample(self, sample: Dict[str, float]) -> bool:
        """Add a calibration sample. Returns True when calibration completes."""
        if self.is_ready:
            return True

        self.buffer.append(sample)
        self.n_samples = len(self.buffer)

        if self.n_samples >= self.calibration_n:
            self.fit()
            return True
        return False

    def fit(self) -> None:
        """Fit median and MAD from accumulated buffer."""
        if not self.buffer:
            return

        self.medians = {}
        self.mads = {}

        for feat in self.features:
            vals = np.array([s[feat] for s in self.buffer if feat in s], dtype=np.float64)
            if len(vals) == 0:
                self.medians[feat] = 0.0
                self.mads[feat] = self.mad_floor
                continue

            med = float(np.median(vals))
            # MAD = median(|x - median(x)|)
            mad = float(np.median(np.abs(vals - med)))
            # Absolute floor: prevents division by zero for constant features
            mad = max(mad, self.mad_floor)
            # Relative floor: bounds z-scores when calibration n is small and
            # the sample MAD underestimates the true scale.
            rel_floor = self.mad_relative_floor * abs(med)
            mad = max(mad, rel_floor)

            self.medians[feat] = med
            self.mads[feat] = mad

        self.is_ready = True

    def compute_z(self, sample: Dict[str, float]) -> Dict[str, float]:
        """Compute robust z-scores: z = (x - median) / (1.4826 * MAD)."""
        if not self.is_ready:
            return {feat: 0.0 for feat in self.features}

        z_scores: Dict[str, float] = {}
        for feat in self.features:
            val = sample.get(feat, 0.0)
            med = self.medians.get(feat, 0.0)
            mad = self.mads.get(feat, self.mad_floor)
            # 1.4826 scale factor normalizes MAD to standard deviation for normal distribution
            denom = 1.4826 * mad
            if denom <= 0:
                denom = self.mad_floor
            z = (val - med) / denom
            z_scores[feat] = float(z)

        return z_scores

    def update_ewma(self, sample: Dict[str, float], alpha: float = 0.01) -> None:
        """Slow EWMA update of baseline medians during confirmed normal state."""
        if not self.is_ready:
            return
        for feat in self.features:
            if feat in sample:
                val = float(sample[feat])
                cur_med = self.medians[feat]
                new_med = (1.0 - alpha) * cur_med + alpha * val
                self.medians[feat] = new_med
                # Slowly update MAD
                diff = abs(val - new_med)
                cur_mad = self.mads[feat]
                self.mads[feat] = max(self.mad_floor, (1.0 - alpha) * cur_mad + alpha * diff)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state for persistent caching."""
        return {
            "features": self.features,
            "calibration_n": self.calibration_n,
            "mad_floor": self.mad_floor,
            "mad_relative_floor": self.mad_relative_floor,
            "is_ready": self.is_ready,
            "n_samples": self.n_samples,
            "medians": self.medians,
            "mads": self.mads,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RobustBaseline":
        """Reconstruct baseline from dictionary."""
        inst = cls(
            features=data["features"],
            calibration_n=data["calibration_n"],
            mad_floor=data.get("mad_floor", 1e-4),
            mad_relative_floor=data.get("mad_relative_floor", 0.05),
        )
        inst.is_ready = data.get("is_ready", False)
        inst.n_samples = data.get("n_samples", 0)
        inst.medians = data.get("medians", {})
        inst.mads = data.get("mads", {})
        return inst
