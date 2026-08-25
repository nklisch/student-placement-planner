# Student Placement Planner

Student Placement Planner is a friendly, local-first desktop app that helps school staff match students to placement locations while respecting capacity, choices, group needs, and driving-time limits.

[Visit the project website](https://nklisch.github.io/student-placement-planner/) · **Windows correction in progress** · [Download for Apple-Silicon Mac](https://github.com/nklisch/student-placement-planner/releases/download/v0.1.0b1/Student-Placement-Planner-0.1.0b1-macOS-Apple-Silicon.dmg)

It is designed as a calm, spreadsheet-friendly tool for school staff:

- type directly into editable tables, paste from a spreadsheet, or import CSV files;
- compare placements by road driving time;
- choose fair-commute, lowest-total-driving, or choices-first priorities;
- save projects explicitly and export or print results;
- keep roster data on the local computer, with no accounts or telemetry.

## Project status

The Apple-Silicon macOS beta is available in [v0.1.0b1](https://github.com/nklisch/student-placement-planner/releases/tag/v0.1.0b1). The original Windows asset was withdrawn after a clean PC exposed a missing Visual C++ runtime; a corrected installer is being built. End users will not need Python or a terminal.

Manual entry, no-key community routing, openrouteservice, Google Maps, and offline-region workflows are implemented and tested. Offline regions are downloaded directly from Geofabrik and prepared inside the app, without project-hosted map files. Preview signatures can produce a one-time operating-system warning; the release includes checksums and GitHub build attestations.

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
