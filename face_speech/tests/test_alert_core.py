"""Unit tests for the alerting core: baseline, CUSUM, state machine, drift, and node."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict

import numpy as np
import pytest

from alerting.core.baseline import RobustBaseline
from alerting.core.config import AlertConfig
from alerting.core.cusum import TwoSidedCUSUM
from alerting.core.drift import EmbeddingDrift
from alerting.core.node import AlertNode
from alerting.core.state import AlertStateMachine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kwargs: Any) -> AlertConfig:
    defaults = dict(
        modality="test",
        calibration_n=5,
        features=["a", "b"],
        feature_groups={"g1": ["a"], "g2": ["b"]},
        embedding_source="au_means",
        z_flag_threshold=3.0,
        z_recovery_threshold=1.5,
        cusum_k=0.5,
        cusum_h=7.0,
        window_history_len=5,
        persist_required_flags=4,
        exit_consecutive_clean=5,
        cooldown_windows=3,
        drift_percentile_flag=98.0,
        drift_percentile_recovery=80.0,
        min_baseline_drift_samples=8,
        pca_max_components=4,
        mad_floor=1e-4,
        mad_relative_floor=0.0,  # disable relative floor in unit tests for precision
    )
    defaults.update(kwargs)
    return AlertConfig(**defaults)


def _make_baseline(values_per_feat: Dict[str, list], mad_relative_floor: float = 0.0) -> RobustBaseline:
    """Fit a baseline from explicit per-feature value lists."""
    features = list(values_per_feat.keys())
    n = len(next(iter(values_per_feat.values())))
    bl = RobustBaseline(features=features, calibration_n=n, mad_floor=1e-4,
                        mad_relative_floor=mad_relative_floor)
    for i in range(n):
        sample = {feat: vals[i] for feat, vals in values_per_feat.items()}
        bl.add_sample(sample)
    return bl


# ---------------------------------------------------------------------------
# RobustBaseline
# ---------------------------------------------------------------------------

class TestRobustBaseline:
    def test_z_correctness(self) -> None:
        """z = (x - median) / (1.4826 * MAD)."""
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]  # median=3, MAD=1
        bl = _make_baseline({"x": vals})
        assert bl.is_ready
        assert bl.medians["x"] == pytest.approx(3.0)
        assert bl.mads["x"] == pytest.approx(1.0)
        z = bl.compute_z({"x": 5.0})
        expected_z = (5.0 - 3.0) / (1.4826 * 1.0)
        assert z["x"] == pytest.approx(expected_z, abs=1e-9)

    def test_constant_feature_mad_floor(self) -> None:
        """Constant feature must not raise; MAD is clamped to mad_floor."""
        bl = _make_baseline({"x": [1.0, 1.0, 1.0, 1.0, 1.0]})
        assert bl.mads["x"] == pytest.approx(1e-4)
        z = bl.compute_z({"x": 1.5})
        # z = (1.5 - 1.0) / (1.4826 * 1e-4) ≈ 3372 — large but finite
        assert np.isfinite(z["x"])

    def test_relative_floor_applied(self) -> None:
        """Relative floor activates when sample MAD is too small."""
        # With only 3 samples from a low-variance distribution, sample MAD may be tiny
        bl = _make_baseline({"x": [100.0, 100.0, 100.0]}, mad_relative_floor=0.05)
        # Relative floor = 0.05 * 100 = 5.0 >> MAD=0 → effective MAD=5.0
        assert bl.mads["x"] == pytest.approx(5.0)

    def test_not_ready_before_calibration_n(self) -> None:
        bl = RobustBaseline(features=["a"], calibration_n=5)
        for i in range(4):
            bl.add_sample({"a": float(i)})
        assert not bl.is_ready
        bl.add_sample({"a": 4.0})
        assert bl.is_ready

    def test_serialisation_roundtrip(self) -> None:
        bl = _make_baseline({"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [5.0, 4.0, 3.0, 2.0, 1.0]})
        d = bl.to_dict()
        bl2 = RobustBaseline.from_dict(d)
        assert bl2.is_ready
        assert bl2.medians["a"] == pytest.approx(bl.medians["a"])
        assert bl2.mads["a"] == pytest.approx(bl.mads["a"])

    def test_ewma_update_shifts_median(self) -> None:
        bl = _make_baseline({"a": [0.0] * 5})
        bl.update_ewma({"a": 10.0}, alpha=0.5)
        assert bl.medians["a"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# TwoSidedCUSUM
# ---------------------------------------------------------------------------

class TestTwoSidedCUSUM:
    def test_no_flag_at_zero_input(self) -> None:
        c = TwoSidedCUSUM(k=0.5, h=7.0)
        for _ in range(50):
            pos, neg, flagged = c.update(0.0)
        assert not flagged
        assert pos == 0.0
        assert neg == 0.0

    def test_positive_drift_flags(self) -> None:
        c = TwoSidedCUSUM(k=0.5, h=7.0)
        flagged = False
        for _ in range(20):
            _, _, flagged = c.update(1.0)
        assert flagged, "Sustained positive z=1.0 must eventually exceed h=7.0"

    def test_negative_drift_flags(self) -> None:
        c = TwoSidedCUSUM(k=0.5, h=7.0)
        flagged = False
        for _ in range(20):
            _, _, flagged = c.update(-1.0)
        assert flagged

    def test_reset_clears_accumulators(self) -> None:
        c = TwoSidedCUSUM(k=0.5, h=7.0)
        for _ in range(15):
            c.update(1.0)
        c.reset()
        assert c.pos == 0.0
        assert c.neg == 0.0
        _, _, flagged = c.update(0.0)
        assert not flagged

    def test_serialisation_roundtrip(self) -> None:
        c = TwoSidedCUSUM(k=0.5, h=5.0)
        c.update(2.0)
        d = c.to_dict()
        c2 = TwoSidedCUSUM.from_dict(d)
        assert c2.pos == pytest.approx(c.pos)
        assert c2.h == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# AlertStateMachine
# ---------------------------------------------------------------------------

class TestAlertStateMachine:
    def _pump(
        self,
        sm: AlertStateMachine,
        n: int,
        feature_flagged: bool = False,
        drift_flagged: bool = False,
        is_clean: bool = True,
        z_scores: Dict[str, float] = None,
    ) -> str:
        """Drive the state machine n times."""
        if z_scores is None:
            z_scores = {"a": 0.0, "b": 0.0}
        state = "normal"
        for _ in range(n):
            flagged = {"a", "b"} if feature_flagged else set()
            state = sm.update(
                is_calibrated=True,
                flagged_features=flagged,
                drift_flagged=drift_flagged,
                z_scores=z_scores,
                drift_percentile=99.0 if drift_flagged else 50.0,
                severity_score=0.9 if (feature_flagged or drift_flagged) else 0.1,
            )
        return state

    def test_starts_calibrating(self) -> None:
        cfg = _make_config()
        sm = AlertStateMachine(cfg)
        state = sm.update(
            is_calibrated=False, flagged_features=set(), drift_flagged=False,
            z_scores={}, drift_percentile=None, severity_score=0.0,
        )
        assert state == "calibrating"

    def test_normal_with_no_flags(self) -> None:
        cfg = _make_config()
        sm = AlertStateMachine(cfg)
        sm.state = "normal"
        state = self._pump(sm, 10, feature_flagged=False)
        assert state == "normal"

    def test_reaches_watch_with_persist(self) -> None:
        # persist_required_flags=4, so need 4 of last 5 windows flagging.
        # Only flag feature "a" (group g1 only) with |z|<z_th to avoid triggering alert.
        cfg = _make_config(persist_required_flags=4)
        sm = AlertStateMachine(cfg)
        sm.state = "normal"
        z_low = {"a": 3.5, "b": 0.0}  # only one feature, one group → watch, not alert
        for _ in range(4):
            state = sm.update(
                is_calibrated=True,
                flagged_features={"a"},
                drift_flagged=False,
                z_scores=z_low,
                drift_percentile=50.0,
                severity_score=0.5,
            )
        assert state == "watch"

    def test_no_watch_without_persistence(self) -> None:
        cfg = _make_config(persist_required_flags=4)
        sm = AlertStateMachine(cfg)
        sm.state = "normal"
        # Only 3 of 5 windows flag (persist=4 required)
        for i in range(5):
            flagged = {"a"} if i < 3 else set()
            state = sm.update(
                is_calibrated=True, flagged_features=flagged, drift_flagged=False,
                z_scores={"a": 3.5 if i < 3 else 0.0, "b": 0.0},
                drift_percentile=50.0, severity_score=0.6 if i < 3 else 0.0,
            )
        assert state == "normal"

    def test_reaches_alert_facial(self) -> None:
        """Facial: >=2 groups flagging in 4/5 windows triggers alert."""
        cfg = _make_config(modality="facial", persist_required_flags=4)
        sm = AlertStateMachine(cfg)
        sm.state = "normal"
        # Drift + feature flag together
        state = self._pump(sm, 5, feature_flagged=True, drift_flagged=True,
                           z_scores={"a": 4.0, "b": 4.0})
        assert state == "alert"

    def test_reaches_alert_speech(self) -> None:
        """Speech: drift AND feature flagging in 4/5 windows triggers alert."""
        cfg = _make_config(modality="speech", persist_required_flags=4)
        sm = AlertStateMachine(cfg)
        sm.state = "normal"
        state = self._pump(sm, 5, feature_flagged=True, drift_flagged=True,
                           z_scores={"a": 4.0, "b": 0.0})
        assert state == "alert"

    def test_no_jump_from_alert_to_normal(self) -> None:
        """Alert must step down: alert -> watch -> normal (never jump)."""
        cfg = _make_config(persist_required_flags=4, exit_consecutive_clean=3)
        sm = AlertStateMachine(cfg)
        sm.state = "alert"
        # Pump 3 clean windows: should step to watch, NOT normal
        state = self._pump(sm, 3, feature_flagged=False, is_clean=True,
                           z_scores={"a": 0.0, "b": 0.0})
        assert state == "watch", f"Expected watch after stepping down from alert, got {state}"

    def test_step_down_to_normal_from_watch(self) -> None:
        cfg = _make_config(persist_required_flags=4, exit_consecutive_clean=5)
        sm = AlertStateMachine(cfg)
        sm.state = "watch"
        # First step alert -> watch already done; now pump 5 clean windows
        state = self._pump(sm, 5, feature_flagged=False, z_scores={"a": 0.0, "b": 0.0})
        assert state == "normal"

    def test_cooldown_prevents_immediate_re_alert(self) -> None:
        # cooldown_windows=10 to ensure it doesn't expire during the test pump
        cfg = _make_config(modality="facial", persist_required_flags=4,
                           exit_consecutive_clean=5, cooldown_windows=10)
        sm = AlertStateMachine(cfg)
        sm.state = "alert"
        sm.last_alert_peak_score = 0.9
        # Step down from alert -> watch via clean windows
        self._pump(sm, 5, feature_flagged=False, z_scores={"a": 0.0, "b": 0.0})
        assert sm.state == "watch"
        # Cooldown is active (10 windows); re-pump 4 alert windows with LOWER severity
        # → blocked because severity_score (0.5) <= last_alert_peak_score (0.9)
        for _ in range(4):
            state = sm.update(
                is_calibrated=True,
                flagged_features={"a", "b"},
                drift_flagged=True,
                z_scores={"a": 3.5, "b": 3.5},
                drift_percentile=99.0,
                severity_score=0.5,  # below the peak score of 0.9
            )
        assert sm.state == "watch", (
            "Cooldown should prevent re-alert when severity does not exceed peak"
        )

    def test_invalid_windows_do_not_update_state(self) -> None:
        """AlertNode must hold state on invalid windows (tested via node)."""
        cfg = _make_config(calibration_n=5)
        node = AlertNode(config=cfg)
        # Calibrate
        for i in range(5):
            node.process_record({
                "modality": "test", "t": f"t{i}", "features": {"a": 1.0, "b": 2.0},
                "quality": 1.0, "valid": True,
            })
        # Put in known state
        node.state_machine.state = "watch"
        # Send invalid windows
        for _ in range(10):
            rec = node.process_record({
                "modality": "test", "t": "ti", "features": {},
                "quality": 0.0, "valid": False,
            })
            assert rec["state"] == "invalid"
        # State machine itself untouched
        assert node.state_machine.state == "watch"

    def test_serialisation_roundtrip(self) -> None:
        cfg = _make_config()
        sm = AlertStateMachine(cfg)
        sm.state = "watch"
        sm.consecutive_clean_count = 3
        sm.cooldown_remaining = 2
        d = sm.to_dict()
        sm2 = AlertStateMachine.from_dict(cfg, d)
        assert sm2.state == "watch"
        assert sm2.consecutive_clean_count == 3
        assert sm2.cooldown_remaining == 2


# ---------------------------------------------------------------------------
# EmbeddingDrift
# ---------------------------------------------------------------------------

class TestEmbeddingDrift:
    def test_disabled_when_too_few_samples(self) -> None:
        drift = EmbeddingDrift(min_baseline_samples=8)
        for _ in range(5):
            drift.add_sample(np.random.randn(10))
        drift.fit()
        assert not drift.enabled

    def test_enabled_with_enough_samples(self) -> None:
        rng = np.random.default_rng(0)
        drift = EmbeddingDrift(min_baseline_samples=8)
        for _ in range(10):
            drift.add_sample(rng.standard_normal(20))
        drift.fit()
        assert drift.enabled

    def test_score_returns_percentile_and_flag(self) -> None:
        rng = np.random.default_rng(1)
        drift = EmbeddingDrift(min_baseline_samples=8, flag_percentile=90.0)
        X = rng.standard_normal((15, 20))
        for row in X:
            drift.add_sample(row)
        drift.fit()
        pct, flagged = drift.score(X[0])
        assert pct is not None
        assert 0.0 <= pct <= 100.0
        assert isinstance(flagged, bool)

    def test_outlier_scores_higher_than_inlier(self) -> None:
        rng = np.random.default_rng(2)
        drift = EmbeddingDrift(min_baseline_samples=8)
        X_base = rng.standard_normal((20, 10))
        for row in X_base:
            drift.add_sample(row)
        drift.fit()
        pct_in, _ = drift.score(X_base[0])  # inlier
        pct_out, _ = drift.score(X_base[0] * 100.0 + 50.0)  # extreme outlier
        assert pct_out > pct_in

    def test_serialisation_roundtrip(self) -> None:
        rng = np.random.default_rng(3)
        drift = EmbeddingDrift(min_baseline_samples=8)
        for _ in range(10):
            drift.add_sample(rng.standard_normal(16))
        drift.fit()
        d = drift.to_dict()
        drift2 = EmbeddingDrift.from_dict(d)
        assert drift2.enabled
        vec = rng.standard_normal(16)
        pct1, _ = drift.score(vec)
        pct2, _ = drift2.score(vec)
        assert pct1 == pytest.approx(pct2)


# ---------------------------------------------------------------------------
# AlertNode (integration)
# ---------------------------------------------------------------------------

class TestAlertNode:
    def _make_node(self, **kwargs: Any) -> AlertNode:
        cfg = _make_config(**kwargs)
        return AlertNode(config=cfg)

    def _valid_rec(self, a: float = 1.0, b: float = 2.0) -> Dict[str, Any]:
        return {
            "modality": "test", "t": "2026-01-01T00:00:00+00:00",
            "features": {"a": a, "b": b}, "quality": 1.0, "valid": True,
        }

    def _invalid_rec(self) -> Dict[str, Any]:
        return {
            "modality": "test", "t": "2026-01-01T00:00:00+00:00",
            "features": {}, "quality": 0.0, "valid": False,
        }

    def test_calibrating_during_first_n_records(self) -> None:
        node = self._make_node(calibration_n=5)
        for i in range(4):
            rec = node.process_record(self._valid_rec())
            assert rec["state"] == "calibrating"
            assert rec["baseline"]["ready"] is False

    def test_normal_after_calibration(self) -> None:
        node = self._make_node(calibration_n=5)
        for _ in range(6):
            rec = node.process_record(self._valid_rec())
        assert rec["state"] == "normal"
        assert rec["baseline"]["ready"] is True

    def test_invalid_windows_hold_state(self) -> None:
        node = self._make_node(calibration_n=5)
        for _ in range(5):
            node.process_record(self._valid_rec())
        for _ in range(3):
            rec = node.process_record(self._invalid_rec())
            assert rec["state"] == "invalid"

    def test_output_contract_fields(self) -> None:
        node = self._make_node(calibration_n=5)
        for _ in range(6):
            rec = node.process_record(self._valid_rec())
        required = {"modality", "t", "subject_id", "state", "score", "quality",
                    "drift", "contributors", "reason", "baseline"}
        assert required.issubset(rec.keys())
        assert isinstance(rec["drift"]["enabled"], bool)
        assert rec["drift"]["percentile"] is None or isinstance(rec["drift"]["percentile"], float)
        assert 0.0 <= rec["score"] <= 1.0

    def test_state_persistence_roundtrip(self) -> None:
        """Save and reload preserves baseline."""
        node = self._make_node(calibration_n=5)
        for _ in range(5):
            node.process_record(self._valid_rec())
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            node.save_state(path)
            node2 = AlertNode.load_state(path)
            assert node2.baseline.is_ready
            assert node2.baseline.medians == node.baseline.medians
        finally:
            os.unlink(path)

    def test_cusum_reset_on_normal(self) -> None:
        """When state returns to normal, all CUSUM accumulators reset."""
        node = self._make_node(calibration_n=5)
        for _ in range(5):
            node.process_record(self._valid_rec())
        # Drive CUSUMs up with clean (normal) values to get some accumulation
        for _ in range(3):
            node.process_record(self._valid_rec())
        # State should be normal, CUSUMs should be 0
        for c in node.cusums.values():
            assert c.pos == 0.0
            assert c.neg == 0.0
