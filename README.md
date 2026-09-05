# Student Placement Planner

Student Placement Planner is a friendly, local-first desktop app that helps school staff match students to placement locations while respecting capacity, choices, group needs, and driving-time limits.

[Visit the project website](https://nklisch.github.io/student-placement-planner/) · [Download for Windows x64](https://github.com/nklisch/student-placement-planner/releases/download/v0.1.0b4/Student-Placement-Planner-0.1.0b4-Windows-x64-Setup.exe) · [Download for Apple-Silicon Mac](https://github.com/nklisch/student-placement-planner/releases/download/v0.1.0b4/Student-Placement-Planner-0.1.0b4-macOS-Apple-Silicon.dmg)

It is designed as a calm, spreadsheet-friendly tool for school staff:

- type directly into editable tables, paste from a spreadsheet, or import CSV files;
- compare placements by road driving time;
- choose fair-commute, lowest-total-driving, or choices-first priorities;
- save projects explicitly and export or print results;
- keep roster data on the local computer, with no accounts or telemetry.

## Project status

The Windows x64 and Apple-Silicon macOS beta is available in [v0.1.0b4](https://github.com/nklisch/student-placement-planner/releases/tag/v0.1.0b4). Both downloads are self-contained; end users do not need Python or a terminal.

Manual entry, no-key community routing, openrouteservice, Google Maps, and offline-region workflows are implemented and tested. Offline regions are downloaded directly from Geofabrik and prepared inside the app, without project-hosted map files. Preview signatures can produce operating-system warnings; some school-managed computers may block installation. Follow the [Windows/macOS installation guide](docs/INSTALLATION.md), including source checks and when to ask school IT. The release includes checksums and GitHub build attestations.

## Get started

1. [Install the app](docs/INSTALLATION.md), then choose **File → Load sample data**. No internet or account is needed for the sample.
2. Choose **Find placements**, then try **Choices first** to compare priorities. Ranked choices are preferences, not required placements.
3. Follow the [user guide](docs/USER_GUIDE.md) to enter your own roster, provide driving times, repair inputs, and share results. It includes downloadable [student](docs/examples/students.csv), [location](docs/examples/locations.csv), and [travel-time](docs/examples/travel-times.csv) CSV examples.
4. Use **File → Save** to keep an editable `.spp` project. There is no automatic roster save. A result CSV or printout is for sharing, not for restoring your project.

The same essentials are available inside the app under **Help → User guide…** and **Guided walkthrough…**.

## Developer setup

Python 3.12 is pinned through `mise`:

```bash
mise install
python -m venv .venv
.venv/bin/pip install -e '.[test,offline-maps]'
.venv/bin/pytest
```

Run the desktop application with:

```bash
.venv/bin/python -m placement_optimizer
```

Useful project pages:

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Online routing setup](docs/GOOGLE_MAPS_SETUP.md)
- [Offline map packs](docs/MAP_PACKS.md)
- [Product and build requirements](docs/BUILD_INSTRUCTIONS.md)
- [Desktop interface specification](docs/UI_SPECIFICATION.md)
- [Building and publishing releases](docs/RELEASING.md)

## License

Student Placement Planner is available under the [MIT License](LICENSE).
