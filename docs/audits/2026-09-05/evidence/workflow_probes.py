"""Read-only audit reproductions; synthetic data, temporary files, no network."""

import asyncio
import json
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from placement_optimizer.application import (
    DraftSession,
    LocationDraft,
    StudentDraft,
    TravelMode,
    solve_project,
)
from placement_optimizer.optimization import AssignmentRules, Preference
from placement_optimizer.projects import parse_matrix_csv
from placement_optimizer.travel import TravelDataError, TravelMatrix
from placement_optimizer.travel.service import resolve_travel_coordinates
from placement_optimizer.ui.controller import SessionController
from placement_optimizer.ui.mainwindow import MainWindow
from placement_optimizer.ui.printing import PrintOptions, build_results_print_html
from placement_optimizer.ui.tablemodels import (
    LocationsTableModel,
    ManualTimesModel,
    StudentsTableModel,
)

app = QApplication.instance() or QApplication([])


def sample():
    s = DraftSession("Synthetic audit")
    s.add_student(
        StudentDraft(
            "s-row", name="Student A", id="s1", address="Old street", coordinates="51.5, -0.12"
        )
    )
    s.add_location(
        LocationDraft("l-row", name="Site A", id="l1", capacity="1", coordinates="51.6, -0.13")
    )
    s.set_manual_time("s-row", "l-row", "10")
    return s


s = sample()
c = SessionController(s)
sm = StudentsTableModel(c)
lm = LocationsTableModel(c)
sm.setData(sm.index(0, 0), "Renamed student")
lm.setData(lm.index(0, 2), "5")
sm.undo.undo()
print(
    "UNDO_OTHER_PAGE",
    json.dumps(
        {"capacity_after_undo_student_name": s.locations[0].capacity, "expected_capacity": "5"}
    ),
)

s = sample()
s.set_travel_mode(TravelMode.COMMUNITY)
s.set_calculated_matrix(TravelMatrix(((1000,),), ((600,),), "community_osrm"))
c = SessionController(s)
tm = ManualTimesModel(c)
s.set_travel_mode(TravelMode.MANUAL)
tm.setData(tm.index(0, 0), "99")
tm.undo.undo()
s.set_travel_mode(TravelMode.COMMUNITY)
print(
    "UNDO_TRAVEL_VALIDITY",
    json.dumps(
        {
            "restored_cell": s.manual_times["s-row", "l-row"],
            "calculated_still_stale": s.calculated_travel_is_stale,
        }
    ),
)


class SpyGeocoder:
    def __init__(self):
        self.calls = []

    async def geocode(self, address):
        self.calls.append(address)
        raise AssertionError("Should not be called by current implementation")


s = sample()
s.update_student(0, address="Entirely different city")
g = SpyGeocoder()
inp = s.build_travel_input()
review = asyncio.run(resolve_travel_coordinates(inp.students, inp.locations, g))
print(
    "ADDRESS_CHANGE",
    json.dumps(
        {
            "entered": review.students[0].entered_address,
            "coordinate": str(review.students[0].coordinate),
            "geocoder_calls": g.calls,
        }
    ),
)

s = sample()
s.set_calculated_matrix(TravelMatrix(((1000,),), ((600,),), "community_osrm"))
s.update_student(0, address="Different city")
print(
    "MANUAL_FALLBACK_STALE",
    json.dumps(
        {
            "mode": str(s.travel_mode),
            "calculated_stale": s.calculated_travel_is_stale,
            "ready": s.readiness().ready,
            "duration": s.build_project().project.travel_matrix.durations_seconds,
        }
    ),
)

s = sample()
w = MainWindow(SessionController(s))
notes = []
w.show_toast = lambda message, *args: notes.append(message)
p = w.pages[3]
p._import_session = s
p._apply_import(parse_matrix_csv("student_id,location_id,driving_minutes\ns1,l1,ten\n"))
print(
    "INVALID_TRAVEL_IMPORT",
    json.dumps(
        {"cell": s.manual_times["s-row", "l-row"], "ready": s.readiness().ready, "feedback": notes}
    ),
)
with tempfile.TemporaryDirectory() as d:
    target = Path(d) / "times.csv"
    w.ask_save_csv = lambda *args: str(target)
    s.set_manual_time("s-row", "l-row", "")
    p.export_csv()
    print("EMPTY_TEMPLATE_EXPORT", repr(target.read_text()))

s = sample()
w.controller.set_session(s)
project = s.build_project().project
outcome = solve_project(project)
s.mark_result()
w.pages[4].show_outcome(outcome, project)
s.update_location(0, capacity="0")
w.controller.notify()
print(
    "STALE_RESULT_EXPORT",
    json.dumps(
        {
            "stale": s.results_are_stale,
            "export_enabled": w.export_action.isEnabled(),
            "print_stale_warning": "latest changes"
            in build_results_print_html(outcome, project, PrintOptions()),
        }
    ),
)
failed = solve_project(s.build_project().project)
s.mark_result()
w.pages[4].show_outcome(failed, s.build_project().project)
w.refresh_chrome()
print(
    "FAILED_RESULT_EXPORT",
    json.dumps(
        {
            "outcome": str(failed.kind),
            "placements": len(failed.result.placements),
            "export_enabled": w.export_action.isEnabled(),
            "stats_longest": w.pages[4].stat_longest.isHidden(),
        }
    ),
)

s = sample()
s.update_student(0, coordinates="", address="")
inp = s.build_travel_input()
g = SpyGeocoder()
try:
    asyncio.run(resolve_travel_coordinates(inp.students, inp.locations, g))
except TravelDataError as e:
    print(
        "MISSING_ADDRESS",
        json.dumps({"ui_receives": str(e), "row_ids_discarded_by_worker": e.item_ids}),
    )

s = sample()
s.add_location(LocationDraft("l2-row", name="Site B", id="l2", capacity="1"))
s.set_manual_time("s-row", "l2-row", "20")
s.set_rules(AssignmentRules(eligible_locations=(Preference("s1", ("l1",)),)))
s.remove_locations([0])
result = solve_project(s.build_project().project)
print(
    "DELETE_ONLY_ELIGIBLE_LOCATION",
    json.dumps(
        {
            "remaining_rule": str(s.rules.eligible_locations),
            "new_assignment": result.result.placements[0].location_id,
        }
    ),
)
w.hide()
