"""Application boundary for online and offline travel-data operations."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from placement_optimizer.application.models import TravelInput
from placement_optimizer.domain import Coordinate
from placement_optimizer.travel import (
    GoogleGeocoder,
    GoogleRoutesMatrix,
    InstalledMapPack,
    NominatimGeocoder,
    OfflineAddressIndex,
    OpenRouteServiceGeocoder,
    OpenRouteServiceMatrix,
    OsrmRouteMatrix,
    TravelCoordinateReview,
    TravelMatrix,
    ValhallaRouteMatrix,
    resolve_travel_coordinates,
    route_reviewed_matrix,
)

HttpClientFactory = Callable[[], httpx.AsyncClient]


class TravelWorkflow:
    """Create provider objects without exposing request construction to the UI."""

    def __init__(self, client_factory: HttpClientFactory | None = None) -> None:
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(
                timeout=httpx.Timeout(45.0, connect=15.0),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "StudentPlacementPlanner/0.1 "
                        "(+https://github.com/nklisch/student-placement-planner)"
                    )
                },
            )
        )

    async def test_google(self, api_key: str) -> None:
        """Verify both APIs needed by the Google workflow."""

        async with self._client_factory() as client:
            geocoder = GoogleGeocoder(api_key, client)
            router = GoogleRoutesMatrix(api_key, client)
            match = await geocoder.geocode("1600 Amphitheatre Parkway, Mountain View, CA")
            await router.route_matrix((match.coordinate,), (match.coordinate,))

    async def review_google(
        self,
        travel_input: TravelInput,
        api_key: str,
    ) -> TravelCoordinateReview:
        async with self._client_factory() as client:
            return await resolve_travel_coordinates(
                travel_input.students,
                travel_input.locations,
                GoogleGeocoder(api_key, client),
            )

    async def calculate_google(
        self,
        review: TravelCoordinateReview,
        api_key: str,
    ) -> TravelMatrix:
        async with self._client_factory() as client:
            return await route_reviewed_matrix(review, GoogleRoutesMatrix(api_key, client))

    async def test_community(self) -> None:
        """Check the shared no-key geocoder and road router."""

        async with self._client_factory() as client:
            geocoder = NominatimGeocoder(
                "https://nominatim.openstreetmap.org",
                client,
                minimum_interval_seconds=1.05,
            )
            router = OsrmRouteMatrix("https://router.project-osrm.org", client)
            match = await geocoder.geocode("Andorra la Vella")
            await router.route_matrix((match.coordinate,), (match.coordinate,))

    async def review_community(self, travel_input: TravelInput) -> TravelCoordinateReview:
        async with self._client_factory() as client:
            return await resolve_travel_coordinates(
                travel_input.students,
                travel_input.locations,
                NominatimGeocoder(
                    "https://nominatim.openstreetmap.org",
                    client,
                    minimum_interval_seconds=1.05,
                ),
            )

    async def calculate_community(self, review: TravelCoordinateReview) -> TravelMatrix:
        async with self._client_factory() as client:
            return await route_reviewed_matrix(
                review,
                OsrmRouteMatrix("https://router.project-osrm.org", client),
            )

    async def test_openrouteservice(self, api_key: str) -> None:
        async with self._client_factory() as client:
            geocoder = OpenRouteServiceGeocoder(api_key, client)
            router = OpenRouteServiceMatrix(api_key, client)
            match = await geocoder.geocode("Heidelberg, Germany")
            await router.route_matrix((match.coordinate,), (match.coordinate,))

    async def review_openrouteservice(
        self,
        travel_input: TravelInput,
        api_key: str,
    ) -> TravelCoordinateReview:
        async with self._client_factory() as client:
            return await resolve_travel_coordinates(
                travel_input.students,
                travel_input.locations,
                OpenRouteServiceGeocoder(api_key, client),
            )

    async def calculate_openrouteservice(
        self,
        review: TravelCoordinateReview,
        api_key: str,
    ) -> TravelMatrix:
        async with self._client_factory() as client:
            return await route_reviewed_matrix(
                review,
                OpenRouteServiceMatrix(api_key, client),
            )

    async def review_offline(
        self,
        travel_input: TravelInput,
        pack: InstalledMapPack,
    ) -> TravelCoordinateReview:
        return await resolve_travel_coordinates(
            travel_input.students,
            travel_input.locations,
            OfflineAddressIndex(pack.addresses_path),
        )

    async def calculate_offline(
        self,
        review: TravelCoordinateReview,
        pack: InstalledMapPack,
    ) -> TravelMatrix:
        return await route_reviewed_matrix(review, ValhallaRouteMatrix(pack))

    async def test_offline(self, pack: InstalledMapPack) -> None:
        """Open the pack and execute a tiny route query near its center."""

        west, south, east, north = pack.manifest.bounds
        center = Coordinate((south + north) / 2, (west + east) / 2)
        await ValhallaRouteMatrix(pack).route_matrix((center,), (center,))
