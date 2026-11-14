"""Physical model evaluation and operational insight generator.

Extracts published astronaut readings and cabin telemetry at the current replay
cursor, evaluates the XGBoost backbone and personal calibration heads, and
determines alert attribution (habitat vs physiological) and cross-crew findings.
"""

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

MODELS_DIR = Path(__file__).resolve().parents[3] / "physical_model" / "alert_models"
HEADS_MAP = {
    "AST-001": "person_1",
    "AST-002": "person_2",
    "AST-003": "person_3",
    "AST-004": "global",
}
HABITAT_KEYS = ["cabin_temp_c", "cabin_humidity_pct", "cabin_co2_ppm"]


class PhysicalEvaluator:
    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = models_dir
        self.loaded = False
        self.feature_names: list[str] = []
        self.base_score: float = 0.15
        self.init_margin: float = 0.0
        self.trees: list[dict[str, Any]] = []
        self.heads: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        backbone_path = self.models_dir / "backbone.json"
        heads_path = self.models_dir / "heads.json"
        if not backbone_path.exists() or not heads_path.exists():
            return
        try:
            with open(backbone_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.feature_names = d["learner"]["feature_names"]
            base_score_str = d["learner"]["learner_model_param"]["base_score"].strip("[]")
            self.base_score = float(base_score_str)
            self.init_margin = math.log(self.base_score / (1.0 - self.base_score))
            self.trees = d["learner"]["gradient_booster"]["model"]["trees"]

            with open(heads_path, "r", encoding="utf-8") as f:
                self.heads = json.load(f)
            self.loaded = True
        except (OSError, ValueError, KeyError):
            self.loaded = False

    def predict_margin(self, features: list[float]) -> float:
        margin = self.init_margin
        for tree in self.trees:
            left, right = tree["left_children"], tree["right_children"]
            split_idx, split_cond = tree["split_indices"], tree["split_conditions"]
            base_weights = tree["base_weights"]
            node = 0
            while left[node] != -1:
                feat_val = features[split_idx[node]]
                if feat_val < split_cond[node]:
                    node = left[node]
                else:
                    node = right[node]
            margin += base_weights[node]
        return margin

    def score_snapshot(self, snapshot: dict[str, float], head: dict[str, Any]) -> float:
        features = [snapshot.get(name, 0.0) for name in self.feature_names]
        margin = self.predict_margin(features)
        logit = head["a"] * margin + head["b"]
        # Numerically stable sigmoid
        if logit >= 0:
            return 1.0 / (1.0 + math.exp(-logit))
        else:
            exp_logit = math.exp(logit)
            return exp_logit / (1.0 + exp_logit)

    def habitat_check(self, snapshot: dict[str, float], head: dict[str, Any], threshold: float) -> dict[str, Any]:
        nominal = head.get("nominal", {"cabin_temp_c": 22.66, "cabin_humidity_pct": 43.7, "cabin_co2_ppm": 3312.0})
        # Test 21 stepped points toward nominal
        for step in range(21):
            fraction = step / 20.0
            targets = {
                key: float(snapshot[key] + fraction * (nominal.get(key, snapshot[key]) - snapshot[key]))
                for key in HABITAT_KEYS if key in snapshot
            }
            test_snap = {**snapshot, **targets}
            if self.score_snapshot(test_snap, head) < threshold:
                return {"driver": "habitat", "targets": targets}
        return {"driver": "physiological", "targets": None}


_evaluator: PhysicalEvaluator | None = None


def get_evaluator() -> PhysicalEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = PhysicalEvaluator()
    return _evaluator


def evaluate_mission_insights(
    connection: sqlite3.Connection,
    replay: Any,
    crew_summaries: list[dict],
    cabin_readings: list[Any],
) -> list[str]:
    """Generate operational insights combining the physical model and cross-crew observations."""
    insights: list[str] = []
    evaluator = get_evaluator()

    # Extract current cabin telemetry
    cabin_by_metric = {r.metric: r.value for r in cabin_readings if r.value is not None}
    cabin_temp = cabin_by_metric.get("cabin_temperature", 22.35)
    cabin_rh = cabin_by_metric.get("cabin_relative_humidity", 45.5)
    cabin_co2_ppm = cabin_by_metric.get("cabin_co2_concentration", 1570.0)
    cabin_co2_mmhg = cabin_by_metric.get("cabin_co2_partial_pressure", cabin_co2_ppm * 760.0 / 1e6)

    active_headaches = 0
    alert_count = 0

    for crew in crew_summaries:
        crew_id = crew["crew_id"]
        display_name = crew["display_name"]
        role = crew["role"]

        # Fetch latest valid vitals for this crew member
        rows = connection.execute(
            """SELECT metric, value FROM observations
               WHERE mission_id = ? AND crew_id = ? AND quality = 'VALID' AND timestamp_utc <= ?
               GROUP BY metric HAVING timestamp_utc = MAX(timestamp_utc)""",
            (replay.dataset_id, crew_id, replay.cursor_utc),
        ).fetchall()
        crew_metrics = {r["metric"]: float(r["value"]) for r in rows if r["value"] is not None}

        if crew_metrics.get("headache", 0.0) > 0:
            active_headaches += 1

        if not evaluator.loaded:
            continue

        pulse = crew_metrics.get("resting_heart_rate", 65.0)
        sys = crew_metrics.get("systolic_bp", 118.0)
        dia = crew_metrics.get("diastolic_bp", 76.0)
        resp = 14.0 + (pulse - 65.0) * 0.08
        body_temp = crew_metrics.get("body_temperature", 36.6)

        snapshot = {
            "pulse_bpm": pulse,
            "systolic_mmhg": sys,
            "diastolic_mmhg": dia,
            "respiratory_rate_rpm": resp,
            "body_temp_c": body_temp,
            "cabin_temp_c": cabin_temp,
            "cabin_humidity_pct": cabin_rh,
            "cabin_co2_ppm": cabin_co2_ppm,
            "prior_day_dose_mgy": 0.202,
        }

        head_key = HEADS_MAP.get(crew_id, "global")
        head = evaluator.heads.get(head_key, evaluator.heads.get("global", {"a": 1.0, "b": 0.0, "threshold": 0.35}))
        threshold = head.get("threshold", 0.35)

        risk = evaluator.score_snapshot(snapshot, head)
        if risk >= threshold:
            alert_count += 1
            attrib = evaluator.habitat_check(snapshot, head, threshold)
            if attrib["driver"] == "habitat":
                insights.append(
                    f"ALERT · {display_name} ({role}): Risk {risk * 100:.1f}% exceeds threshold {threshold * 100:.1f}%. Driver: Cabin habitat (CO₂ {cabin_co2_ppm:.0f} ppm). Cabin normalization clears alert."
                )
            else:
                insights.append(
                    f"ALERT · {display_name} ({role}): Risk {risk * 100:.1f}% exceeds threshold {threshold * 100:.1f}%. Driver: Physiological cardiovascular/thermal shift (Pulse {pulse:.0f} bpm, BP {sys:.0f}/{dia:.0f} mmHg)."
                )
        else:
            insights.append(
                f"NOMINAL · {display_name} ({role}): Predicted Risk {risk * 100:.2f}% (Safety Threshold: {threshold * 100:.1f}%). Vitals: HR {pulse:.0f} bpm, BP {sys:.0f}/{dia:.0f} mmHg, Temp {body_temp:.2f}°C."
            )

    # Cross-crew shared cabin finding (CONTRACTS.md Stage 04 rule)
    if active_headaches >= 2 and cabin_co2_mmhg > 2.5:
        insights.append(
            f"SHARED CABIN ADVISORY: Concurrent headache self-reports from {active_headaches} astronauts with elevated cabin CO₂ ({cabin_co2_mmhg:.2f} mmHg)."
        )

    return insights
