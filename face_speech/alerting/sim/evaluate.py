"""Scenario evaluation runner reporting detection delay, false alarms, and alert flapping."""

from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional

from alerting.adapters.facial import get_facial_config
from alerting.adapters.speech import get_speech_config
from alerting.core.node import AlertNode
from alerting.sim.generate import generate_scenario_stream


def evaluate_stream(
    modality: str,
    scenario: str,
    n_baseline: int = 40,
    n_test: int = 60,
    seed: int = 42,
) -> Dict[str, Any]:
    """Run alert node on a simulated scenario stream and compute evaluation metrics."""
    config = get_facial_config() if modality == "facial" else get_speech_config()
    config.calibration_n = n_baseline

    node = AlertNode(config=config, subject_id="sim_astronaut")
    records = generate_scenario_stream(
        modality=modality,
        scenario=scenario,
        n_baseline=n_baseline,
        n_test=n_test,
        seed=seed,
    )

    states: List[str] = []
    watch_window_idx: Optional[int] = None
    alert_window_idx: Optional[int] = None
    flapping_count = 0
    prev_state: Optional[str] = None

    for idx, rec in enumerate(records):
        alert_rec = node.process_record(rec)
        cur_state = alert_rec["state"]
        states.append(cur_state)

        # Only evaluate scenario test window detections (after calibration)
        if idx >= n_baseline:
            test_rel_idx = idx - n_baseline
            if cur_state == "watch" and watch_window_idx is None:
                watch_window_idx = test_rel_idx
            if cur_state == "alert" and alert_window_idx is None:
                alert_window_idx = test_rel_idx

            # Alert flapping: rapid oscillation between alert and watch/normal
            if prev_state is not None:
                if (prev_state == "alert" and cur_state != "alert") or (
                    prev_state != "alert" and cur_state == "alert"
                ):
                    flapping_count += 1
            prev_state = cur_state

    # Post-calibration states
    test_states = states[n_baseline:]
    alert_count = sum(1 for s in test_states if s == "alert")
    watch_count = sum(1 for s in test_states if s == "watch")
    false_alert_rate_per_100 = (alert_count / float(n_test)) * 100.0

    return {
        "modality": modality,
        "scenario": scenario,
        "n_test": n_test,
        "watch_delay": watch_window_idx if watch_window_idx is not None else -1,
        "alert_delay": alert_window_idx if alert_window_idx is not None else -1,
        "alert_count": alert_count,
        "watch_count": watch_count,
        "false_alert_rate": round(false_alert_rate_per_100, 1),
        "flapping_count": flapping_count,
    }


def main() -> None:
    """Run all standard evaluation scenarios across facial and speech modalities."""
    scenarios = ["fatigue_ramp", "stress_spike", "noise_only", "sensor_dropout", "null"]
    modalities = ["speech", "facial"]

    print("=" * 85)
    print("           PER-MODALITY ALERTING ENGINE SCENARIO EVALUATION REPORT           ")
    print("=" * 85)
    header = (
        f"{'Modality':<9} | {'Scenario':<15} | {'Watch Delay':<11} | {'Alert Delay':<11} | "
        f"{'Alert Count':<11} | {'False Alerts/100':<16} | {'Flapping':<8}"
    )
    print(header)
    print("-" * 85)

    all_passed = True

    for mod in modalities:
        for scen in scenarios:
            res = evaluate_stream(modality=mod, scenario=scen, n_baseline=20 if mod == "speech" else 40, n_test=60)
            w_del = f"+{res['watch_delay']} w" if res['watch_delay'] >= 0 else "None"
            a_del = f"+{res['alert_delay']} w" if res['alert_delay'] >= 0 else "None"
            row = (
                f"{res['modality']:<9} | {res['scenario']:<15} | {w_del:<11} | {a_del:<11} | "
                f"{res['alert_count']:<11} | {res['false_alert_rate']:<16} | {res['flapping_count']:<8}"
            )
            print(row)

            # Verification rules:
            # 1. fatigue_ramp and stress_spike MUST reach alert
            if scen in ("fatigue_ramp", "stress_spike"):
                if res["alert_count"] == 0:
                    all_passed = False
                    print(f"  [FAIL] {mod} {scen} expected to reach alert, but got 0 alerts.")
            # 2. noise_only, sensor_dropout, null MUST NOT alert
            if scen in ("noise_only", "sensor_dropout", "null"):
                if res["alert_count"] > 0:
                    all_passed = False
                    print(f"  [FAIL] {mod} {scen} produced {res['alert_count']} false alerts.")

    print("-" * 85)
    if all_passed:
        print("ALL EVALUATION SCENARIOS PASSED: Anomaly sensitivity and noise immunity verified.")
    else:
        print("SOME SCENARIOS FAILED.")
    print("=" * 85)


if __name__ == "__main__":
    main()
