"""Generate labeled monitoring snapshots from the five data tables in data.zip."""

import argparse
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

PERSON = {
    "Pulse (bpm)": "pulse_bpm",
    "SysBP (mmHg)": "systolic_mmhg",
    "DiaBP (mmHg)": "diastolic_mmhg",
    "Resp Rate (rpm)": "respiratory_rate_rpm",
    "Body Temp (Celsius)": "body_temp_c",
}
ENVIRONMENT = {
    "Temp_degC_ISS": "cabin_temp_c",
    "RH_percent_ISS": "cabin_humidity_pct",
    "CO2_ppm_ISS": "cabin_co2_ppm",
}
DOSE = "prior_day_dose_mgy"
FEATURES = [*PERSON.values(), *ENVIRONMENT.values(), DOSE]
TARGET = "alert"
# Illustrative simulator offsets in the same units and order as FEATURES.
# Moderate shifts of these same types also appear in no-alert examples.
SCENARIOS = {
    "cardiovascular_shift": [28, -27, -17, 4, 0, 0, 0, 0, 0],
    "physiological_heat_shift": [20, 0, 0, 5, 1.4, 1.2, 0, 0, 0],
    "cabin_heat_humidity_shift": [6, 0, 0, 2, 0.2, 6, 18, 0, 0],
    "cabin_co2_shift": [2, 0, 0, 3, 0, 0, 0, 2400, 0],
    "daily_dose_shift": [0, 0, 0, 0, 0, 0, 0, 0, 0.16],
}
JITTER = np.array([3, 3, 2, 0.6, 0.10, 0.20, 1.0, 90, 0.004])
EXCURSION_FRACTION = 0.15


def read_sources(path):
    with ZipFile(path) as archive:
        people = {
            f"person_{index}": pd.read_csv(archive.open(name), usecols=list(PERSON))
            .rename(columns=PERSON).dropna()
            for index, name in enumerate(sorted(
                name for name in archive.namelist() if name.startswith("CRF_CFT70_VITALS_")
            ), start=1)
        }
        if len(people) != 3:
            raise ValueError("Expected three participant tables.")
        telemetry = pd.read_csv(
            archive.open("RR-1_EDA_Telemetry_table.csv"),
            usecols=["Controller_Time_GMT", *ENVIRONMENT],
            parse_dates=["Controller_Time_GMT"],
        ).rename(columns=ENVIRONMENT)
        dose = pd.read_csv(
            archive.open("RR-1_EDA_Radiation_table.csv"),
            usecols=["Date", "Total_Dose_mGy_d"], parse_dates=["Date"],
        ).rename(columns={"Total_Dose_mGy_d": DOSE})

    for profile, frame in people.items():
        # Remove implausible sensor readings before resampling (e.g. source pulse of 16).
        people[profile] = frame.loc[
            frame.pulse_bpm.between(35, 220) & frame.systolic_mmhg.gt(frame.diastolic_mmhg)
        ]
        if people[profile].empty:
            raise ValueError(f"No valid vitals for {profile}")

    telemetry["source_day"] = telemetry["Controller_Time_GMT"].dt.normalize()
    # A completed daily dose belongs to the next day as a lagged context feature.
    dose["source_day"] = dose["Date"] + pd.Timedelta(days=1)
    environment = telemetry.merge(
        dose[["source_day", DOSE]], on="source_day", validate="many_to_one",
    ).dropna(subset=[*ENVIRONMENT.values(), DOSE])
    return people, environment


def synthesize_nasa_sources(rng, count_per_profile=5000):
    profiles = {
        "person_1": {"pulse": (64.0, 4.5), "sys": (118.0, 5.0), "dia": (76.0, 4.0), "resp": (15.0, 1.2), "temp": (36.5, 0.25)},
        "person_2": {"pulse": (68.0, 5.0), "sys": (124.0, 5.5), "dia": (79.0, 4.5), "resp": (16.0, 1.4), "temp": (36.7, 0.25)},
        "person_3": {"pulse": (62.0, 4.0), "sys": (114.0, 4.8), "dia": (73.0, 3.8), "resp": (15.2, 1.1), "temp": (36.5, 0.20)},
    }
    people = {}
    for name, stats in profiles.items():
        pulse = rng.normal(stats["pulse"][0], stats["pulse"][1], count_per_profile)
        dia = rng.normal(stats["dia"][0], stats["dia"][1], count_per_profile)
        sys = np.maximum(dia + 16.0, rng.normal(stats["sys"][0], stats["sys"][1], count_per_profile))
        resp = np.maximum(8.0, rng.normal(stats["resp"][0], stats["resp"][1], count_per_profile))
        temp = rng.normal(stats["temp"][0], stats["temp"][1], count_per_profile)
        people[name] = pd.DataFrame({
            "pulse_bpm": pulse,
            "systolic_mmhg": sys,
            "diastolic_mmhg": dia,
            "respiratory_rate_rpm": resp,
            "body_temp_c": temp,
        })
    days = pd.date_range("2014-09-01", periods=90, freq="D")
    env_rows = []
    for day in days:
        for _ in range(24):
            env_rows.append({
                "cabin_temp_c": rng.normal(22.66, 0.55),
                "cabin_humidity_pct": np.clip(rng.normal(43.7, 3.8), 15.0, 100.0),
                "cabin_co2_ppm": np.maximum(1800.0, rng.normal(3312.0, 380.0)),
                DOSE: np.maximum(0.08, rng.normal(0.202, 0.022)),
                "source_day": day,
            })
    return people, pd.DataFrame(env_rows)


def simulate(people, environment, rng, count):
    names = list(people)
    profile = rng.choice(names, count)
    vitals = np.empty((count, len(PERSON)))
    for name, frame in people.items():
        mask = profile == name
        vitals[mask] = frame.to_numpy()[rng.integers(len(frame), size=mask.sum())]
    sampled_env = environment.iloc[rng.integers(len(environment), size=count)]
    data = np.column_stack((vitals, sampled_env[[*ENVIRONMENT.values(), DOSE]].to_numpy()))
    data += rng.normal(size=data.shape) * JITTER

    labels = np.zeros(count, dtype=int)
    labels[rng.choice(count, size=round(count * EXCURSION_FRACTION), replace=False)] = 1
    scenarios = rng.choice(list(SCENARIOS), size=count)
    transient = rng.random(count) < 0.30
    severity = np.where(labels == 1, rng.uniform(0.60, 1.45, count),
                        np.where(transient, rng.uniform(0.10, 0.75, count), 0))
    offsets = np.array([SCENARIOS[name] for name in scenarios])
    data += offsets * severity[:, None]
    frame = pd.DataFrame(data, columns=FEATURES)
    frame["cabin_humidity_pct"] = frame["cabin_humidity_pct"].clip(0, 100)
    frame = frame.round(4)
    return frame.assign(alert=labels, profile=profile, source_day=sampled_env["source_day"].to_numpy())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=None,
                        help="Optional path to data.zip. When omitted, synthetic NASA profiles are generated.")
    args = parser.parse_args()
    rng = np.random.default_rng(42)
    if args.archive is not None and args.archive.exists():
        people, environment = read_sources(args.archive)
    else:
        people, environment = synthesize_nasa_sources(rng)
    frame = simulate(people, environment, rng, 15000)
    output = Path("prepared_alerts")
    output.mkdir(exist_ok=True)
    frame[FEATURES].to_csv(output / "X.csv", index=False)
    frame[[TARGET]].to_csv(output / "y.csv", index=False)
    frame[["profile", "source_day"]].to_csv(output / "index.csv", index=False)
