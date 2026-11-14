import sqlite3
from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, Request

from astra.db import read_snapshot
from astra.models import (
    CrewList, CrewProfile, DatasetInfo, DatasetMetadata, LatestObservations, Metric, Mission,
    ObservationPage, ReplayCommand, ReplayState, ReplayView,
)
from astra.reads import (
    ApiError, HistoryRequest, LatestRequest, ObservationFilters, crew_profile, history_page,
    latest_observations, observation_dto, replay_state, visible_observations,
)
from astra.replay import replay_view

router = APIRouter(prefix="/api")


@contextmanager
def mission_snapshot(request: Request) -> Iterator[tuple[sqlite3.Connection, ReplayState]]:
    if not request.app.state.schema_ready:
        raise ApiError(503, "database_unavailable", "Mission storage is unavailable.")
    with read_snapshot(request.app.state.database_path) as connection:
        yield connection, replay_state(connection)


def crew_rows(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute("SELECT crew_id, display_name, role FROM crew ORDER BY crew_id")]


@router.get("/crew", response_model=CrewList)
def crew(request: Request):
    with mission_snapshot(request) as (connection, _):
        return {"items": crew_rows(connection)}


@router.get("/crew/{crew_id}", response_model=CrewProfile)
def profile(request: Request, crew_id: str):
    with mission_snapshot(request) as (connection, _):
        return crew_profile(connection, crew_id)


@router.get("/observations", response_model=ObservationPage)
def observations(request: Request, query: HistoryRequest):
    with mission_snapshot(request) as (connection, replay):
        return history_page(connection, replay, query)


@router.get("/observations/latest", response_model=LatestObservations)
def latest(request: Request, query: LatestRequest):
    with mission_snapshot(request) as (connection, replay):
        query.check(connection)
        if query.crew_id is None and query.scope != "cabin":
            raise ApiError(422, "invalid_filters", "Select a crew member or cabin scope for latest readings.")
        readings, missing = latest_observations(connection, replay, query)
        return LatestObservations(
            revision=replay.revision, cursor_utc=replay.cursor_utc, items=readings,
            latest_missing=missing, next_cursor=None,
        )


@router.get("/mission", response_model=Mission)
def mission(request: Request):
    with mission_snapshot(request) as (connection, replay):
        readings, missing = latest_observations(connection, replay, ObservationFilters(scope="cabin"))
        summaries = crew_rows(connection)
        crew_readings = {}
        for profile in summaries:
            crew_id = profile["crew_id"]
            sql, values = visible_observations(replay, ObservationFilters(crew_id=crew_id), include_private=False)
            latest = connection.execute(
                sql + " AND quality = 'VALID' ORDER BY timestamp_utc DESC, observation_id DESC LIMIT 1", values,
            ).fetchone()
            if latest is not None:
                crew_readings[crew_id] = observation_dto(latest)
        return {
            "revision": replay.revision, "cursor_utc": replay.cursor_utc, "mission_day": replay.mission_day,
            "replay_status": replay.status, "crew_summaries": summaries, "crew_readings": crew_readings,
            "cabin_readings": readings, "cabin_latest_missing": missing,
            "insights": [],
        }


@router.get("/replay")
def replay(request: Request) -> ReplayView:
    with mission_snapshot(request) as (connection, _):
        return replay_view(connection, request.app.state.replay_engine.error)


@router.post("/replay")
async def control_replay(request: Request, command: ReplayCommand) -> ReplayView:
    if not request.app.state.schema_ready:
        raise ApiError(503, "database_unavailable", "Mission storage is unavailable.")
    return await request.app.state.replay_engine.command(command)


@router.get("/data")
def data(request: Request) -> DatasetInfo:
    with mission_snapshot(request) as (connection, replay):
        row = connection.execute("SELECT * FROM datasets WHERE dataset_id = ?", (replay.dataset_id,)).fetchone()
        metadata = DatasetMetadata.model_validate_json(row["metadata_json"])
        metrics = []
        for metric in connection.execute("SELECT * FROM metrics ORDER BY scope DESC, metric"):
            item = dict(metric)
            item["is_nasa_measured"] = item["is_nasa_measured"] == 1
            metrics.append(Metric.model_validate(item))
        return DatasetInfo(
            **metadata.model_dump(), replay=replay, source_status=request.app.state.source_status, metrics=metrics,
            imported_at_utc=row["imported_at_utc"], historical_count=row["historical_count"],
            historical_missing_count=row["historical_missing_count"],
        )
