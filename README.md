# Student Placement Planner

Student Placement Planner is a friendly, local-first desktop app that helps school staff match students to placement locations while respecting capacity, choices, group needs, and driving-time limits.

[Visit the project website](https://nklisch.github.io/student-placement-planner/) · [View releases](https://github.com/nklisch/student-placement-planner/releases)

It is designed as a calm, spreadsheet-friendly tool for school staff:

- type directly into editable tables, paste from a spreadsheet, or import CSV files;
- compare placements by road driving time;
- choose fair-commute, lowest-total-driving, or choices-first priorities;
- save projects explicitly and export or print results;
- keep roster data on the local computer, with no accounts or telemetry.

## Project status

The manual, Google Maps, and downloadable offline-map workflows are implemented and tested. Native Windows and macOS packaging is now the remaining release phase.

There is no public installer yet. The first beta will be distributed through [GitHub Releases](https://github.com/nklisch/student-placement-planner/releases) as a normal Windows installer and macOS disk image. End users will not need Python or a terminal.

## Developer setup

Python 3.12 is pinned through `mise`:

```bash
mise install
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

Run the desktop application with:

```bash
.venv/bin/python -m placement_optimizer
```

Useful project pages:

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Google Maps setup](docs/GOOGLE_MAPS_SETUP.md)
- [Offline map packs](docs/MAP_PACKS.md)
- [Product and build requirements](docs/BUILD_INSTRUCTIONS.md)
- [Desktop interface specification](docs/UI_SPECIFICATION.md)
- [Building and publishing releases](docs/RELEASING.md)

## License

Student Placement Planner is available under the [MIT License](LICENSE).
