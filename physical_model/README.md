# Astronaut monitoring prototype

Optuna tunes XGBoost on three profile-grouped folds for partial ROC AUC near the 1-in-30 false-alert target, then the personal head sets the alert and flagged readings get a cabin comparison and a local Qwen note or template.

```bash
uv sync
uv run python prepare_alerts.py data.zip
uv run python train.py --trials 20
uv run python alert.py example_alert.json --astronaut person_1
uv run python test_ui/server.py
```

Open the test UI at [127.0.0.1:8765](http://127.0.0.1:8765). It uses the bundled example and supports editing every reading and choosing a saved profile. The template works with Ollama offline.

Labels are synthetic and derived from three participants. Fold scores guide tuning and calibration, with no independent test set.
