# ASTRA 2.0 contributor instructions

- Work in ASTRA-Hackathon. Read the Stage status, roadmap and relevant contracts before edits. Implement the requested stage and preserve teammates' work.
- Keep replay and observation reads behind the FastAPI backend. The published cursor is an inclusive cutoff for every observation consumer. Future CSVs are private inputs to replay. Evaluation labels, generator parameters and scenario notes stay outside runtime analysis and UI.
- Preserve source data and stable IDs. Keep synthetic provenance, UTC timestamps, observation contexts, units and missingness. Use recorded rows for replay.
- Keep the app offline after installation and non-clinical. Use the four specified screens and the agreed stack. See [architecture](docs/ARCHITECTURE.md) and [contracts](docs/CONTRACTS.md).
- On Windows use installed Python 3.12 with an explicit interpreter path when needed. Keep Windows security protections enabled.
- Run focused checks and record actual results and gaps in [status](docs/STATUS.md). Stop at the requested stage and await review. Commit, push or change remotes only with explicit approval.
