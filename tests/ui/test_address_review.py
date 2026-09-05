from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox

from placement_optimizer.domain import Coordinate
from placement_optimizer.travel import ResolvedPlace, TravelCoordinateReview
from placement_optimizer.ui.pages.addressreview import AddressReviewDialog


def _review() -> TravelCoordinateReview:
    return TravelCoordinateReview(
        (
            ResolvedPlace(
                "s1",
                "Alice",
                "1 Home Road",
                "1 Home Road, Exampletown",
                Coordinate(51.5, -0.12),
            ),
        ),
        (
            ResolvedPlace(
                "l1",
                "Clinic",
                "2 Work Road",
                "2 Work Road, Exampletown",
                Coordinate(51.52, -0.11),
            ),
        ),
    )


def test_review_dialog_allows_coordinate_correction(qtbot) -> None:
    dialog = AddressReviewDialog(_review())
    qtbot.addWidget(dialog)
    coordinate = dialog.model.index(0, 4)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)

    dialog.model.setData(coordinate, "not coordinates", Qt.ItemDataRole.EditRole)
    assert not ok.isEnabled()
    assert "latitude and longitude" in coordinate.data(Qt.ItemDataRole.ToolTipRole)

    dialog.model.setData(coordinate, "51.6, -0.2", Qt.ItemDataRole.EditRole)
    assert ok.isEnabled()
    assert dialog.review().students[0].coordinate == Coordinate(51.6, -0.2)
    assert dialog.corrections() == (("Student", "s1", Coordinate(51.6, -0.2)),)


def test_review_headers_explain_what_leaves_the_computer(qtbot) -> None:
    dialog = AddressReviewDialog(_review())
    qtbot.addWidget(dialog)

    name_help = dialog.model.headerData(
        1,
        Qt.Orientation.Horizontal,
        Qt.ItemDataRole.ToolTipRole,
    )
    assert "not sent" in name_help


def test_unresolved_rows_remain_repairable_and_keep_errors(qtbot) -> None:
    review = TravelCoordinateReview(
        (ResolvedPlace("s1", "Alice", "Missing road", "", None, "No match", "Needs correction"),),
        _review().locations,
    )
    dialog = AddressReviewDialog(review)
    qtbot.addWidget(dialog)
    assert dialog.model.index(0, 3).data() == "No match"
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert dialog.table.currentIndex().row() == 0
    assert dialog.review().students[0].coordinate is None
    dialog.model.setData(dialog.model.index(0, 4), "51.2, -0.4")
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert dialog.review().students[0].error == ""
    assert "overrides address" in dialog.model.index(0, 5).data()
    assert dialog.corrections() == (("Student", "s1", Coordinate(51.2, -0.4)),)


def test_address_repair_emits_local_row_identity(qtbot) -> None:
    dialog = AddressReviewDialog(_review())
    qtbot.addWidget(dialog)
    requests = []
    dialog.addressRepairRequested.connect(lambda kind, item_id: requests.append((kind, item_id)))
    dialog.table.setCurrentIndex(dialog.model.index(1, 2))
    dialog._repair_selected()
    assert requests == [("Location", "l1")]


def test_display_precision_does_not_create_an_implicit_coordinate_override(qtbot) -> None:
    coordinate = Coordinate(51.123456789, -0.123456789)
    review = TravelCoordinateReview((ResolvedPlace("s1", "Alice", "Road", "Road", coordinate),), ())
    dialog = AddressReviewDialog(review)
    qtbot.addWidget(dialog)
    assert dialog.corrections() == ()
    assert dialog.review().students[0].coordinate == coordinate
    assert not dialog.review().students[0].coordinate_override
