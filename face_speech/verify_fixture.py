from pathlib import Path
import os
import sys

# Run from a disposable directory containing only reviewed source and detector dependencies.

root = Path(__file__).resolve().parent
runtime = Path(sys.base_prefix).resolve()
sys.dont_write_bytecode = True
# The reviewed fixture path uses a subset of dependencies and a disposable directory.
def audit(event, args):
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname",
                 "subprocess.Popen", "os.system", "os.startfile", "os.posix_spawn", "os.exec"}:
        raise PermissionError(f"Fixture guard denied {event}")
    if event == "open" and not isinstance(args[0], int):
        path = Path(os.fsdecode(args[0])).resolve()
        writes = args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if not path.is_relative_to(root) and (writes or not path.is_relative_to(runtime)):
            raise PermissionError(f"Fixture guard denied file access: {path}")

sys.addaudithook(audit)
sys.path.insert(0, str(root))
mode = sys.argv[1]
if mode == "tests":
    import pytest
    raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", "-s", "-p", "no:logging", *sys.argv[2:]]))
if mode == "fixture":
    import json
    from alerting.adapters.facial import get_facial_config
    from alerting.adapters.speech import get_speech_config
    from alerting.core.node import AlertNode
    from alerting.sim.generate import generate_scenario_stream
    from alerting.sim.evaluate import evaluate_stream
    result = {"source": "Synthetic feature windows", "upstream": "dc30f16775cefe34777dcbf85d949d545ea1bf62", "modalities": {}}
    for modality, config in (("facial", get_facial_config()), ("speech", get_speech_config())):
        scenarios = {}
        features = ["expressiveness", "au_activation_rate"] if modality == "facial" else ["speech_rate_syll_per_s", "pause_ratio"]
        for scenario in ("fatigue_ramp", "stress_spike", "noise_only", "sensor_dropout", "null"):
            stats = evaluate_stream(modality, scenario, n_baseline=config.calibration_n)
            print(modality, scenario, stats["alert_count"], stats["watch_count"])
            if scenario not in {"fatigue_ramp", "sensor_dropout"}:
                continue
            node = AlertNode(config, subject_id=f"demo-{modality}", adapt=False)
            stream = generate_scenario_stream(modality, scenario, n_baseline=config.calibration_n)
            rows = []
            alerts = root / f"{modality}-{scenario}.jsonl"
            with alerts.open("w", encoding="utf-8") as output:
                for observed in stream:
                    alert = node.process_record(observed)
                    output.write(json.dumps(alert, allow_nan=False) + "\n")
                    rows.append({
                        "t": alert["t"], "state": alert["state"], "quality": alert["quality"],
                        "baseline": alert["baseline"],
                        "score": alert["score"] if alert["state"] in {"normal", "watch", "alert"} else None,
                        "driftPercentile": alert["drift"]["percentile"],
                        "features": {key: round(float(observed["features"][key]), 4) if observed["valid"] else None for key in features},
                        "contributors": [item for item in alert["contributors"] if item["windows_flagged"] > 0][:3],
                    })
            scenarios[scenario] = rows
        result["modalities"][modality] = {"target": config.calibration_n, "scenarios": scenarios}
    (root / "demo.json").write_text(json.dumps(result, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8")
else:
    raise SystemExit("Choose tests or fixture.")
