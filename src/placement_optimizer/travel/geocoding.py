"""Offline address lookup backed by a small SQLite FTS index in each map pack."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel.base import GeocodingResult, TravelDataError

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class AddressRecord:
    display_name: str
    latitude: float
    longitude: float


def normalize_address(value: str) -> str:
    """Normalize user and pack text for deterministic full-text matching."""

    folded = unicodedata.normalize("NFKD", value).casefold()
    plain = "".join(character if character.isalnum() else " " for character in folded)
    return _WHITESPACE.sub(" ", plain).strip()


class OfflineAddressIndex:
    """Resolve addresses without a service or network connection."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    async def geocode(self, address: str) -> GeocodingResult:
        normalized = normalize_address(address)
        if not normalized:
            raise TravelDataError("enter an address or latitude/longitude")
        try:
            with sqlite3.connect(f"file:{self._path}?mode=ro", uri=True) as database:
                exact = database.execute(
                    "SELECT display_name, latitude, longitude "
                    "FROM address_search WHERE normalized = ? LIMIT 1",
                    (normalized,),
                ).fetchone()
                row = exact or self._search(database, normalized)
        except sqlite3.Error as error:
            raise TravelDataError("the offline address index couldn't be read") from error
        if row is None:
            raise TravelDataError(f"address was not found in the installed map pack: {address}")
        try:
            coordinate = Coordinate(latitude=float(row[1]), longitude=float(row[2]))
        except (TypeError, ValueError) as error:
            raise TravelDataError(
                "the offline address index contains invalid coordinates"
            ) from error
        return GeocodingResult(coordinate, str(row[0]))

    @staticmethod
    def _search(database: sqlite3.Connection, normalized: str):
        # Prefixes make incomplete postcodes and abbreviated street names useful while
        # requiring every entered token to appear in the selected address.
        query = " AND ".join(f'"{token}"*' for token in normalized.split())
        return database.execute(
            "SELECT display_name, latitude, longitude FROM address_search "
            "WHERE address_search MATCH ? ORDER BY bm25(address_search) LIMIT 1",
            (query,),
        ).fetchone()


class AddressIndexBuilder:
    """Incrementally build a pack index without retaining a region in memory."""

    def __init__(self, path: str | Path, *, batch_size: int = 10_000) -> None:
        self.target = Path(path)
        self.temporary = self.target.with_name(f".{self.target.name}.tmp")
        self.batch_size = batch_size
        self.count = 0
        self._database: sqlite3.Connection | None = None
        self._rows: list[tuple[str, str, float, float]] = []

    def __enter__(self) -> AddressIndexBuilder:
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.temporary.unlink(missing_ok=True)
        self._database = sqlite3.connect(self.temporary)
        self._database.execute(
            "CREATE VIRTUAL TABLE address_search USING fts5("
            "display_name, normalized, latitude UNINDEXED, longitude UNINDEXED, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        return self

    def add(self, record: AddressRecord) -> None:
        normalized = normalize_address(record.display_name)
        if not normalized:
            return
        Coordinate(record.latitude, record.longitude)
        self._rows.append(
            (record.display_name.strip(), normalized, record.latitude, record.longitude)
        )
        if len(self._rows) >= self.batch_size:
            self._flush()

    def _flush(self) -> None:
        if not self._rows or self._database is None:
            return
        self._database.executemany(
            "INSERT INTO address_search(display_name, normalized, latitude, longitude) "
            "VALUES (?, ?, ?, ?)",
            self._rows,
        )
        self.count += len(self._rows)
        self._rows.clear()

    def __exit__(self, exception_type, _exception, _traceback) -> None:
        database = self._database
        self._database = None
        try:
            if database is None:
                return
            if exception_type is None:
                self._flush_with(database)
                database.execute("INSERT INTO address_search(address_search) VALUES ('optimize')")
                database.commit()
            database.close()
            if exception_type is None:
                self.temporary.replace(self.target)
        finally:
            self.temporary.unlink(missing_ok=True)

    def _flush_with(self, database: sqlite3.Connection) -> None:
        if self._rows:
            database.executemany(
                "INSERT INTO address_search(display_name, normalized, latitude, longitude) "
                "VALUES (?, ?, ?, ?)",
                self._rows,
            )
            self.count += len(self._rows)
            self._rows.clear()


def create_address_index(records: Iterable[AddressRecord], path: str | Path) -> int:
    """Build the deterministic address index used by downloadable packs and tests."""

    with AddressIndexBuilder(path) as builder:
        for record in records:
            builder.add(record)
    return builder.count
