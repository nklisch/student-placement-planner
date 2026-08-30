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
s1,Aisha Khan,"300 N Adams Ave, Loveland, CO 80537",40.3974971,-105.0692592
s2,Mateo Ruiz,"503 N Lincoln Ave, Loveland, CO 80537",40.3966195,-105.0733009
s3,Ana Petrova,"700 E 4th St, Loveland, CO 80537",40.3946665,-105.0672849
s4,Liam O'Brien,"5971 Sky Pond Dr, Loveland, CO 80538",40.4157174,-104.989151
s5,Grace Nakamura,"201 Peterson St, Fort Collins, CO 80524",40.5849487,-105.0726563
s6,Noah Williams,"408 Mason Ct, Fort Collins, CO 80524",40.5934306,-105.0780625
s7,Zara Ahmed,"2145 Centre Ave, Fort Collins, CO 80526",40.5613001,-105.0856453
s8,Oliver Chen,"215 E Foothills Pkwy, Fort Collins, CO 80525",40.544534,-105.073685
"""

SAMPLE_LOCATIONS_CSV = (
    "location_id,name,capacity,address,latitude,longitude\n"
    'l1,Target Loveland,2,"1725 Rocky Mountain Ave, Loveland, CO 80538",'
    "40.4097852,-105.0039464\n"
    'l2,Walmart Supercenter Loveland,2,"1325 Denver Ave, Loveland, CO 80537",'
    "40.404432,-105.0466952\n"
    'l3,Whole Foods Market Fort Collins,2,"2201 S College Ave, Fort Collins, CO 80525",'
    "40.5591621,-105.077211\n"
    'l4,The Home Depot North Fort Collins,2,"1251 E Magnolia St, Fort Collins, CO 80524",'
    "40.5832465,-105.0545061\n"
)

SAMPLE_TIMES_CSV = """student_id,location_id,driving_minutes
s1,l1,9
s1,l2,5
s1,l3,21
s1,l4,27
s2,l1,9
s2,l2,5
s2,l3,21
s2,l4,27
s3,l1,9
s3,l2,5
s3,l3,22
s3,l4,28
s4,l1,5
s4,l2,9
s4,l3,24
s4,l4,21
s5,l1,21
s5,l2,25
s5,l3,5
s5,l4,4
s6,l1,23
s6,l2,27
s6,l3,7
s6,l4,6
s7,l1,23
s7,l2,25
s7,l3,3
s7,l4,8
s8,l1,22
s8,l2,22
s8,l3,4
s8,l4,10
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
