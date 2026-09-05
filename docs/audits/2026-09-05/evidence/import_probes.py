"""Additional UI import and identifier-edit reproductions, synthetic inputs only."""

import json

from PySide6.QtWidgets import QApplication

from placement_optimizer.application import DraftSession, LocationDraft, StudentDraft
from placement_optimizer.optimization import AssignmentRules, StudentLocationPair
from placement_optimizer.projects import parse_locations_csv, parse_students_csv
from placement_optimizer.ui.mainwindow import MainWindow

app = QApplication([])
w = MainWindow()
notes = []
w.show_toast = lambda text, *args: notes.append(text)
w.report_import = lambda **kw: None
s = w.controller.session
p = w.pages[0]
p._import_session = s
p._apply_import(parse_students_csv("name\nStudent A\nStudent B\n"))
print(
    "NAME_ONLY_CSV",
    json.dumps(
        {
            "ids": [r.id for r in s.students],
            "parser_ids": [r.id for r in parse_students_csv("name\nStudent A\nStudent B\n").items],
            "notes": notes,
            "issues": [i.message for i in s.readiness().issues],
        }
    ),
)
s = DraftSession()
w.controller.set_session(s)
p = w.pages[1]
p._import_session = s
p._apply_import(
    parse_locations_csv(
        'Name,ID,Capacity,Minimum,Address,Coordinates\nSite A,l1,2,1,,"51.5, -0.12"\n'
    )
)
print(
    "VISIBLE_COLUMN_NAMES_CSV",
    json.dumps(
        {
            "row": str(s.locations[0]),
            "issues": [i.message for i in s.readiness().issues],
            "notes": notes[-1:],
        }
    ),
)
s = DraftSession()
s.add_student(StudentDraft("s1row", name="A", id="s1"))
s.add_student(StudentDraft("s2row", name="B", id="s2"))
s.add_location(LocationDraft("l1row", name="A", id="l1", capacity="2"))
s.add_location(LocationDraft("l2row", name="B", id="l2", capacity="2"))
s.set_rules(
    AssignmentRules(pinned=(StudentLocationPair("s1", "l1"), StudentLocationPair("s2", "l2")))
)
s.update_student(0, id="s2")
s.update_student(0, id="s3")
print(
    "REPAIRED_DUPLICATE_ID",
    json.dumps(
        {
            "student_ids": [r.id for r in s.students],
            "pins": [(r.student_id, r.location_id) for r in s.rules.pinned],
        }
    ),
)
w.hide()
