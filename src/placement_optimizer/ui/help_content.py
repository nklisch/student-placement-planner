"""Plain-language help content shared by tooltips and in-app guides."""

# Keep each piece of displayed prose intact so copy reviews can read it as users do.
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass

STUDENT_FIELD_HELP = (
    "The student's name, shown in rules and results.",
    "A short code used to match this row when you import or export a CSV. It's filled in automatically.",
    "The student's starting street address. Needed only when maps calculate driving times.",
    "Optional latitude and longitude, such as 51.5074, -0.1278. These can replace the address.",
)

LOCATION_FIELD_HELP = (
    "The placement location's name, shown in rules and results.",
    "A short code used to match this row when you import or export a CSV. It's filled in automatically.",
    "The most students this location can take.",
    "Optional. The location must receive at least this many students; leave blank for no minimum.",
    "The location's street address. Needed only when maps calculate driving times.",
    "Optional latitude and longitude, such as 51.5074, -0.1278. These can replace the address.",
)

GOAL_HELP = {
    "Fair commute (recommended)": (
        "Keeps the longest drive as short as possible, then reduces the number of long drives and the total driving."
    ),
    "Lowest total driving": "Makes the combined driving time of all students as low as possible.",
    "Choices first": "Gives students their ranked choices wherever possible, then shortens drives.",
    "Custom": "Uses the priority order chosen in More options.",
    "More options…": "Choose the exact order of goals, commute target, and calculation time.",
}

RULE_ACTION_HELP = {
    "Ranked choices…": "Record up to three preferred locations for each student.",
    "Keep students together…": "Require selected students to be placed at the same location.",
    "Keep students apart…": "Require selected students to be placed at different locations.",
    "Pin a placement…": "Require one student to be placed at one particular location.",
    "Not allowed at a location…": "Prevent one student from being placed at one location.",
    "Limit driving time…": "Set a maximum drive for everyone or for individual students.",
    "Allowed locations only…": "Restrict one student to a selected set of locations.",
}


@dataclass(frozen=True, slots=True)
class HelpEntry:
    heading: str
    body: str


@dataclass(frozen=True, slots=True)
class HelpTopic:
    title: str
    introduction: str
    entries: tuple[HelpEntry, ...]


HELP_TOPICS = (
    HelpTopic(
        "Quick start",
        "Work through the five steps in order, or move between them whenever you need to.",
        (
            HelpEntry(
                "1. Add students",
                "Type directly in the table, paste rows copied from a spreadsheet, or import CSV. "
                "Names are required; IDs are filled in automatically and can be changed.",
            ),
            HelpEntry(
                "2. Add locations",
                "Enter every placement location and its maximum capacity. A minimum is optional.",
            ),
            HelpEntry(
                "3. Add only necessary rules",
                "Rules are optional. Use them for choices, required or forbidden placements, "
                "keeping students together or apart, allowed locations, and strict driving limits.",
            ),
            HelpEntry(
                "4. Enter or calculate driving times",
                "For manual entry, every student-to-location cell needs driving minutes or x for no "
                "route. You can paste a rectangular block straight from a spreadsheet.",
            ),
            HelpEntry(
                "5. Find placements",
                "Choose a goal at the bottom of the window, then select Find placements. Results show "
                "where each student is placed, their drive, their choices, and how full each location is.",
            ),
            HelpEntry(
                "Try without entering data",
                "Choose File → Load sample data to explore a complete example. You'll be asked "
                "whether to save the project you have open first.",
            ),
        ),
    ),
    HelpTopic(
        "Student fields",
        "Only the name is needed when you enter driving times yourself. If you use maps to calculate times, an address or coordinates are also needed.",
        tuple(
            HelpEntry(heading, body)
            for heading, body in zip(
                ("Name", "ID", "Address", "Coordinates (optional)"),
                STUDENT_FIELD_HELP,
                strict=True,
            )
        ),
    ),
    HelpTopic(
        "Location fields",
        "A name and maximum capacity are required. An address is needed only when maps calculate the times.",
        tuple(
            HelpEntry(heading, body)
            for heading, body in zip(
                (
                    "Name",
                    "ID",
                    "Capacity",
                    "Minimum (optional)",
                    "Address",
                    "Coordinates (optional)",
                ),
                LOCATION_FIELD_HELP,
                strict=True,
            )
        ),
    ),
    HelpTopic(
        "Rules",
        "Rules limit which arrangements are allowed. Ranked choices help guide the result; every other rule is always followed.",
        (
            HelpEntry("Ranked choices", RULE_ACTION_HELP["Ranked choices…"]),
            HelpEntry(
                "Keep together / apart",
                "Place selected students at one shared location, or require different locations.",
            ),
            HelpEntry(
                "Pin / not allowed",
                "Require one student to be placed at one location, or prevent it.",
            ),
            HelpEntry(
                "Driving limit",
                "Set a strict maximum driving time. No student can be placed somewhere the drive would be over the limit.",
            ),
            HelpEntry(
                "Allowed locations",
                "Restrict a student to selected locations. Leave every location checked to allow anywhere.",
            ),
            HelpEntry(
                "When rules conflict",
                "You'll be told that no arrangement fits. Nothing is changed, so you can adjust the rules.",
            ),
        ),
    ),
    HelpTopic(
        "Travel times",
        "Driving time is the main measure used to compare placements.",
        (
            HelpEntry(
                "A number",
                "Driving minutes from that student's starting point to that location, such as 18 or 12.5.",
            ),
            HelpEntry(
                "x or -",
                "There is no usable driving route. That student will not be placed there.",
            ),
            HelpEntry(
                "A blank cell",
                "No time has been entered yet. Every cell needs a number or x before placements can be found.",
            ),
            HelpEntry(
                "Import and export",
                "Imported CSV files are matched to your students and locations by their IDs. Use Export times… to produce a file in the exact format the import expects.",
            ),
            HelpEntry(
                "Using maps",
                "Download an OpenStreetMap region directly from Geofabrik and let the app prepare it for offline use, use the occasional-use community option with no key, or connect openrouteservice or Google. Type a direct region name and choose a matching suggestion; download and preparation progress stays visible in the region window. Online services receive only addresses or coordinates—never names, IDs, choices, capacities, or rules. Every map option lets you review address matches before calculation.",
            ),
        ),
    ),
    HelpTopic(
        "Goals and results",
        "Goals are applied in order: the app makes the first goal as good as it can before improving the next.",
        (
            HelpEntry("Fair commute", GOAL_HELP["Fair commute (recommended)"]),
            HelpEntry("Lowest total driving", GOAL_HELP["Lowest total driving"]),
            HelpEntry("Choices first", GOAL_HELP["Choices first"]),
            HelpEntry("More options", GOAL_HELP["More options…"]),
            HelpEntry(
                "Not placed",
                "Shown only when 'Allow students to be left unplaced' is turned on in More options.",
            ),
            HelpEntry(
                "Results became out of date",
                "Your previous result stays visible when you change your data. Select Update placements to calculate it again.",
            ),
            HelpEntry(
                "Print preview",
                "Print opens a preview. Arrange the list by student or group it by placement, and turn off drive time and distance when you only need the names.",
            ),
        ),
    ),
    HelpTopic(
        "Spreadsheet tips",
        "The roster and travel tables behave like compact spreadsheets.",
        (
            HelpEntry(
                "Paste",
                "Copy cells from Excel, Numbers, or another spreadsheet, select the first destination cell, and paste.",
            ),
            HelpEntry(
                "Copy",
                "Select cells and copy; you can paste them straight into a spreadsheet.",
            ),
            HelpEntry(
                "Move while editing",
                "Tab moves across, Shift+Tab moves back, Enter saves the cell and moves down, and Escape cancels the current edit.",
            ),
            HelpEntry(
                "Clear cells",
                "Select cells and press Delete or Backspace. To remove whole students or locations, select their rows and use Remove selected or Edit → Delete rows.",
            ),
            HelpEntry(
                "Repair errors",
                "Text the table can't use is kept in the cell and marked, not deleted. Hover the marked cell for the problem, or select an issue above the table to jump to it. An untouched extra row with only its automatic ID is ignored; any row you start filling must have its required values.",
            ),
            HelpEntry(
                "Undo",
                "A pasted block counts as one undo step. Undo works in the table you're in; on the Rules page it reverses the most recent rule deletion.",
            ),
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class WalkthroughStep:
    page_index: int
    title: str
    body: str
    try_this: str


WALKTHROUGH_STEPS = (
    WalkthroughStep(
        0,
        "Add the students who need placements",
        "Use one row per student. For manual travel times, a name is enough to begin; the ID is filled automatically.",
        "Try typing in the + row at the bottom of the table, pasting spreadsheet rows, or choosing Import CSV.",
    ),
    WalkthroughStep(
        1,
        "Add placement locations and spaces",
        "Each location needs a name and capacity. Minimum, address, and coordinates are optional.",
        "Hover a column heading for its definition. Leave Minimum blank unless this location must always receive at least that many students.",
    ),
    WalkthroughStep(
        2,
        "Add only the rules that matter",
        "Most projects need few or no rules. Rules can record choices, keep students together or apart, pin a student to a location, prevent a placement, set driving limits, and restrict where a student can go.",
        "Open Add a rule to see the available rule types. Nothing changes until you accept a rule dialog.",
    ),
    WalkthroughStep(
        3,
        "Enter or calculate driving times",
        "In the grid, enter minutes for each student and location. Use x when no route is possible. Every cell needs a number or an x.",
        "A rectangular block copied from a spreadsheet can fill the grid in one paste.",
    ),
    WalkthroughStep(
        4,
        "Choose a goal and review placements",
        "The goal, chosen at the bottom of the window, controls what improves first. Fair commute is a good default; the results show who goes where and how full each location is.",
        "When the button at the bottom left says Ready to find placements, choose Find placements. You can export or print the result.",
    ),
)
