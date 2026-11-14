# ASTRA 2.0 roadmap

Implement one approved stage at a time. Keep stage acceptance based on the source partitions and the published cursor. Review each completed stage before starting its successor.

| Stage | Depends on | Work and exit check |
| --- | --- | --- |
| 00 · Specification | Project brief and dataset | Inspect inputs and define architecture, contracts and delivery sequence. Deliver docs only. |
| 01 · Local foundation | 00 review | Create the FastAPI and Vite skeleton, Windows startup guide, shared error contract and health endpoint. Verify system-installed Python 3.12, local SQLite readiness and frontend start. |
| 02 · Historical import | 01 | Build immutable input validation, source adapter and transactional history ingest. Verify 6,252 rows, four crew, matching units and expected missing values. Start at Day 45 and verify future rows are absent from storage and every query surface. |
| 03 · Replay engine | 02 | Add backend-owned replay controls, transactional publication by timestamp, cursor-gated reads, restart and reset. Test simultaneous batches, step/day/play/pause, failed-write rollback, stale revisions, repeated reset and repeatable Day 90 count of 12,491. |
| 04 · Personal analysis | 02 and 03 | Calculate fixed personal references and visible trends. Document and test coverage, zero dispersion, context isolation, missing/stale data, privacy and optional cabin association. Include adversarial late rows and verify earlier baselines and findings are unchanged. |
| 05 · Four-screen interface | 03 and 04 | Connect Mission Overview, Crew Health, Mission Replay and Data & Science. Verify navigation, responsive charts, missingness, statuses, offline source descriptions and shared cabin privacy. |
| 06 · Demo verification | 05 | Run backend and frontend regression checks. Manually replay Days 45–90 and reset from a clean install, verify offline startup and document timing, usability and known limits. Prepare a local checkpoint for review. |

Optional data calibration or local AI has its own approval and follows the core demo. If approved, every observation consumer uses the same cutoff and privacy rules. Evaluation-only files remain outside runtime.
