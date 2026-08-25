"""Built-in sample data for first-run exploration.

Parsed through the normal CSV import path so the sample exercises exactly
what users get from their own files.
"""

from __future__ import annotations

from placement_optimizer.application import DraftSession, LocationDraft, StudentDraft
from placement_optimizer.domain import Coordinate
from placement_optimizer.optimization import AssignmentRules, Preference
from placement_optimizer.projects import parse_locations_csv, parse_matrix_csv, parse_students_csv

SAMPLE_STUDENTS_CSV = """student_id,name,address
s1,Aisha Khan,12 Cedar Avenue
s2,Mateo Ruiz,4 Harbor Road
s3,Ana Petrova,88 Hillcrest Lane
s4,Liam O'Brien,15 Willow Street
s5,Grace Nakamura,203 Birch Boulevard
s6,Noah Williams,7 Orchard Way
s7,Zara Ahmed,31 Elm Close
s8,Oliver Chen,9 Maple Drive
"""

SAMPLE_LOCATIONS_CSV = """location_id,name,capacity,address
l1,North Clinic,2,40 Medical Way
l2,Riverside School,2,18 River Street
l3,Community Workshop,2,5 Maker Lane
l4,Greenhouse Farm,2,72 Field Road
"""

SAMPLE_TIMES_CSV = """student_id,location_id,driving_minutes
s1,l1,8
s1,l2,22
s1,l3,14
s1,l4,31
s2,l1,26
s2,l2,9
s2,l3,18
s2,l4,27
s3,l1,12
s3,l2,17
s3,l3,6
s3,l4,24
s4,l1,19
s4,l2,28
s4,l3,11
s4,l4,7
s5,l1,15
s5,l2,10
s5,l3,21
s5,l4,29
s6,l1,30
s6,l2,13
s6,l3,25
s6,l4,16
s7,l1,10
s7,l2,20
s7,l3,9
s7,l4,23
s8,l1,24
s8,l2,15
s8,l3,27
s8,l4,5
"""

SAMPLE_PREFERENCES = (
    ("s1", ("l1", "l3", "l2")),
    ("s2", ("l2", "l4")),
)


def _format_coordinate(coordinate: Coordinate | None) -> str:
    if coordinate is None:
        return ""
    return f"{coordinate.latitude:g}, {coordinate.longitude:g}"


def build_sample_session() -> DraftSession:
    session = DraftSession("Sample project")
    for student in parse_students_csv(SAMPLE_STUDENTS_CSV).items:
        session.add_student(
            StudentDraft(
                key="",
                id=student.id,
                name=student.name,
                address=student.address or "",
                coordinates=_format_coordinate(student.coordinate),
            )
        )
    for location in parse_locations_csv(SAMPLE_LOCATIONS_CSV).items:
        session.add_location(
            LocationDraft(
                key="",
                id=location.id,
                name=location.name,
                capacity=str(location.capacity),
                minimum_capacity=(
                    str(location.minimum_capacity) if location.minimum_capacity else ""
                ),
                address=location.address or "",
                coordinates=_format_coordinate(location.coordinate),
            )
        )

    student_keys = {row.id: row.key for row in session.students}
    location_keys = {row.id: row.key for row in session.locations}
    for entry in parse_matrix_csv(SAMPLE_TIMES_CSV).items:
        if entry.duration_seconds is None:
            continue
        session.set_manual_time(
            student_keys[entry.student_id],
            location_keys[entry.location_id],
            f"{entry.duration_seconds / 60:g}",
        )

    session.set_rules(
        AssignmentRules(
            preferences=tuple(
                Preference(student_id, location_ids)
                for student_id, location_ids in SAMPLE_PREFERENCES
            )
        )
    )
    session.mark_saved()
    return session
