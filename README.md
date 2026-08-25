# Student Placement Planner

Student Placement Planner is a local-first desktop utility for assigning students to placement locations while respecting capacity, choices, eligibility, group rules, and driving-time limits.

It is designed as a calm, spreadsheet-friendly tool for school staff:

- type directly into editable tables, paste from a spreadsheet, or import CSV files;
- compare placements by road driving time;
- choose fair-commute, lowest-total-driving, or choices-first priorities;
- save projects explicitly and export or print results;
- keep roster data on the local computer, with no accounts or telemetry.

## Project status

The manual travel-time workflow and desktop interface are complete and tested. Google Maps integration, downloadable offline map packs, and native Windows/macOS installers are under active development.

The first public beta will be distributed through [GitHub Releases](https://github.com/nklisch/student-placement-planner/releases) as a normal Windows installer and signed macOS disk image. End users will not need Python or a terminal.

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

See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) for the staged build plan and [`docs/BUILD_INSTRUCTIONS.md`](docs/BUILD_INSTRUCTIONS.md) for durable product requirements.

## License

Student Placement Planner is available under the [MIT License](LICENSE).
