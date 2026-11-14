import sqlite3
from contextlib import closing
from pathlib import Path


def probe_database(path: Path, *, initialize: bool = False) -> None:
    if initialize:
        path.parent.mkdir(parents=True, exist_ok=True)
    mode = "rwc" if initialize else "rw"
    with closing(sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True, timeout=1.0)) as connection:
        # Reading the schema also verifies the file is a readable SQLite database.
        connection.execute("PRAGMA schema_version").fetchone()
        if initialize and path.stat().st_size == 0:
            connection.execute("PRAGMA user_version = 0")
        if connection.execute("SELECT 1").fetchone() != (1,):
            raise sqlite3.DatabaseError("SQLite readiness query failed")
