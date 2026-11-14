"""Read-only mission snapshots. All observation consumers use visible_observations."""

import base64
import binascii
import json
import sqlite3
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field

from astra.models import Context, Observation, ReplayState, Scope, parse_utc


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class ObservationFilters(BaseModel):
    crew_id: str | None = None
    scope: Scope | None = None
    metric: str | None = None
    context: Context | None = None
    from_utc: str | None = None
    to_utc: str | None = None

    def check(self, connection: sqlite3.Connection) -> None:
        if self.scope == "cabin" and self.crew_id is not None:
            raise ApiError(422, "invalid_filters", "Cabin observations do not have a crew ID.")
        if self.crew_id is not None:
            crew_profile(connection, self.crew_id)
        if self.metric is not None:
            metric = connection.execute("SELECT scope FROM metrics WHERE metric = ?", (self.metric,)).fetchone()
            if metric is None:
                raise ApiError(422, "invalid_filters", "Unknown metric.")
            scope = self.scope or ("person" if self.crew_id is not None else None)
            if scope is not None and metric["scope"] != scope:
                raise ApiError(422, "invalid_filters", "The metric does not match the requested scope.")
        try:
            start = parse_utc(self.from_utc) if self.from_utc is not None else None
            end = parse_utc(self.to_utc) if self.to_utc is not None else None
        except ValueError as exc:
            raise ApiError(422, "invalid_filters", "Use whole-second UTC timestamps such as 2040-02-14T23:59:59Z.") from exc
        if start is not None and end is not None and start > end:
            raise ApiError(422, "invalid_filters", "The time range is reversed.")


class HistoryQuery(ObservationFilters):
    limit: int = Field(default=100, ge=1, le=500)
    cursor: str | None = Field(default=None, max_length=2048)


HistoryRequest = Annotated[HistoryQuery, Query()]
LatestRequest = Annotated[ObservationFilters, Query()]


def replay_state(connection: sqlite3.Connection) -> ReplayState:
    row = connection.execute(
        """SELECT r.* FROM replay_state AS r JOIN datasets AS d USING (dataset_id)
           WHERE r.singleton = 1"""
    ).fetchone()
    if row is None:
        raise ApiError(503, "dataset_unavailable", "Historical mission data is not initialized. Check the backend startup log.")
    return ReplayState.model_validate(dict(row))


def crew_profile(connection: sqlite3.Connection, crew_id: str) -> dict:
    row = connection.execute("SELECT * FROM crew WHERE crew_id = ?", (crew_id,)).fetchone()
    if row is None:
        raise ApiError(404, "unknown_crew", "Crew member not found.")
    return dict(row)


def visible_observations(
    replay: ReplayState, filters: ObservationFilters, *, include_private: bool = True,
) -> tuple[str, list]:
    """Build the common observation read, locked to the published mission and cursor."""
    clauses = ["mission_id = ?", "timestamp_utc <= ?"]
    values = [replay.dataset_id, replay.cursor_utc]
    for parameter, column, operator in (
        (filters.crew_id, "crew_id", "="),
        (filters.scope, "scope", "="),
        (filters.metric, "metric", "="),
        (filters.context, "activity_context", "="),
        (filters.from_utc, "timestamp_utc", ">="),
        (filters.to_utc, "timestamp_utc", "<="),
    ):
        if parameter is not None:
            clauses.append(f"{column} {operator} ?")
            values.append(parameter)
    if filters.crew_id is None or not include_private:
        clauses.append("privacy <> 'private_health'")
    return "SELECT * FROM observations WHERE " + " AND ".join(clauses), values


def observation_dto(row: sqlite3.Row) -> Observation:
    return Observation.model_validate(dict(row))


def encode_cursor(replay: ReplayState, filters: dict, last: Observation) -> str:
    payload = [replay.dataset_id, replay.revision, filters, last.timestamp_utc, last.observation_id]
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def decode_cursor(token: str, replay: ReplayState, filters: dict) -> tuple[str, str]:
    try:
        dataset, revision, saved_filters, timestamp, observation_id = json.loads(
            base64.b64decode(token, altchars=b"-_", validate=True)
        )
        if (dataset != replay.dataset_id or type(revision) is not int or saved_filters != filters
                or type(timestamp) is not str or type(observation_id) is not str or not observation_id):
            raise ValueError("Invalid continuation")
        parse_utc(timestamp)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ApiError(422, "invalid_cursor", "Invalid continuation for these filters.") from exc
    if revision != replay.revision:
        raise ApiError(409, "stale_revision", "Mission state changed. Restart paging from the first page.")
    return timestamp, observation_id


def history_page(connection: sqlite3.Connection, replay: ReplayState, query: HistoryQuery) -> dict:
    query.check(connection)
    sql, values = visible_observations(replay, query)
    filters = query.model_dump(exclude={"limit", "cursor"}, exclude_none=True)
    if query.cursor is not None:
        values.extend(decode_cursor(query.cursor, replay, filters))
        sql += " AND (timestamp_utc, observation_id) > (?, ?)"
    rows = connection.execute(
        sql + " ORDER BY timestamp_utc, observation_id LIMIT ?", (*values, query.limit + 1)
    ).fetchall()
    items = [observation_dto(row) for row in rows[:query.limit]]
    next_cursor = encode_cursor(replay, filters, items[-1]) if len(rows) > query.limit else None
    return {"revision": replay.revision, "cursor_utc": replay.cursor_utc, "items": items, "next_cursor": next_cursor}


def latest_observations(
    connection: sqlite3.Connection, replay: ReplayState, filters: ObservationFilters
) -> tuple[list[Observation], list[Observation]]:
    sql, values = visible_observations(replay, filters)
    # Ranking by quality retains the last valid value even when the newest sample is missing.
    rows = connection.execute(f"""
        WITH visible AS ({sql}),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY metric ORDER BY timestamp_utc DESC, observation_id DESC
            ) AS newest,
            ROW_NUMBER() OVER (
                PARTITION BY metric, quality ORDER BY timestamp_utc DESC, observation_id DESC
            ) AS newest_quality
            FROM visible
        )
        SELECT * FROM ranked
        WHERE (quality = 'VALID' AND newest_quality = 1) OR (quality = 'MISSING' AND newest = 1)
        ORDER BY metric
    """, values)
    valid, missing = [], []
    for row in rows:
        target = valid if row["quality"] == "VALID" else missing
        target.append(observation_dto(row))
    return valid, missing
