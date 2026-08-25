"""Geocoding and road-route matrix providers."""

from placement_optimizer.travel.base import (
    Geocoder,
    GeocodingResult,
    MatrixEntry,
    RouteMatrixProvider,
    TravelDataError,
    TravelMatrix,
)
from placement_optimizer.travel.geocoding import (
    AddressIndexBuilder,
    AddressRecord,
    OfflineAddressIndex,
    create_address_index,
    normalize_address,
)
from placement_optimizer.travel.google import GoogleGeocoder, GoogleRoutesMatrix
from placement_optimizer.travel.local import NominatimGeocoder, OsrmRouteMatrix
from placement_optimizer.travel.openrouteservice import (
    OpenRouteServiceGeocoder,
    OpenRouteServiceMatrix,
)
from placement_optimizer.travel.pack_builder import build_map_pack
from placement_optimizer.travel.packs import (
    DEFAULT_PACK_CATALOG_URL,
    InstalledMapPack,
    MapPackCatalog,
    MapPackCatalogEntry,
    MapPackDownloadCancelled,
    MapPackError,
    MapPackManifest,
    MapPackStore,
    file_sha256,
)
from placement_optimizer.travel.regions import (
    GEOFABRIK_CATALOG_URL,
    GeofabrikRegion,
    fetch_geofabrik_regions,
    prepare_geofabrik_region,
)
from placement_optimizer.travel.service import (
    ResolvedPlace,
    TravelCoordinateReview,
    build_travel_matrix,
    matrix_from_entries,
    resolve_travel_coordinates,
    route_reviewed_matrix,
)
from placement_optimizer.travel.valhalla import ValhallaRouteMatrix

__all__ = [
    "DEFAULT_PACK_CATALOG_URL",
    "GEOFABRIK_CATALOG_URL",
    "AddressIndexBuilder",
    "AddressRecord",
    "Geocoder",
    "GeocodingResult",
    "GeofabrikRegion",
    "GoogleGeocoder",
    "GoogleRoutesMatrix",
    "InstalledMapPack",
    "MapPackCatalog",
    "MapPackCatalogEntry",
    "MapPackDownloadCancelled",
    "MapPackError",
    "MapPackManifest",
    "MapPackStore",
    "MatrixEntry",
    "NominatimGeocoder",
    "OfflineAddressIndex",
    "OpenRouteServiceGeocoder",
    "OpenRouteServiceMatrix",
    "OsrmRouteMatrix",
    "ResolvedPlace",
    "RouteMatrixProvider",
    "TravelCoordinateReview",
    "TravelDataError",
    "TravelMatrix",
    "ValhallaRouteMatrix",
    "build_map_pack",
    "build_travel_matrix",
    "create_address_index",
    "fetch_geofabrik_regions",
    "file_sha256",
    "matrix_from_entries",
    "normalize_address",
    "prepare_geofabrik_region",
    "resolve_travel_coordinates",
    "route_reviewed_matrix",
]
