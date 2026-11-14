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
    parser.add_argument("archive", type=Path)
    people, environment = read_sources(parser.parse_args().archive)
    frame = simulate(people, environment, np.random.default_rng(42), 15000)
    output = Path("prepared_alerts")
    output.mkdir(exist_ok=True)
    frame[FEATURES].to_csv(output / "X.csv", index=False)
    frame[[TARGET]].to_csv(output / "y.csv", index=False)
    frame[["profile", "source_day"]].to_csv(output / "index.csv", index=False)
