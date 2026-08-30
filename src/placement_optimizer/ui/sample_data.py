"""Built-in sample data for first-run exploration.

Parsed through the normal CSV import path so the sample exercises exactly
what users get from their own files. Public landmarks serve as privacy-safe
student origins, while placement rows use real northern Colorado businesses;
the bundled travel times were calculated from those coordinates.
"""

from __future__ import annotations

from placement_optimizer.application import DraftSession, LocationDraft, StudentDraft
from placement_optimizer.domain import Coordinate
from placement_optimizer.optimization import AssignmentRules, Preference
from placement_optimizer.projects import parse_locations_csv, parse_matrix_csv, parse_students_csv

SAMPLE_STUDENTS_CSV = """student_id,name,address,latitude,longitude
s1,Example Student 01,"300 N Adams Ave, Loveland, CO 80537",40.3974971,-105.0692592
s2,Example Student 02,"503 N Lincoln Ave, Loveland, CO 80537",40.3966195,-105.0733009
s3,Example Student 03,"700 E 4th St, Loveland, CO 80537",40.3946665,-105.0672849
s4,Example Student 04,"5971 Sky Pond Dr, Loveland, CO 80538",40.4157174,-104.989151
s5,Example Student 05,"201 Peterson St, Fort Collins, CO 80524",40.5849487,-105.0726563
s6,Example Student 06,"408 Mason Ct, Fort Collins, CO 80524",40.5934306,-105.0780625
s7,Example Student 07,"2145 Centre Ave, Fort Collins, CO 80526",40.5613001,-105.0856453
s8,Example Student 08,"215 E Foothills Pkwy, Fort Collins, CO 80525",40.544534,-105.073685
"""

SAMPLE_LOCATIONS_CSV = (
    "location_id,name,capacity,address,latitude,longitude\n"
    'l1,Cottonwood Centre,2,"815 Centre Ave, Fort Collins, CO 80526",'
    "40.5553402,-105.0913073\n"
    'l2,Cottonwood Lemay,2,"4824 S Lemay Ave, Fort Collins, CO 80525",'
    "40.5192821,-105.0572307\n"
    'l3,Cottonwood West,2,"940 Worthington Cir, Fort Collins, CO 80526",'
    "40.5573834,-105.0941321\n"
    'l4,Cottonwood Windsor Commons,2,"1475 Main St, Windsor, CO 80550",'
    "40.4797646,-104.8969468\n"
    'l5,Good Samaritan Fort Collins,2,"508 W Trilby Rd, Fort Collins, CO 80525",'
    "40.4956128,-105.0856783\n"
    'l6,Good Samaritan Loveland,2,"2101 S Garfield Ave, Loveland, CO 80537",'
    "40.367572,-105.078254\n"
    'l7,North Shore Loveland,2,"1365 W 29th St, Loveland, CO 80538",'
    "40.4217716,-105.09613\n"
)

SAMPLE_TIMES_CSV = """student_id,location_id,driving_minutes
s1,l1,22
s1,l2,19
s1,l3,23
s1,l4,24
s1,l5,14
s1,l6,6
s1,l7,7
s2,l1,21
s2,l2,18
s2,l3,22
s2,l4,24
s2,l5,13
s2,l6,5
s2,l7,6
s3,l1,23
s3,l2,20
s3,l3,24
s3,l4,25
s3,l5,15
s3,l6,6
s3,l7,8
s4,l1,26
s4,l2,19
s4,l3,27
s4,l4,18
s4,l5,19
s4,l6,15
s4,l7,15
s5,l1,7
s5,l2,13
s5,l3,8
s5,l4,25
s5,l5,14
s5,l6,30
s5,l7,23
s6,l1,9
s6,l2,15
s6,l3,10
s6,l4,27
s6,l5,16
s6,l6,32
s6,l7,25
s7,l1,2
s7,l2,11
s7,l3,2
s7,l4,27
s7,l5,11
s7,l6,27
s7,l7,18
s8,l1,5
s8,l2,8
s8,l3,6
s8,l4,25
s8,l5,9
s8,l6,24
s8,l7,17
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
