"""Hysteresis state machine managing calibrating -> normal -> watch -> alert transitions."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from alerting.core.config import AlertConfig


class AlertStateMachine:
    """State machine with temporal hysteresis, step-down exit rules, and cooldown."""

    VALID_STATES = ("calibrating", "normal", "watch", "alert", "invalid")

    def __init__(self, config: AlertConfig) -> None:
        self.config = config
        self.state: str = "calibrating"

        # Sliding window history of (feature_flagged_set, drift_flagged_bool, all_clean_bool)
        self.history: deque[Tuple[Set[str], bool, bool]] = deque(
            maxlen=config.window_history_len
        )

        # Consecutive clean windows counter (for exit rules)
        self.consecutive_clean_count: int = 0

        # Cooldown management: after stepping down from alert, avoid re-alert unless score exceeds peak
        self.cooldown_remaining: int = 0
        self.last_alert_peak_score: float = 0.0

    def compute_severity_score(
        self,
        z_scores: Dict[str, float],
        cusum_maxes: Dict[str, float],
        drift_percentile: Optional[float],
    ) -> float:
        """Compute monotonic severity score in [0.0, 1.0].

        Mapping principles:
        - 0.0: at baseline
        - ~0.5: at the watch threshold (|z| ~ 2.5 or drift ~ 95%)
        - 1.0: at or beyond the alert threshold (|z| >= 4.0 or CUSUM >= 2*h)
        """
        # Feature evidence
        max_abs_z = max((abs(z) for z in z_scores.values()), default=0.0)
        max_cusum = max(cusum_maxes.values(), default=0.0)

        # Normalize z: 0 at z=0, 0.5 at z=2.5, 1.0 at z>=4.5
        score_z = float(min(1.0, max_abs_z / 4.5))

        # Normalize CUSUM: 0 at CUSUM=0, 0.5 at CUSUM=h(5), 1.0 at CUSUM=2*h(10)
        score_cusum = float(min(1.0, max_cusum / (2.0 * self.config.cusum_h)))

        # Normalize Drift: 0 at percentile <= 50, 0.5 at 95, 1.0 at 99+
        if drift_percentile is not None and drift_percentile > 50.0:
            score_drift = float(min(1.0, (drift_percentile - 50.0) / 49.0))
        else:
            score_drift = 0.0

        # Max evidence combination with smooth saturation
        raw_score = max(score_z, score_cusum, score_drift)
        return round(float(raw_score), 4)

    def update(
        self,
        is_calibrated: bool,
        flagged_features: Set[str],
        drift_flagged: bool,
        z_scores: Dict[str, float],
        drift_percentile: Optional[float],
        severity_score: float,
    ) -> str:
        """Evaluate state transition rules given current window evidence."""
        if not is_calibrated:
            self.state = "calibrating"
            return self.state

        # Check clean condition for exit rules: all |z| < 1.5 and drift < 80th percentile
        all_z_clean = all(
            abs(z) < self.config.z_recovery_threshold for z in z_scores.values()
        )
        drift_clean = (
            drift_percentile is None
            or drift_percentile < self.config.drift_percentile_recovery
        )
        is_window_clean = all_z_clean and drift_clean

        # Determine if THIS window meets watch or alert triggers
        has_feature_flag = len(flagged_features) >= 1
        window_watch_active = has_feature_flag or drift_flagged

        window_alert_active = False
        if self.config.modality == "speech":
            # Speech: drift flags AND at least one feature flags
            window_alert_active = drift_flagged and has_feature_flag
        else:
            # Facial: (drift flags AND at least one feature flags) OR (>= 2 groups flag)
            cond1 = drift_flagged and has_feature_flag
            groups_flagged = set()
            for group_name, group_feats in self.config.feature_groups.items():
                if any(f in flagged_features for f in group_feats):
                    groups_flagged.add(group_name)
            cond2 = len(groups_flagged) >= 2
            window_alert_active = cond1 or cond2

        # Record into history: (window_watch_active, window_alert_active, is_window_clean)
        self.history.append((window_watch_active, window_alert_active, is_window_clean))

        # Update clean streak
        if is_window_clean:
            self.consecutive_clean_count += 1
        else:
            self.consecutive_clean_count = 0

        # Decrement cooldown counter if active
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1

        # Evaluate persistence in last N windows (>= 3 of last 5 windows)
        watch_flag_count = sum(1 for (w_act, _, _) in self.history if w_act)
        alert_flag_count = sum(1 for (_, a_act, _) in self.history if a_act)

        persisting_watch = watch_flag_count >= self.config.persist_required_flags
        persisting_alert = alert_flag_count >= self.config.persist_required_flags

        # Evaluate state transitions
        if self.state in ("calibrating", "normal"):
            if persisting_alert:
                if (
                    self.cooldown_remaining > 0
                    and severity_score <= self.last_alert_peak_score
                ):
                    self.state = "watch"
                else:
                    self.state = "alert"
                    self.last_alert_peak_score = severity_score
            elif persisting_watch:
                self.state = "watch"
            else:
                self.state = "normal"

        elif self.state == "watch":
            if persisting_alert:
                if (
                    self.cooldown_remaining > 0
                    and severity_score <= self.last_alert_peak_score
                ):
                    self.state = "watch"
                else:
                    self.state = "alert"
                    self.last_alert_peak_score = severity_score
            elif (
                self.consecutive_clean_count >= self.config.exit_consecutive_clean
            ):
                self.state = "normal"
                self.consecutive_clean_count = 0
            # Otherwise maintain watch state

        elif self.state == "alert":
            self.last_alert_peak_score = max(self.last_alert_peak_score, severity_score)
            # Step down alert -> watch -> normal, NEVER jump directly
            if self.consecutive_clean_count >= self.config.exit_consecutive_clean:
                self.state = "watch"
                self.cooldown_remaining = self.config.cooldown_windows
                self.consecutive_clean_count = 0
            # Otherwise maintain alert state

        return self.state

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state machine."""
        return {
            "state": self.state,
            "consecutive_clean_count": self.consecutive_clean_count,
            "cooldown_remaining": self.cooldown_remaining,
            "last_alert_peak_score": self.last_alert_peak_score,
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, config: AlertConfig, data: Dict[str, Any]) -> "AlertStateMachine":
        """Deserialize state machine."""
        inst = cls(config)
        inst.state = data.get("state", "calibrating")
        inst.consecutive_clean_count = data.get("consecutive_clean_count", 0)
        inst.cooldown_remaining = data.get("cooldown_remaining", 0)
        inst.last_alert_peak_score = data.get("last_alert_peak_score", 0.0)
        inst.history = deque(
            [
                (item[0], item[1], item[2])
                for item in data.get("history", [])
            ],
            maxlen=config.window_history_len,
        )
        return inst
