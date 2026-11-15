# ASTRA 2.0 roadmap

Implement one approved stage at a time. Keep stage acceptance based on the source partitions and the published cursor. Review each completed stage before starting its successor.

| Stage | Depends on | Work and exit check |
| --- | --- | --- |
| 00 · Specification | Project brief and dataset | Inspect inputs and define architecture, contracts and delivery sequence. Deliver docs only. |
| 01 · Local foundation | 00 review | Create the FastAPI and Vite skeleton, Windows startup guide, shared error contract and health endpoint. Verify system-installed Python 3.12, local SQLite readiness and frontend start. |
| 02 · Historical import | 01 | Build immutable input validation, source adapter and transactional history ingest. Verify 6,252 rows, four crew, matching units and expected missing values. Start at Day 45 and verify future rows are absent from storage and every query surface. |
| 03 · Replay engine | 02 | Add backend-owned replay controls, transactional publication by timestamp, cursor-gated reads, restart and reset. Test simultaneous batches, step/day/play/pause, failed-write rollback, stale revisions, repeated reset and repeatable Day 90 count of 12,491. |
| 04 · Personal analysis | 02 and 03 | Native statistics from replay-gated observations: fixed references, cadence-aware detection, contextual and shared cabin findings, and integrated Mission Overview, Crew Health and Data & Science. Verify all Day 45–90 snapshots and a same-day cutoff. See the [verification report](STAGE_04_VERIFICATION.md). |
| 05 · ASTRA Companion | 04 checkpoint | Add optional local recreational Qwen chat in a separate runtime path. Verify strict isolation from health and replay, real local inference, and Core functionality without Ollama. |
| 06 · Scientific foundation | 04 and 05 | Redesign Data & Science: show metadata and replay visibility, NASA hazards, native methods, an interactive comparison, validation provenance, references, AI attribution and evidence boundaries. Verify in the browser and with regression tests. |
| 07 · Global UI/UX polish | 06 visual approval | Refine the console in a separately approved scope. Preserve the dataset, privacy, replay, analysis, optional chat and prototype behavior. |

Future observation consumers use the same cutoff and privacy rules. Evaluation-only files remain outside runtime. Companion is recreational and has no observation access.
