"""Tune the shared XGBoost model and fit personal heads from grouped margins."""

import argparse
import json
from pathlib import Path

import numpy as np
import optuna
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from xgboost import XGBClassifier

from alert import HABITAT, MODELS, risk
from prepare_alerts import FEATURES, TARGET

DEFAULT_PARAMS = {"n_estimators": 200, "max_depth": 3, "learning_rate": 0.1,
                  "min_child_weight": 1, "reg_lambda": 1.0}
FALSE_ALERT_RATE = 1 / 30


def grouped_margins(readings, labels, folds, params):
    backbone = XGBClassifier(random_state=42, n_jobs=2, **params)
    margins = np.empty(len(labels))
    for train, held_out in folds:
        backbone.fit(readings.iloc[train], labels[train])
        margins[held_out] = backbone.predict(readings.iloc[held_out], output_margin=True)
    return backbone, margins


def tune(readings, labels, folds, trials):
    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 75, 325, step=25),
            "max_depth": trial.suggest_int("max_depth", 2, 6),
            "learning_rate": trial.suggest_float("learning_rate", 0.025, 0.2, log=True),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 16),
            "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 20.0, log=True),
        }
        _, margins = grouped_margins(readings, labels, folds, params)
        return float(np.mean([
            roc_auc_score(labels[held_out], margins[held_out], max_fpr=FALSE_ALERT_RATE)
            for _, held_out in folds
        ]))

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.enqueue_trial(DEFAULT_PARAMS)
    study.optimize(objective, n_trials=trials)
    print(f"Grouped partial ROC AUC: fixed {study.trials[0].value:.4f}, selected {study.best_value:.4f}")
    print(f"Selected parameters: {json.dumps(study.best_params)}")
    return study.best_params


def fit_head(margins, labels, readings, global_head=None):
    fit = LogisticRegression().fit(margins[:, None], labels)
    a, b = fit.coef_.item(), fit.intercept_.item()
    if global_head is not None:
        weight = len(labels) / (len(labels) + 15)
        a = weight * a + (1 - weight) * global_head["a"]
        b = weight * b + (1 - weight) * global_head["b"]
    normal = labels == 0
    head = {"a": a, "b": b, "nominal": readings.loc[normal, HABITAT].median().to_dict()}
    head["threshold"] = float(np.quantile(risk(margins[normal], head), 1 - FALSE_ALERT_RATE))
    return head


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=20, help="Optuna trials, including the fixed baseline")
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be at least 1")

    data = Path("prepared_alerts")
    readings = pd.read_csv(data / "X.csv")
    labels = pd.read_csv(data / "y.csv")[TARGET].to_numpy()
    profiles = pd.read_csv(data / "index.csv")["profile"].to_numpy()
    if list(readings) != FEATURES or len(readings) != len(labels) or len(labels) != len(profiles):
        raise ValueError("Regenerate the matching feature, label, and profile CSVs.")
    folds = list(StratifiedGroupKFold(3).split(readings, labels, profiles))
    params = tune(readings, labels, folds, args.trials)
    backbone, margins = grouped_margins(readings, labels, folds, params)

    heads = {"global": fit_head(margins, labels, readings)}
    for profile in sorted(set(profiles)):
        own = profiles == profile
        truth = labels[own]
        head = fit_head(margins[own], truth, readings.loc[own], heads["global"])
        heads[profile] = head
        alerts = risk(margins[own], head) >= head["threshold"]
        print(f"{profile} false-alert rate {alerts[truth == 0].mean():.2%}, recall {alerts[truth == 1].mean():.2%}")

    backbone.fit(readings, labels)
    MODELS.mkdir(exist_ok=True)
    backbone.save_model(MODELS / "backbone.json")
    (MODELS / "heads.json").write_text(json.dumps(heads, indent=2) + "\n")
