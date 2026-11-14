import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 2

SCHEMA = (
    """CREATE TABLE datasets (
        dataset_id TEXT PRIMARY KEY,
        metadata_json TEXT NOT NULL,
        input_hashes_json TEXT NOT NULL,
        imported_at_utc TEXT NOT NULL,
        historical_count INTEGER NOT NULL CHECK (historical_count > 0),
        historical_missing_count INTEGER NOT NULL CHECK (historical_missing_count >= 0)
    )""",
    """CREATE TABLE crew (
        crew_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL,
        age_years INTEGER NOT NULL CHECK (age_years > 0),
        activity_pref TEXT NOT NULL
    )""",
    """CREATE TABLE metrics (
        metric TEXT PRIMARY KEY,
        unit TEXT NOT NULL,
        description TEXT NOT NULL,
        scope TEXT NOT NULL CHECK (scope IN ('person', 'cabin')),
        provenance TEXT NOT NULL CHECK (provenance = 'SYNTHETIC'),
        measurement_cadence TEXT NOT NULL,
        is_nasa_measured INTEGER NOT NULL CHECK (is_nasa_measured = 0)
    )""",
    """CREATE TABLE replay_state (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        dataset_id TEXT NOT NULL REFERENCES datasets (dataset_id),
        revision INTEGER NOT NULL CHECK (revision >= 0),
        status TEXT NOT NULL CHECK (status IN ('PAUSED', 'RUNNING', 'COMPLETE')),
        cursor_utc TEXT NOT NULL,
        mission_day INTEGER NOT NULL CHECK (mission_day BETWEEN 1 AND 90),
        visible_count INTEGER NOT NULL CHECK (visible_count >= 0)
    )""",
    """CREATE TABLE observations (
        observation_id TEXT PRIMARY KEY,
        mission_id TEXT NOT NULL REFERENCES datasets (dataset_id),
        crew_id TEXT REFERENCES crew (crew_id),
        subject_id TEXT NOT NULL,
        scope TEXT NOT NULL CHECK (scope IN ('person', 'cabin')),
        timestamp_utc TEXT NOT NULL,
        mission_day INTEGER NOT NULL CHECK (mission_day BETWEEN 1 AND 90),
        metric TEXT NOT NULL REFERENCES metrics (metric),
        value TEXT,
        unit TEXT NOT NULL,
        activity_context TEXT NOT NULL,
        source TEXT NOT NULL,
        provenance TEXT NOT NULL CHECK (provenance = 'SYNTHETIC'),
        quality TEXT NOT NULL,
        missing_reason TEXT,
        privacy TEXT NOT NULL,
        share_cabin_context INTEGER NOT NULL CHECK (share_cabin_context IN (0, 1)),
        CHECK ((scope = 'person' AND crew_id IS NOT NULL AND subject_id = crew_id)
            OR (scope = 'cabin' AND crew_id IS NULL AND subject_id = 'CABIN-01')),
        CHECK ((quality = 'VALID' AND value IS NOT NULL AND missing_reason IS NULL)
            OR (quality = 'MISSING' AND value IS NULL AND missing_reason IS NOT NULL))
    )""",
    "CREATE INDEX observations_time ON observations (mission_id, timestamp_utc, observation_id)",
    """CREATE INDEX observations_crew_metric_time
        ON observations (mission_id, crew_id, metric, timestamp_utc, observation_id)""",
)

REPLAY_MIGRATION = (
    "ALTER TABLE replay_state ADD COLUMN speed REAL NOT NULL DEFAULT 2 CHECK (speed IN (0.5, 2, 5))",
    "ALTER TABLE replay_state ADD COLUMN source_sha256 TEXT",
    """CREATE TABLE replay_observations (
        observation_id TEXT PRIMARY KEY REFERENCES observations (observation_id) ON DELETE CASCADE
    )""",
)


def connect_database(path: Path, mode: str = "rw") -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def read_snapshot(path: Path) -> Iterator[sqlite3.Connection]:
    with closing(connect_database(path, "ro")) as connection, connection:
        connection.execute("BEGIN")
        yield connection


def initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect_database(path, "rwc")) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version not in (0, 1):
            raise sqlite3.DatabaseError(f"Unsupported ASTRA schema version {version}")
        if version == 0:
            for statement in SCHEMA:
                connection.execute(statement)
        for statement in REPLAY_MIGRATION:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def probe_database(connection: sqlite3.Connection) -> int:
    # Reading the schema verifies the file is actually SQLite.
    connection.execute("PRAGMA schema_version").fetchone()
    if connection.execute("SELECT 1").fetchone()[0] != 1:
        raise sqlite3.DatabaseError("SQLite readiness query failed")
    return connection.execute("PRAGMA user_version").fetchone()[0]
