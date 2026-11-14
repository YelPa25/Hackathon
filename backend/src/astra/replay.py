"""The only runtime reader of the private replay partition."""

import asyncio
import csv
import json
import logging
import sqlite3
from bisect import bisect_right
from contextlib import closing, suppress
from datetime import timedelta
from pathlib import Path
from time import monotonic

from starlette.concurrency import run_in_threadpool

from astra.db import connect_database
from astra.importer import (
    OBSERVATION_FIELDS, DatasetError, csv_rows, insert_observations, observation_records, verified_inputs,
)
from astra.models import DatasetMetadata, Metric, ReplayCommand, ReplayView, parse_utc
from astra.reads import ApiError, replay_state

logger = logging.getLogger("astra")
FUTURE = "replay_future_HIDDEN_DAY46_to_DAY90.csv"
FUTURE_COUNT = 6239


def replay_view(connection: sqlite3.Connection, playback_error: str | None) -> ReplayView:
    state = replay_state(connection)
    row = connection.execute(
        "SELECT metadata_json FROM datasets WHERE dataset_id = ?", (state.dataset_id,)
    ).fetchone()
    metadata = DatasetMetadata.model_validate_json(row["metadata_json"])
    activity = None
    if state.mission_day > metadata.historical_days:
        totals = connection.execute(
            """SELECT COUNT(*) AS observation_count, COUNT(o.crew_id) AS crew_count,
                      COUNT(*) - COUNT(o.crew_id) AS cabin_count,
                      MIN(o.timestamp_utc) AS first_utc, MAX(o.timestamp_utc) AS last_utc
               FROM observations AS o JOIN replay_observations AS r USING (observation_id)
               WHERE o.mission_id = ? AND o.mission_day = ? AND o.timestamp_utc <= ?""",
            (state.dataset_id, state.mission_day, state.cursor_utc),
        ).fetchone()
        activity = {"mission_day": state.mission_day, **dict(totals)}
    return ReplayView(
        **state.model_dump(), historical_days=metadata.historical_days, mission_days=metadata.mission_days,
        latest_activity=activity, playback_error=playback_error,
    )


class ReplayEngine:
    def __init__(self, path: Path, source: Path):
        self.path = path
        self.source = source
        self.error: str | None = None
        self._deadline: float | None = None
        self._lock = asyncio.Lock()
        self._partition: tuple[str, list[str], list[dict[str, str]]] | None = None

    def pause_after_restart(self) -> None:
        with closing(connect_database(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE replay_state SET status = 'PAUSED', revision = revision + 1 WHERE status = 'RUNNING'"
            )

    def _private_partition(self, metadata: DatasetMetadata):
        if self._partition is None:
            try:
                files, hashes = verified_inputs(self.source, (FUTURE,))
                rows = list(csv_rows(files[FUTURE], (*OBSERVATION_FIELDS, "note"), FUTURE))
                times = [row["timestamp_utc"] for row in rows]
                start = parse_utc(metadata.mission_start_utc).date()
                for row in rows:
                    day = (parse_utc(row["timestamp_utc"]).date() - start).days + 1
                    if not metadata.historical_days < day <= metadata.mission_days or row["mission_day"] != str(day):
                        raise DatasetError("Unexpected replay partition timestamp or mission day")
                if (len(rows) != FUTURE_COUNT or len({row["observation_id"] for row in rows}) != len(rows)
                        or sorted(times) != times):
                    raise DatasetError("Unexpected replay partition count, IDs or ordering")
            except (OSError, ValueError, csv.Error) as exc:
                logger.warning("Replay source failed validation: %s", type(exc).__name__)
                raise ApiError(503, "replay_source_unavailable", "The private replay source could not be verified.") from exc
            self._partition = (hashes[FUTURE], times, rows)
        return self._partition

    def _change(self, command: str, revision: int | None = None, speed: float | None = None) -> ReplayView:
        with closing(connect_database(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            state = replay_state(connection)
            if revision is not None and revision != state.revision:
                raise ApiError(409, "stale_revision", "Replay changed. Review the latest state and try again.")
            if command == "TICK" and state.status != "RUNNING":
                return replay_view(connection, self.error)
            if (command == "PAUSE" and state.status != "RUNNING"
                    or command in {"PLAY", "NEXT_DAY", "NEXT_EVENT"} and state.status != "PAUSED"):
                raise ApiError(409, "invalid_transition", "That control is unavailable in the current replay state.")

            installed = connection.execute(
                "SELECT metadata_json, historical_count FROM datasets WHERE dataset_id = ?", (state.dataset_id,)
            ).fetchone()
            metadata = DatasetMetadata.model_validate_json(installed["metadata_json"])
            start = parse_utc(metadata.mission_start_utc)
            cursor = parse_utc(state.cursor_utc)
            end = start + timedelta(days=metadata.mission_days, seconds=-1)
            status, count = state.status, state.visible_count

            if command == "RESET":
                connection.execute(
                    """DELETE FROM observations WHERE mission_id = ?
                       AND observation_id IN (SELECT observation_id FROM replay_observations)""", (state.dataset_id,)
                )
                cursor = start + timedelta(days=metadata.historical_days, seconds=-1)
                status, count = "PAUSED", installed["historical_count"]
            elif command == "PAUSE":
                status = "PAUSED"
            elif command in {"PLAY", "NEXT_DAY", "NEXT_EVENT", "TICK"}:
                digest, times, rows = self._private_partition(metadata)
                pinned = connection.execute("SELECT source_sha256 FROM replay_state").fetchone()[0]
                if pinned is not None and pinned != digest:
                    raise ApiError(503, "replay_source_changed", "The private replay source differs from the installed version.")
                if pinned is None:
                    connection.execute("UPDATE replay_state SET source_sha256 = ?", (digest,))
                if command == "PLAY":
                    status = "RUNNING"
                else:
                    first = bisect_right(times, state.cursor_utc)
                    if command == "NEXT_EVENT":
                        cursor = parse_utc(times[first]) if first < len(times) else end
                    elif command == "NEXT_DAY":
                        cursor = min(end, cursor.replace(hour=23, minute=59, second=59) + timedelta(days=1))
                    else:
                        cursor = min(end, cursor + timedelta(days=1))
                    last = bisect_right(times, cursor.strftime("%Y-%m-%dT%H:%M:%SZ"))
                    batch = sorted(rows[first:last], key=lambda row: (row["timestamp_utc"], row["observation_id"]))
                    metrics = {
                        row["metric"]: Metric.model_validate({**dict(row), "is_nasa_measured": False})
                        for row in connection.execute("SELECT * FROM metrics")
                    }
                    try:
                        records = observation_records(batch, metadata, metrics, metadata.historical_days + 1, metadata.mission_days)
                    except ValueError as exc:
                        raise ApiError(503, "replay_source_invalid", "The next replay batch failed validation.") from exc
                    try:
                        insert_observations(connection, records)
                        connection.executemany(
                            "INSERT INTO replay_observations VALUES (?)", [(row["observation_id"],) for row in batch]
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ApiError(409, "observation_conflict", "Replay found an observation conflict. No new readings were published.") from exc
                    count += len(records)
                    if cursor == end:
                        status = "COMPLETE"

            connection.execute(
                """UPDATE replay_state SET revision = revision + 1, status = ?, cursor_utc = ?,
                          mission_day = ?, visible_count = ?, speed = ? WHERE singleton = 1""",
                (status, cursor.strftime("%Y-%m-%dT%H:%M:%SZ"), (cursor.date() - start.date()).days + 1,
                 count, speed if command == "SET_SPEED" else state.speed),
            )
            return replay_view(connection, None)

    async def command(self, request: ReplayCommand) -> ReplayView:
        async with self._lock:
            result = await run_in_threadpool(self._change, request.command, request.expected_revision, request.speed)
            self.error = None
            self._deadline = monotonic() + result.speed if result.status == "RUNNING" else None
            return result

    async def run(self) -> None:
        while True:
            await asyncio.sleep(0.05)
            async with self._lock:
                if self._deadline is None or monotonic() < self._deadline:
                    continue
                try:
                    result = await run_in_threadpool(self._change, "TICK")
                except (ApiError, OSError, ValueError, sqlite3.Error) as exc:
                    logger.warning("Playback paused after publication failure: %s", type(exc).__name__)
                    self.error = exc.message if isinstance(exc, ApiError) else "Playback stopped because mission storage is unavailable."
                    self._deadline = None
                    with suppress(ApiError, sqlite3.Error):
                        await run_in_threadpool(self._change, "PAUSE")
                else:
                    self._deadline = self._deadline + result.speed if result.status == "RUNNING" else None
