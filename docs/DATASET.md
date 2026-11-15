# ASTRA synthetic dataset

ASTRA-SYN-90D-01 v1.0.0 is a deterministic simulation of a fictional four-person crew over 90 mission days (1 January to 30 March 2040 UTC). It is research-informed and contains no individual-level astronaut or NHANES records. The 18 metrics include physiology, sleep, activity, subjective check-ins, and four cabin measurements. The complete observation set has 12,491 rows, including 67 explicit missing readings. The first partition has 6,252 rows; the replay partition has 6,239. See the [original manifest](../ASTRA_90day_dataset_v1/dataset_manifest.json) and [validation report](../ASTRA_90day_dataset_v1/validation_report.json).

## Source files and runtime boundary

- Historical [Days 1–45](../ASTRA_90day_dataset_v1/replay_history_DAY01_to_DAY45.csv) initialize SQLite and the personal reference window. Only the chronological replay publisher reads the [Days 46–90 partition](../ASTRA_90day_dataset_v1/replay_future_HIDDEN_DAY46_to_DAY90.csv). The backend’s independent read cutoff prevents unrevealed observations from reaching Core views or analytics.
- The [crew profiles](../ASTRA_90day_dataset_v1/crew_profiles.csv), [metric dictionary](../ASTRA_90day_dataset_v1/metric_dictionary.csv), [manifest](../ASTRA_90day_dataset_v1/dataset_manifest.json), and [scientific sources](../ASTRA_90day_dataset_v1/scientific_sources.csv) are runtime metadata. Cabin CO₂ ppm is derived using the manifest’s assumed pressure. Missing flags and original timestamps are preserved.
- The [generator](../ASTRA_90day_dataset_v1/generate_dataset.py) and [validation report](../ASTRA_90day_dataset_v1/validation_report.json) are review material. They are not loaded by the application. The full archive, duplicate source exports and workbooks, original bundle notes, and evaluation-only truth labels are excluded from this source tree. Synthetic evaluation labels do not contribute to the live system.
- The [source checksum list](../ASTRA_90day_dataset_v1/SHA256SUMS.txt) is unchanged and covers all 16 entries in the original full bundle, including files omitted here. The app verifies each runtime file it reads. Repository integrity checks verify only present files against their recorded hashes.

## Method and provenance

The generator uses NumPy and an explicit seed of 20261114. It simulates personal variability, intermittent collection, missing data and engineered events. To study the generator, copy the script into a new scratch directory before running it. It writes outputs beside itself. Normal ASTRA installation uses the included source records and requires no regeneration.

NASA standard measures informed the observation categories. The sleep distribution was checked against a published aggregate rather than fitted to individual astronauts. NASA CO₂ guidance and CDC/NHANES blood-pressure metadata inform measurement context. The dataset was not fitted to raw human data, and deliberately co-occurring cabin and symptom observations do not establish a causal relationship. The [scientific source catalog](../ASTRA_90day_dataset_v1/scientific_sources.csv) records each use.
