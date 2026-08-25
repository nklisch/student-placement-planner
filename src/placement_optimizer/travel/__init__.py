"""Geocoding and road-route matrix providers."""

from placement_optimizer.travel.base import (
    Geocoder,
    GeocodingResult,
    MatrixEntry,
    RouteMatrixProvider,
    TravelDataError,
    TravelMatrix,
)
from placement_optimizer.travel.google import GoogleGeocoder, GoogleRoutesMatrix
from placement_optimizer.travel.local import NominatimGeocoder, OsrmRouteMatrix
from placement_optimizer.travel.service import build_travel_matrix, matrix_from_entries

__all__ = [
    "Geocoder",
    "GeocodingResult",
    "GoogleGeocoder",
    "GoogleRoutesMatrix",
    "MatrixEntry",
    "NominatimGeocoder",
    "OsrmRouteMatrix",
    "RouteMatrixProvider",
    "TravelDataError",
    "TravelMatrix",
    "build_travel_matrix",
    "matrix_from_entries",
]
