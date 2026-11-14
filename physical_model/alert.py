"""Score a synthetic snapshot and request one grounded note from local Qwen."""

import argparse
import json
import math
import re
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from xgboost import DMatrix, XGBClassifier

from prepare_alerts import FEATURES

MODELS = Path("alert_models")
HABITAT = ["cabin_temp_c", "cabin_humidity_pct", "cabin_co2_ppm"]
SYSTEM = (
    "Write a plain-language handoff for a clinician reviewing a synthetic monitoring alert. "
    "Use two short paragraphs. First explain which recorded measurements contributed most to "
    "the model score and what the cabin comparison showed. Treat drivers as model contributions "
    "and habitat targets as simulated values. If targets are null, say cabin changes alone did "
    "not clear the model alert. The attribution label does not establish a cause. "
    "Then recommend practical verification steps tailored to the readings, such as checking "
    "sensor quality, reviewing recent activity or exposure records, and comparing repeat readings "
    "with the astronaut's baseline. Ask for clinician review if the discrepancy persists. "
    "Use only supplied facts and original measurement units. Avoid diagnosis, claims about "
    "what caused a person's readings, severity judgments, treatment, or cabin control instructions. "
    "Return one JSON field named note."
)
NUMBER = re.compile(r"(?:(?<![\d.])[+-])?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?")


def risk(margin, head):
    logit = head["a"] * np.asarray(margin, dtype=float) + head["b"]
    return np.exp(-np.logaddexp(0, -logit))


def habitat_check(score_fn, snapshot, nominal, threshold):
    for fraction in np.linspace(0, 1, 21):
        targets = {field: float(snapshot[field] + fraction * (nominal[field] - snapshot[field]))
                   for field in HABITAT}
        if score_fn({**snapshot, **targets}) < threshold:
            return {"driver": "habitat", "targets": targets}
    return {"driver": "physiological", "targets": None}


def numeric_values(value):
    if isinstance(value, (dict, list)):
        for item in value.values() if isinstance(value, dict) else value:
            yield from numeric_values(item)
    elif type(value) in (int, float):
        yield value


def verify_note(note, payload):
    if not isinstance(note, str) or not note.strip():
        return False
    facts = tuple(numeric_values(payload))
    text = re.sub(r"(?<![a-z0-9])(?:CO2|SpO2)(?![a-z0-9])", "", note, flags=re.IGNORECASE)
    text = text.replace("−", "-")
    return all(any(math.isclose(value, fact, rel_tol=0.01) for fact in facts)
               for value in (float(token.replace(",", "")) for token in NUMBER.findall(text)))


def qwen_note(payload):
    body = {
        "model": "qwen3:4b", "stream": False, "think": False,
        "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 320},
        "format": {"type": "object", "properties": {"note": {"type": "string"}},
                   "required": ["note"], "additionalProperties": False},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": json.dumps(payload)}],
    }
    request = Request("http://127.0.0.1:11434/api/chat", data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=60) as response:
            draft = json.loads(json.load(response)["message"]["content"])
        if isinstance(draft, dict) and set(draft) == {"note"} and verify_note(draft["note"], payload):
            return draft["note"].strip()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    field = next(iter(payload["drivers"]), "pulse_bpm")
    reading = f"{field.replace('_', ' ')} ({payload['measurements'][field]:g})"
    comparison = (
        "The score dropped below the cutoff in the simulated cabin comparison."
        if payload["attribution"]["targets"] else
        "The simulated cabin changes alone did not clear the model alert."
    )
    return (
        f"The model flagged this synthetic snapshot. Review {reading}. {comparison}\n\n"
        "Confirm the reading against the original record and check the sensor and measurement context. "
        "Compare a repeat reading with the astronaut's baseline and ask the clinician to review "
        "any persistent discrepancy."
    )


def classify(snapshot, astronaut):
    if not isinstance(snapshot, dict) or set(snapshot) != set(FEATURES):
        raise ValueError("Provide the nine measurement fields in example_alert.json.")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in snapshot.values()):
        raise ValueError("Snapshot measurements must be finite numbers.")
    backbone = XGBClassifier(n_jobs=1)
    backbone.load_model(MODELS / "backbone.json")
    heads = json.loads((MODELS / "heads.json").read_text())
    head = heads.get(astronaut, heads["global"])

    def score(reading):
        frame = pd.DataFrame([reading], columns=FEATURES)
        return float(risk(backbone.predict(frame, output_margin=True)[0], head))

    value, threshold = score(snapshot), head["threshold"]
    result = {"alert": value >= threshold, "risk": value, "threshold": threshold}
    if result["alert"]:
        frame = pd.DataFrame([snapshot], columns=FEATURES)
        contributions = backbone.get_booster().predict(DMatrix(frame), pred_contribs=True)[0, :-1]
        top = sorted(zip(FEATURES, contributions), key=lambda pair: pair[1], reverse=True)[:3]
        facts = {"measurements": snapshot, "risk": value, "threshold": threshold,
                 "drivers": {field: float(effect) for field, effect in top if effect > 0},
                 "attribution": habitat_check(score, snapshot, head["nominal"], threshold)}
        result.update(facts, note=qwen_note(facts))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--astronaut", required=True)
    args = parser.parse_args()
    print(json.dumps(classify(json.loads(args.snapshot.read_text()), args.astronaut), indent=2))
