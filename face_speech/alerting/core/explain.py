"""Explainability and human-readable reason string generation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


FEATURE_HUMAN_NAMES: Dict[str, str] = {
    "f0_mean": "Pitch (F0)",
    "f0_std": "Pitch variability",
    "jitter": "Voice jitter",
    "shimmer": "Voice shimmer",
    "hnr": "Harmonics-to-noise ratio",
    "loudness_mean": "Speech loudness",
    "loudness_std": "Loudness variability",
    "speech_rate_syll_per_s": "Speech rate",
    "articulation_rate_syll_per_s": "Articulation rate",
    "pause_ratio": "Pause ratio",
    "mean_pause_s": "Average pause duration",
    "pause_count_per_min": "Pause frequency",
    "expressiveness": "Facial expressiveness",
    "au_activation_rate": "Facial muscle activation rate",
    "head_pose_std": "Head motion variability",
    "au1_mean": "Inner brow raise (AU1)",
    "au2_mean": "Outer brow raise (AU2)",
    "au4_mean": "Brow furrow (AU4)",
    "au5_mean": "Upper lid raise (AU5)",
    "au6_mean": "Cheek raise (AU6)",
    "au9_mean": "Nose wrinkle (AU9)",
    "au12_mean": "Lip corner pull (AU12)",
    "au15_mean": "Lip corner depress (AU15)",
    "au17_mean": "Chin raise (AU17)",
    "au20_mean": "Lip stretch (AU20)",
    "au25_mean": "Lips part (AU25)",
    "au26_mean": "Jaw drop (AU26)",
}


def build_contributors(
    z_scores: Dict[str, float],
    cusum_tracker: Dict[str, float],
    flagged_counters: Dict[str, int],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Rank top evidence features by combined |z| + cusum contribution.

    Contract:
    [ { "feature": "...", "z": <float>, "direction": "up"|"down", "cusum": <float>, "windows_flagged": <int> } ]
    """
    items = []
    for feat, z in z_scores.items():
        c_val = cusum_tracker.get(feat, 0.0)
        flag_cnt = flagged_counters.get(feat, 0)
        # Score priority: absolute z plus accumulated CUSUM
        priority = abs(z) + (c_val / 2.0)
        items.append({
            "feature": feat,
            "z": round(float(z), 2),
            "direction": "up" if z >= 0 else "down",
            "cusum": round(float(c_val), 2),
            "windows_flagged": int(flag_cnt),
            "_priority": priority,
        })

    # Sort descending by priority
    items.sort(key=lambda x: x["_priority"], reverse=True)
    # Remove internal sorting key
    for it in items:
        it.pop("_priority", None)

    return items[:top_k]


def build_reason_string(
    state: str,
    top_contributors: List[Dict[str, Any]],
    current_values: Dict[str, float],
    baseline_medians: Dict[str, float],
    drift_percentile: Optional[float] = None,
    drift_flagged: bool = False,
) -> str:
    """Generate a neutral, plain-language explanation of state.

    Rules:
    - Report percent change vs baseline median.
    - Never use clinical/emotional diagnoses.
    - Use neutral, objective phrasing.
    """
    if state == "invalid":
        return "Window invalid due to sensor quality or insufficient speech duration."
    if state == "calibrating":
        return "Establishing personal baseline from initial valid windows."
    if state == "normal":
        if drift_percentile is not None and drift_percentile > 75.0:
            return f"Metrics within normal baseline range; slight pattern drift at {drift_percentile:.0f}th percentile."
        return "All physiological and behavioral indicators are consistent with baseline."

    # For watch or alert
    parts = []
    # Include up to top 2 dominant features with % change
    for item in top_contributors[:2]:
        feat = item["feature"]
        human_name = FEATURE_HUMAN_NAMES.get(feat, feat)
        cur = current_values.get(feat)
        med = baseline_medians.get(feat)
        if cur is not None and med is not None and abs(med) > 1e-5:
            pct_change = ((cur - med) / abs(med)) * 100.0
            direction_word = "above" if pct_change > 0 else "below"
            parts.append(
                f"{human_name} {abs(pct_change):.0f}% {direction_word} baseline"
            )
        else:
            parts.append(f"{human_name} shifted from baseline (|z|={abs(item['z']):.1f})")

    phrase = " and ".join(parts) if parts else "Multiple features shifted from baseline"

    # Add persistence context if available
    max_flagged = max((it["windows_flagged"] for it in top_contributors), default=1)
    if max_flagged >= 2:
        phrase += f" across {max_flagged} consecutive windows"

    # Add drift note if flagged
    if drift_flagged and drift_percentile is not None:
        phrase += f"; overall vector pattern shifted at the {drift_percentile:.0f}th percentile"
    elif drift_percentile is not None and drift_percentile >= 90.0:
        phrase += f"; overall vector pattern shows {drift_percentile:.0f}th percentile divergence"

    phrase += "."
    return phrase
