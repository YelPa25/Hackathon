"""Alerting engine combining baseline, CUSUM, drift, state machine, and explainability."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from alerting.core.baseline import RobustBaseline
from alerting.core.config import AlertConfig
from alerting.core.cusum import TwoSidedCUSUM
from alerting.core.drift import EmbeddingDrift
from alerting.core.explain import build_contributors, build_reason_string
from alerting.core.state import AlertStateMachine


class AlertNode:
    """Modality-agnostic alerting processor for streaming records."""

    def __init__(
        self,
        config: AlertConfig,
        subject_id: str = "astronaut_1",
        adapt: bool = False,
    ) -> None:
        self.config = config
        self.subject_id = subject_id
        self.adapt = adapt

        self.baseline = RobustBaseline(
            features=config.features,
            calibration_n=config.calibration_n,
            mad_floor=config.mad_floor,
            mad_relative_floor=config.mad_relative_floor,
        )

        self.cusums: Dict[str, TwoSidedCUSUM] = {
            feat: TwoSidedCUSUM(k=config.cusum_k, h=config.cusum_h)
            for feat in config.features
        }

        self.drift = EmbeddingDrift(
            pca_max_components=config.pca_max_components,
            min_baseline_samples=config.min_baseline_drift_samples,
            flag_percentile=config.drift_percentile_flag,
            recovery_percentile=config.drift_percentile_recovery,
        )

        self.state_machine = AlertStateMachine(config)

        # Persistence counters for how many recent windows each feature has flagged
        self.flagged_window_counters: Dict[str, int] = {feat: 0 for feat in config.features}

        # Gap count for invalid windows
        self.invalid_gap_count: int = 0
        self.last_valid_state: str = "calibrating"

    def _extract_vector(self, record: Dict[str, Any]) -> Optional[np.ndarray]:
        """Extract multi-dimensional vector for drift analysis based on adapter config."""
        if self.config.embedding_source == "au_means":
            # Facial modality: vector of AU mean intensities
            au_means = []
            feats = record.get("features", {})
            for k in sorted(feats.keys()):
                if k.startswith("au") and k.endswith("_mean"):
                    au_means.append(float(feats[k]))
            if au_means:
                return np.array(au_means, dtype=np.float64)
            return None

        if self.config.embedding_source == "layer":
            # Speech modality: XLS-R embedding vector from configured layer
            emb = record.get("embedding", {})
            vectors = emb.get("vectors", {})
            layer_key = str(self.config.embedding_layer)
            if layer_key in vectors:
                vec = vectors[layer_key]
                if isinstance(vec, list) and len(vec) > 0:
                    return np.array(vec, dtype=np.float64)
            return None

        return None

    def process_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Process one incoming extractor JSONL record and emit contract-valid alert record.

        Contract:
        {
          "modality": "facial" | "speech",
          "t": "<copied from the input record>",
          "subject_id": "<from CLI or config, default 'astronaut_1'>",
          "state": "calibrating" | "normal" | "watch" | "alert" | "invalid",
          "score": <float 0-1>,
          "quality": <float 0-1>,
          "drift": { "percentile": <float|null>, "enabled": <bool> },
          "contributors": [ { "feature": "...", "z": <float>, "direction": "up"|"down", "cusum": <float>, "windows_flagged": <int> } ],
          "reason": "<plain-language sentence>",
          "baseline": { "n": <int>, "ready": <bool> }
        }
        """
        modality = record.get("modality", self.config.modality)
        t_iso = record.get("t", "")
        quality = float(record.get("quality", 0.0))
        is_valid = bool(record.get("valid", False))
        features_dict = record.get("features", {})

        # Rule 1: Quality Gate
        if not is_valid:
            self.invalid_gap_count += 1
            return {
                "modality": modality,
                "t": t_iso,
                "subject_id": self.subject_id,
                "state": "invalid",
                "score": 0.0,
                "quality": quality,
                "drift": {
                    "percentile": None,
                    "enabled": self.drift.enabled,
                },
                "contributors": [],
                "reason": (
                    f"Window invalid (quality {quality:.2f} below threshold); "
                    f"holding previous state '{self.last_valid_state}' (gap: {self.invalid_gap_count} windows)."
                ),
                "baseline": {
                    "n": self.baseline.n_samples,
                    "ready": self.baseline.is_ready,
                },
            }

        # Valid window: reset gap counter
        self.invalid_gap_count = 0
        vector = self._extract_vector(record)

        # Rule 2: Calibration
        if not self.baseline.is_ready:
            self.baseline.add_sample(features_dict)
            if vector is not None:
                self.drift.add_sample(vector)

            if self.baseline.is_ready:
                # Baseline just became ready
                self.drift.fit()

            self.last_valid_state = "calibrating"
            return {
                "modality": modality,
                "t": t_iso,
                "subject_id": self.subject_id,
                "state": "calibrating",
                "score": 0.0,
                "quality": quality,
                "drift": {
                    "percentile": None,
                    "enabled": self.drift.enabled,
                },
                "contributors": [],
                "reason": (
                    f"Calibrating baseline: {self.baseline.n_samples}/{self.config.calibration_n} "
                    f"valid windows collected."
                ),
                "baseline": {
                    "n": self.baseline.n_samples,
                    "ready": self.baseline.is_ready,
                },
            }

        # Baseline is ready: compute robust z-scores
        z_scores = self.baseline.compute_z(features_dict)

        # Update per-feature CUSUM
        flagged_features: Set[str] = set()
        cusum_maxes: Dict[str, float] = {}

        for feat in self.config.features:
            z = z_scores.get(feat, 0.0)
            c_pos, c_neg, c_flag = self.cusums[feat].update(z)
            c_max = max(c_pos, c_neg)
            cusum_maxes[feat] = c_max

            # Rule 6: Feature flags when |z| >= 2.5 or CUSUM exceeds h
            is_feat_flagged = (abs(z) >= self.config.z_flag_threshold) or c_flag
            if is_feat_flagged:
                flagged_features.add(feat)
                self.flagged_window_counters[feat] = self.flagged_window_counters.get(feat, 0) + 1
            else:
                self.flagged_window_counters[feat] = max(
                    0, self.flagged_window_counters.get(feat, 0) - 1
                )

        # Evaluate Embedding Drift
        drift_percentile: Optional[float] = None
        drift_flagged: bool = False
        if vector is not None and self.drift.enabled:
            drift_percentile, drift_flagged = self.drift.score(vector)

        # Severity score
        severity_score = self.state_machine.compute_severity_score(
            z_scores=z_scores,
            cusum_maxes=cusum_maxes,
            drift_percentile=drift_percentile,
        )

        # State transition update
        current_state = self.state_machine.update(
            is_calibrated=True,
            flagged_features=flagged_features,
            drift_flagged=drift_flagged,
            z_scores=z_scores,
            drift_percentile=drift_percentile,
            severity_score=severity_score,
        )
        self.last_valid_state = current_state

        # Optional Adaptation (slow EWMA update only while state is normal)
        if self.adapt and current_state == "normal":
            self.baseline.update_ewma(features_dict, alpha=self.config.adapt_ewma_alpha)

        # If state returns to normal, reset CUSUM trackers
        if current_state == "normal":
            for c in self.cusums.values():
                c.reset()

        # Build explainability payload
        contributors = build_contributors(
            z_scores=z_scores,
            cusum_tracker=cusum_maxes,
            flagged_counters=self.flagged_window_counters,
            top_k=5,
        )

        reason = build_reason_string(
            state=current_state,
            top_contributors=contributors,
            current_values=features_dict,
            baseline_medians=self.baseline.medians,
            drift_percentile=drift_percentile,
            drift_flagged=drift_flagged,
        )

        return {
            "modality": modality,
            "t": t_iso,
            "subject_id": self.subject_id,
            "state": current_state,
            "score": severity_score,
            "quality": quality,
            "drift": {
                "percentile": drift_percentile,
                "enabled": self.drift.enabled,
            },
            "contributors": contributors,
            "reason": reason,
            "baseline": {
                "n": self.baseline.n_samples,
                "ready": self.baseline.is_ready,
            },
        }

    def save_state(self, path: str) -> None:
        """Persist baseline and state machine to file."""
        state = {
            "config": self.config.to_dict(),
            "subject_id": self.subject_id,
            "adapt": self.adapt,
            "baseline": self.baseline.to_dict(),
            "drift": self.drift.to_dict(),
            "state_machine": self.state_machine.to_dict(),
            "cusums": {feat: c.to_dict() for feat, c in self.cusums.items()},
            "flagged_window_counters": self.flagged_window_counters,
            "invalid_gap_count": self.invalid_gap_count,
            "last_valid_state": self.last_valid_state,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    @classmethod
    def load_state(cls, path: str) -> "AlertNode":
        """Load persisted node state from file."""
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)

        cfg = AlertConfig(**state["config"])
        node = cls(config=cfg, subject_id=state["subject_id"], adapt=state.get("adapt", False))
        node.baseline = RobustBaseline.from_dict(state["baseline"])
        node.drift = EmbeddingDrift.from_dict(state["drift"])
        node.state_machine = AlertStateMachine.from_dict(cfg, state["state_machine"])
        node.cusums = {
            feat: TwoSidedCUSUM.from_dict(data)
            for feat, data in state.get("cusums", {}).items()
        }
        node.flagged_window_counters = state.get("flagged_window_counters", {})
        node.invalid_gap_count = state.get("invalid_gap_count", 0)
        node.last_valid_state = state.get("last_valid_state", "calibrating")
        return node
