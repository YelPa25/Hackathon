# ASTRA 2.0 release verification

The rehearsal used an independent local Git clone on Windows with CPython 3.12.10, uv 0.12.10, Node.js 26.13.1 and npm 11.20.0. It created its own virtual environment, node_modules and SQLite database. It reused the workstation's installed system runtimes and available package caches. The application ran on separate loopback ports while the existing instance remained available.

| Check | Result |
| --- | --- |
| Environment and Python lock | uv sync --locked installed the locked packages. uv lock --check --offline passed. |
| Frontend lock and checks | npm ci created a new installation. ESLint, TypeScript and Vite production build passed. |
| Backend suite | 73 passed, including native analysis, chronological replay, science comparison, and Companion contract and failure-path tests. |
| Research suite | 49 passed using the separately installed Windows research environment. |
| Core startup and browser | SQLite initialized from the tracked source files. Mission Overview displayed four crew. Crew Health displayed a real baseline and plotted historical observations. |
| Replay | A new database started at Day 45 with 6,252 observations. Next Day reached Day 46 and 6,393 observations. Reset restored Day 45. |
| Science and styling | The science slider updated using the real personal references. The five hazards and AI attribution were present. The Earth backdrop loaded from the local application. |
| Research browser | Both bundled synthetic sample charts ran. The isolated browser origin is not authorized by the live capture service; no devices were activated. |
| Companion browser | The installed Ollama 0.40.16 runtime detected the exact qwen3:4b-instruct-2507-q4_K_M model and answered a real astronomy prompt. Model setup was not repeated. |

Source integrity was checked against the original SHA-256 list. All 16 source entries matched in the development copy. The repository contains eight of those checked files, including both original replay partitions; the checksum list also documents intentionally excluded artifacts from the original bundle.

Core uses local services at runtime. The first install can require network access. Test cases cover unavailable optional services, and the clone ran Core independently of the research broker. The LibreFace 0.2.0 upstream weight download matched the existing AU worker hash. There was no new physical camera or microphone run and no clinical validation. Stage 04's all-day synthetic evaluation remains in the [methodology verification report](STAGE_04_VERIFICATION.md).

The GitHub publication and anonymous clone checks are pending. A local clone is the current reproducibility evidence.
