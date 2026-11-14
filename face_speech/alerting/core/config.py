"""Configuration dataclasses for alerting modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from typing import Any, Dict, List, Optional
import yaml


@dataclass
class AlertConfig:
    """Modality-specific configuration for alerting engine."""

    modality: str = "generic"
    calibration_n: int = 40  # Default: 40 windows for facial, 7 checkin or 20 continuous for speech
    features: List[str] = field(default_factory=list)
    feature_groups: Dict[str, List[str]] = field(default_factory=dict)

    # Embedding drift settings
    embedding_source: str = "au_means"  # "au_means" for facial, "layer" for speech
    embedding_layer: str = "6"          # Default XLS-R layer for speech
    drift_percentile_flag: float = 95.0
    drift_percentile_recovery: float = 80.0
    min_baseline_drift_samples: int = 8
    pca_max_components: int = 8

    # Statistical & CUSUM thresholds
    mad_floor: float = 1e-4
    # Relative MAD floor as a fraction of |median|. Applied after fitting:
    # effective_mad = max(mad, mad_relative_floor * |median|).
    # Prevents z-score blow-up when calibration sample size is small and the
    # sample MAD underestimates the true scale. Set 0.0 to disable.
    mad_relative_floor: float = 0.05
    z_flag_threshold: float = 2.5
    z_recovery_threshold: float = 1.5
    cusum_k: float = 0.5
    cusum_h: float = 5.0

    # Hysteresis state machine parameters
    window_history_len: int = 5
    persist_required_flags: int = 3
    exit_consecutive_clean: int = 5
    cooldown_windows: int = 5

    # Adaptation
    adapt_ewma_alpha: float = 0.01  # Slow EWMA update rate during normal state

    @classmethod
    def from_file(cls, path: str) -> "AlertConfig":
        """Load configuration from YAML or JSON file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            if path.endswith(".json"):
                data = json.load(f)
            else:
                data = yaml.safe_load(f)
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)
