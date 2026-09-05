"""Complete manual, Google, and offline travel-mode UI workflows."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QLabel

from placement_optimizer.application import TravelMode
from placement_optimizer.domain import Coordinate
from placement_optimizer.travel import (
    ResolvedPlace,
    TravelCoordinateReview,
    TravelDataError,
    TravelMatrix,
)
from placement_optimizer.ui.mainwindow import MainWindow
from placement_optimizer.ui.pages import travel as travel_module


class _AcceptedReviewDialog(QObject):
    addressRepairRequested = Signal(str, str)
    retryRequested = Signal()

    def __init__(self, review, _parent=None) -> None:
        super().__init__()
        self._review = review

    def exec(self) -> bool:
        return True

    def corrections(self):
        return ()

    def review(self):
        return self._review


class _Workflow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def test_community(self) -> None:
        self.calls.append("test-community")

    async def review_community(self, travel_input):
        self.calls.append("review-community")
        return _review(travel_input)

    async def calculate_community(self, review):
        self.calls.append("calculate-community")
        return _matrix(review, "community_osrm")

    async def test_openrouteservice(self, _key: str) -> None:
        self.calls.append("test-openrouteservice")

    async def review_openrouteservice(self, travel_input, _key: str):
        self.calls.append("review-openrouteservice")
        return _review(travel_input)

    async def calculate_openrouteservice(self, review, _key: str):
        self.calls.append("calculate-openrouteservice")
        return _matrix(review, "openrouteservice")

    async def test_google(self, _key: str) -> None:
        self.calls.append("test-google")

    async def review_google(self, travel_input, _key: str):
        self.calls.append("review-google")
        return _review(travel_input)

    async def calculate_google(self, review, _key: str):
        self.calls.append("calculate-google")
        return _matrix(review, "google_routes")

    async def review_offline(self, travel_input, _pack):
        self.calls.append("review-offline")
        return _review(travel_input)

    async def calculate_offline(self, review, _pack):
        self.calls.append("calculate-offline")
        return _matrix(review, "valhalla:test-region:1")


class _PackStore:
    def __init__(self, pack=None) -> None:
        self.pack = pack

    def active(self):
        return self.pack


def _pack():
    return SimpleNamespace(
        compatible=True,
        problem="",
        path="/synthetic/test-region/1",
        manifest=SimpleNamespace(
            name="Test Region", version="1", addresses=SimpleNamespace(sha256="a" * 64)
        ),
    )


def _review(travel_input) -> TravelCoordinateReview:
    students = tuple(
        ResolvedPlace(
            student.id,
            student.name,
            student.address or "",
            "Matched student address",
            Coordinate(51 + index / 100, -1),
        )
        for index, student in enumerate(travel_input.students)
    )
    locations = tuple(
        ResolvedPlace(
            location.id,
            location.name,
            location.address or "",
            "Matched location address",
            Coordinate(52 + index / 100, -1),
        )
        for index, location in enumerate(travel_input.locations)
    )
    return TravelCoordinateReview(students, locations)


def _matrix(review: TravelCoordinateReview, source: str) -> TravelMatrix:
    return TravelMatrix(
        tuple(tuple(1000 for _ in review.locations) for _ in review.students),
        tuple(tuple(300 for _ in review.locations) for _ in review.students),
        source,
    )


def test_map_storage_failure_disables_only_offline_mode(qtbot, monkeypatch) -> None:
    def unavailable_store():
        raise OSError("read-only app data")

    monkeypatch.setattr(travel_module, "MapPackStore", unavailable_store)
    degraded_window = MainWindow()
    degraded_window._confirm_close = lambda: "discard"
    qtbot.addWidget(degraded_window)
    page = degraded_window.pages[3]

    assert not page.manage_packs_button.isEnabled()
    assert "Offline region storage isn't available" in page.offline_pack_label.text()
    page.manual_card.select()
    assert degraded_window.controller.session.travel_mode is TravelMode.MANUAL
    page.online_card.select()
    assert degraded_window.controller.session.travel_mode is TravelMode.COMMUNITY


def test_offline_mode_explains_that_a_region_is_needed(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    page.offline_card.select()

    assert window.controller.session.travel_mode is TravelMode.OFFLINE
    assert page.panels.currentIndex() == 1
    assert "No offline region" in page.offline_pack_label.text()
    assert page.manage_packs_button.isEnabled()
    assert not page.offline_calculate_button.isEnabled()


def test_online_mode_offers_no_key_service_and_protects_roster_data(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    page.online_card.select()

    panel = page.panels.currentWidget()
    texts = [label.text() for label in panel.findChildren(QLabel)]
    assert any("never sent" in text for text in texts)
    assert window.controller.session.travel_mode is TravelMode.COMMUNITY
    assert page.community_calculate_button.isEnabled()
    page.google_key.clear()
    page._review_addresses(TravelMode.GOOGLE)
    assert "Paste a Google Maps API key" in page.google_message.text()
    assert not window.controller.session.readiness().travel_ready


def test_community_mode_reviews_then_calculates(window, qtbot, fill_small, monkeypatch) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    workflow = _Workflow()
    page._workflow = workflow
    monkeypatch.setattr(travel_module, "AddressReviewDialog", _AcceptedReviewDialog)
    page.online_card.select()

    page._review_addresses(TravelMode.COMMUNITY)

    qtbot.waitUntil(
        lambda: window.controller.session.calculated_matrix is not None,
        timeout=5000,
    )
    qtbot.waitUntil(lambda: page._provider_worker is None, timeout=5000)
    assert workflow.calls == ["review-community", "calculate-community"]
    assert window.controller.session.calculated_matrix.source == "community_osrm"
    assert window.controller.session.readiness().travel_ready


def test_openrouteservice_requires_key(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    page.ors_key.clear()

    page._review_addresses(TravelMode.OPENROUTESERVICE)

    assert "Paste an openrouteservice API key" in page.ors_message.text()
    assert window.controller.session.travel_mode is TravelMode.OPENROUTESERVICE


def test_google_mode_reviews_then_calculates(window, qtbot, fill_small, monkeypatch) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    workflow = _Workflow()
    page._workflow = workflow
    monkeypatch.setattr(travel_module, "AddressReviewDialog", _AcceptedReviewDialog)
    page.online_card.select()
    page.google_key.setText("test-key")

    page._review_addresses(TravelMode.GOOGLE)

    qtbot.waitUntil(
        lambda: window.controller.session.calculated_matrix is not None,
        timeout=5000,
    )
    qtbot.waitUntil(lambda: page._provider_worker is None, timeout=5000)
    assert workflow.calls == ["review-google", "calculate-google"]
    assert window.controller.session.calculated_matrix.source == "google_routes"
    assert window.controller.session.readiness().travel_ready


def test_offline_mode_reviews_then_calculates(window, qtbot, fill_small, monkeypatch) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    workflow = _Workflow()
    page._workflow = workflow
    page._pack_store = _PackStore(_pack())
    monkeypatch.setattr(travel_module, "AddressReviewDialog", _AcceptedReviewDialog)
    page.offline_card.select()

    page._review_addresses(TravelMode.OFFLINE)

    qtbot.waitUntil(
        lambda: window.controller.session.calculated_matrix is not None,
        timeout=5000,
    )
    qtbot.waitUntil(lambda: page._provider_worker is None, timeout=5000)
    assert workflow.calls == ["review-offline", "calculate-offline"]
    assert window.controller.session.calculated_matrix.source.startswith("valhalla:")
    assert window.controller.session.readiness().travel_ready


def test_provider_failure_keeps_address_out_of_troubleshooting_details(
    window, qtbot, fill_small
) -> None:
    fill_small(window.controller)
    page = window.pages[3]

    class FailingWorkflow(_Workflow):
        async def review_google(self, _travel_input, _key: str):
            raise TravelDataError("address was not found: 123 Private Home")

    page._workflow = FailingWorkflow()
    page.online_card.select()
    page.google_key.setText("test-key")
    page._review_addresses(TravelMode.GOOGLE)

    qtbot.waitUntil(lambda: page._provider_worker is None, timeout=5000)
    assert "123 Private Home" in page.google_message.text()
    assert "123 Private Home" not in window._last_detail


def test_provider_result_is_discarded_when_addresses_change_mid_operation(
    window, qtbot, fill_small
) -> None:
    import asyncio

    fill_small(window.controller)
    page = window.pages[3]

    class SlowWorkflow(_Workflow):
        async def review_google(self, travel_input, _key: str):
            await asyncio.sleep(0.1)
            return _review(travel_input)

    page._workflow = SlowWorkflow()
    page.online_card.select()
    page.google_key.setText("test-key")
    page._review_addresses(TravelMode.GOOGLE)

    window.controller.session.update_student(0, address="Changed address")
    window.controller.notify()

    qtbot.waitUntil(lambda: page._provider_worker is None, timeout=5000)
    assert window.controller.session.calculated_matrix is None
    assert "data changed" in page.google_message.text().lower()


def test_provider_operation_can_be_cancelled_without_losing_manual_data(
    window, qtbot, fill_small
) -> None:
    import asyncio

    fill_small(window.controller)
    existing = dict(window.controller.session.manual_times)
    page = window.pages[3]

    class WaitingWorkflow(_Workflow):
        async def review_google(self, _travel_input, _key: str):
            await asyncio.Event().wait()

    page._workflow = WaitingWorkflow()
    page.online_card.select()
    page.google_key.setText("test-key")
    page._review_addresses(TravelMode.GOOGLE)
    qtbot.waitUntil(lambda: page._provider_worker is not None, timeout=2000)

    page.cancel_operation()

    qtbot.waitUntil(lambda: page._provider_worker is None, timeout=5000)
    assert "Cancelled" in page.google_message.text()
    assert window.controller.session.manual_times == existing


def test_travel_page_keeps_provider_request_details_behind_application_boundary() -> None:
    source = inspect.getsource(travel_module)
    for forbidden in (
        "httpx",
        "GoogleGeocoder",
        "GoogleRoutesMatrix",
        "OfflineAddressIndex",
        "ValhallaRouteMatrix",
        "build_travel_matrix",
    ):
        assert forbidden not in source


def test_mode_radios_stay_exclusive(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]

    page.manual_card.select()
    page.manual_card.radio.click()

    assert page.manual_card.radio.isChecked()
    assert (
        sum(
            card.radio.isChecked()
            for card in (page.manual_card, page.offline_card, page.online_card)
        )
        == 1
    )
    assert window.controller.session.travel_mode is TravelMode.MANUAL


def test_clicking_mode_card_body_selects_it(window, qtbot, fill_small) -> None:
    fill_small(window.controller)
    window.show()
    window.navigate(3)
    page = window.pages[3]

    qtbot.mouseClick(page.offline_card, Qt.MouseButton.LeftButton)

    assert page.offline_card.radio.isChecked()
    assert window.controller.session.travel_mode is TravelMode.OFFLINE


def test_manual_mode_remains_the_ready_path(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    page.manual_card.select()

    readiness = window.controller.session.readiness()
    assert readiness.travel_ready
    assert "Travel times ready" in page.status_label.text()


def test_invalid_import_replaces_old_time_and_keeps_valid_progress(window, fill_small) -> None:
    from placement_optimizer.projects import parse_matrix_csv

    fill_small(window.controller)
    page = window.pages[3]
    session = window.controller.session
    page._import_session = session
    page._apply_import(
        parse_matrix_csv(
            "student_id,location_id,driving_minutes\ns1,l1,ten\ns1,l2,12\nunknown,l1,5"
        )
    )
    assert session.manual_times[("student-a", "location-a")] == "ten"
    assert session.manual_times[("student-a", "location-b")] == "12"
    assert not session.readiness().travel_ready
    assert "not numeric" in page.import_report.text()
    assert "1 rows have unknown IDs" in page.import_report.text()


def test_invalid_distance_and_duplicate_pair_cannot_leave_grid_ready(window, fill_small) -> None:
    from placement_optimizer.projects import parse_matrix_csv

    fill_small(window.controller)
    page = window.pages[3]
    session = window.controller.session
    page._import_session = session
    page._apply_import(
        parse_matrix_csv(
            "student_id,location_id,driving_minutes,distance_km\n"
            "s1,l1,10,far\ns1,l2,11,1\ns1,l2,12,2"
        )
    )
    assert "invalid CSV" in session.manual_times[("student-a", "location-a")]
    assert "duplicate pair" in session.manual_times[("student-a", "location-b")]
    assert "far" in page.import_report.text()
    assert not session.readiness().travel_ready


def test_export_template_includes_blank_pairs_without_inventing_no_route(
    window, fill_small, tmp_path, monkeypatch
) -> None:
    import csv

    fill_small(window.controller)
    session = window.controller.session
    session.manual_times.clear()
    path = tmp_path / "template.csv"
    monkeypatch.setattr(window, "ask_save_csv", lambda *args: str(path))
    window.pages[3].export_csv()
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    assert {row["driving_minutes"] for row in rows} == {""}
    session.set_manual_time("student-a", "location-a", "5")
    session.set_manual_time("student-a", "location-b", "x")
    window.pages[3].export_csv()
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["driving_minutes"] for row in rows] == ["5", "no route", "", ""]


def test_missing_address_preflight_links_to_local_row(window, fill_small) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    page._show_address_preflight(window.controller.session.build_travel_input())
    requests = []
    page.addressRepairRequested.connect(lambda kind, item_id: requests.append((kind, item_id)))
    assert "Bob" in page.address_issues.text()
    page._repair_address_link("0")
    assert requests == [("Student", "s2")]


def test_retry_reuses_successes_but_not_changed_addresses_or_cleared_overrides(
    window, fill_small
) -> None:
    from dataclasses import replace

    fill_small(window.controller)
    page = window.pages[3]
    session = window.controller.session
    travel_input = session.build_travel_input()
    review = _review(travel_input)
    page._review_cache = review
    page._review_cache_context = page._review_context(TravelMode.GOOGLE)
    reused = page._reuse_review_matches(travel_input, TravelMode.GOOGLE)
    assert reused.students[0].coordinate == review.students[0].coordinate
    session.update_student(0, address="A changed street")
    changed = page._reuse_review_matches(session.build_travel_input(), TravelMode.GOOGLE)
    assert changed.students[0].coordinate is None
    page._review_cache = replace(
        review,
        students=(
            replace(review.students[0], source="Coordinate override", coordinate_override=True),
            *review.students[1:],
        ),
    )
    cleared = page._reuse_review_matches(travel_input, TravelMode.GOOGLE)
    assert cleared.students[0].coordinate is None


def test_review_cancel_is_neutral_and_keeps_successful_matches(
    window, qtbot, fill_small, monkeypatch
) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    page._workflow = _Workflow()

    class CancelledDialog(_AcceptedReviewDialog):
        def exec(self):
            return False

    monkeypatch.setattr(travel_module, "AddressReviewDialog", CancelledDialog)
    page._review_addresses(TravelMode.COMMUNITY)
    qtbot.waitUntil(lambda: page._provider_worker is None)
    assert "review cancelled" in page.community_message.text()
    assert page._review_cache is not None
    assert window.controller.session.calculated_matrix is None


def test_partial_review_retry_only_looks_up_unresolved_addresses(
    window, qtbot, fill_small, monkeypatch
) -> None:
    from placement_optimizer.travel import GeocodingResult, resolve_travel_coordinates

    fill_small(window.controller)
    session = window.controller.session
    session.update_student(1, address="Retry street")
    session.update_location(0, address="Library street")
    session.update_location(1, address="Workshop street")
    addresses = []

    class Geocoder:
        async def geocode(self, address):
            addresses.append(address)
            if address == "Retry street" and addresses.count(address) == 1:
                raise TravelDataError("Temporary failure; retry")
            return GeocodingResult(Coordinate(51, -1), "Matched " + address)

    class Workflow(_Workflow):
        async def review_community(self, travel_input):
            return await resolve_travel_coordinates(
                travel_input.students, travel_input.locations, Geocoder()
            )

    class RetryDialog(_AcceptedReviewDialog):
        attempts = 0

        def exec(self):
            type(self).attempts += 1
            if self.attempts == 1:
                assert self._review.students[0].coordinate is not None
                assert self._review.students[1].coordinate is None
                assert "Temporary failure" in self._review.students[1].error
                self.retryRequested.emit()
                return False
            assert all(place.coordinate is not None for place in self._review.students)
            assert "Retained address match" in self._review.students[0].source
            return True

    page = window.pages[3]
    page._workflow = Workflow()
    monkeypatch.setattr(travel_module, "AddressReviewDialog", RetryDialog)
    page._review_addresses(TravelMode.COMMUNITY)
    qtbot.waitUntil(lambda: session.calculated_matrix is not None, timeout=5000)
    qtbot.waitUntil(lambda: page._provider_worker is None, timeout=5000)
    assert addresses == [
        "1 Main Street",
        "Retry street",
        "Library street",
        "Workshop street",
        "Retry street",
    ]
    assert RetryDialog.attempts == 2


def test_roster_names_refresh_travel_headers_without_resetting_selection(
    window, fill_small
) -> None:
    fill_small(window.controller)
    page = window.pages[3]
    session = window.controller.session
    version = session.travel_input_version
    selected = page.model.index(1, 1)
    page.table.setCurrentIndex(selected)
    headers = []
    resets = []
    page.model.headerDataChanged.connect(lambda *args: headers.append(args))
    page.model.modelReset.connect(lambda: resets.append(True))

    session.update_student(0, name="Renamed student")
    session.update_location(1, name="Renamed location")
    window.controller.notify()

    assert session.travel_input_version == version
    assert page.model.headerData(0, Qt.Orientation.Vertical) == "Renamed student"
    assert page.model.headerData(1, Qt.Orientation.Horizontal) == "Renamed location"
    assert {change[0] for change in headers} == {Qt.Orientation.Vertical, Qt.Orientation.Horizontal}
    assert not resets
    assert page.table.currentIndex() == selected

    headers.clear()
    page.model.setData(selected, "14")
    session.update_location(0, capacity="5")
    window.controller.notify()
    assert not headers
    assert not resets
    assert page.table.currentIndex() == selected


def test_review_rechecks_roster_after_modal_dialog(window, qtbot, fill_small, monkeypatch):
    from placement_optimizer.application import StudentDraft

    fill_small(window.controller)
    session = window.controller.session
    page = window.pages[3]
    workflow = _Workflow()
    page._workflow = workflow

    class ChangedDuringReview(_AcceptedReviewDialog):
        def exec(self):
            # Models an import completion processed by the modal event loop.
            session.add_student(StudentDraft("late", name="Later import", id="s3"))
            return True

    monkeypatch.setattr(travel_module, "AddressReviewDialog", ChangedDuringReview)
    page.online_card.select()
    page.google_key.setText("test-key")
    page._review_addresses(TravelMode.GOOGLE)
    qtbot.waitUntil(lambda: page._provider_worker is None, timeout=5000)
    assert workflow.calls == ["review-google"]
    assert "changed during review" in page.google_message.text()
    assert session.calculated_matrix is None
