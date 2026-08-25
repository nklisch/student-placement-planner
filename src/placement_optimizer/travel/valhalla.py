"""Lazy pyvalhalla adapter for matrices calculated from an installed map pack."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from contextlib import suppress
from itertools import islice
from math import isfinite
from typing import Protocol

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel.base import TravelDataError, TravelMatrix
from placement_optimizer.travel.packs import InstalledMapPack


class _Actor(Protocol):
    def matrix(self, request: dict[str, object]) -> object: ...


ActorFactory = Callable[[dict[str, object]], _Actor]
ConfigFactory = Callable[..., dict[str, object]]


class ValhallaRouteMatrix:
    """Driving matrices from the native Valhalla engine and one regional pack."""

    def __init__(
        self,
        pack: InstalledMapPack,
        *,
        block_size: int = 40,
        actor_factory: ActorFactory | None = None,
        config_factory: ConfigFactory | None = None,
    ) -> None:
        if not 1 <= block_size <= 100:
            raise ValueError("Valhalla block_size must be between 1 and 100")
        if not pack.compatible:
            raise TravelDataError(pack.problem)
        self._pack = pack
        self._block_size = block_size
        self._actor_factory = actor_factory
        self._config_factory = config_factory
        self._actor: _Actor | None = None

    async def route_matrix(
        self,
        origins: Sequence[Coordinate],
        destinations: Sequence[Coordinate],
    ) -> TravelMatrix:
        if not origins:
            return TravelMatrix((), (), source=self._source)
        if not destinations:
            raise TravelDataError("at least one route destination is required")

        distances: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
        durations: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
        actor = self._get_actor()
        for origin_start, origin_block in _blocks(origins, self._block_size):
            for destination_start, destination_block in _blocks(destinations, self._block_size):
                request: dict[str, object] = {
                    "sources": [_location(point) for point in origin_block],
                    "targets": [_location(point) for point in destination_block],
                    "costing": "auto",
                    "units": "kilometers",
                    "verbose": False,
                }
                try:
                    response = await _native_matrix(actor, request)
                    block_distances, block_durations = _parse_matrix(
                        response,
                        len(origin_block),
                        len(destination_block),
                    )
                except TravelDataError:
                    raise
                except Exception as error:
                    raise TravelDataError(
                        "offline routing couldn't calculate these driving times"
                    ) from error
                for offset, row in enumerate(block_distances):
                    distances[origin_start + offset][
                        destination_start : destination_start + len(destination_block)
                    ] = row
                for offset, row in enumerate(block_durations):
                    durations[origin_start + offset][
                        destination_start : destination_start + len(destination_block)
                    ] = row
        return TravelMatrix(
            tuple(tuple(row) for row in distances),
            tuple(tuple(row) for row in durations),
            self._source,
        )

    @property
    def _source(self) -> str:
        manifest = self._pack.manifest
        return f"valhalla:{manifest.pack_id}:{manifest.version}"

    def _get_actor(self) -> _Actor:
        if self._actor is not None:
            return self._actor
        actor_factory = self._actor_factory
        config_factory = self._config_factory
        if actor_factory is None or config_factory is None:
            try:
                from valhalla import Actor
                from valhalla.config import get_config
            except ImportError as error:
                raise TravelDataError(
                    "offline routing isn't included in this build; reinstall with offline maps"
                ) from error
            actor_factory = Actor
            config_factory = get_config
        try:
            # Current pyvalhalla validates both values. The extract is preferred;
            # an existing pack directory supplies the harmless tile_dir fallback.
            config = config_factory(
                tile_extract=self._pack.tiles_path,
                tile_dir=self._pack.path,
                verbose=False,
            )
            self._actor = actor_factory(config)
        except (OSError, RuntimeError, ValueError) as error:
            raise TravelDataError(
                f"{self._pack.manifest.name} couldn't be opened for offline routing"
            ) from error
        return self._actor


async def _native_matrix(actor: _Actor, request: dict[str, object]) -> object:
    """Run one native block off-loop and never abandon its filesystem-backed actor."""

    task = asyncio.create_task(asyncio.to_thread(actor.matrix, request))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Native code cannot be interrupted safely. Wait for only the current
        # block, then propagate cancellation before another block can start.
        with suppress(Exception):
            await task
        raise


def _location(coordinate: Coordinate) -> dict[str, float]:
    return {"lat": coordinate.latitude, "lon": coordinate.longitude}


def _parse_matrix(
    response: object,
    rows: int,
    columns: int,
) -> tuple[list[list[int | None]], list[list[int | None]]]:
    if not isinstance(response, dict):
        raise TravelDataError("offline routing returned an invalid matrix")
    values = response.get("sources_to_targets")
    if not isinstance(values, dict):
        raise TravelDataError("offline routing returned an invalid matrix")
    raw_distances = values.get("distances")
    raw_durations = values.get("durations")
    return (
        _parse_values(raw_distances, rows, columns, distance=True),
        _parse_values(raw_durations, rows, columns, distance=False),
    )


def _parse_values(
    value: object,
    rows: int,
    columns: int,
    *,
    distance: bool,
) -> list[list[int | None]]:
    if not isinstance(value, list) or len(value) != rows:
        raise TravelDataError("offline routing returned an incorrectly sized matrix")
    result: list[list[int | None]] = []
    for row in value:
        if not isinstance(row, list) or len(row) != columns:
            raise TravelDataError("offline routing returned an incorrectly sized matrix")
        parsed = []
        for cell in row:
            if cell is None:
                parsed.append(None)
                continue
            try:
                number = float(cell)
            except (TypeError, ValueError) as error:
                raise TravelDataError("offline routing returned an invalid matrix value") from error
            if not isfinite(number) or number < 0:
                raise TravelDataError("offline routing returned an invalid matrix value")
            parsed.append(round(number * 1000) if distance else round(number))
        result.append(parsed)
    return result


def _blocks[T](values: Sequence[T], size: int) -> list[tuple[int, list[T]]]:
    iterator = iter(values)
    result: list[tuple[int, list[T]]] = []
    start = 0
    while block := list(islice(iterator, size)):
        result.append((start, block))
        start += len(block)
    return result
