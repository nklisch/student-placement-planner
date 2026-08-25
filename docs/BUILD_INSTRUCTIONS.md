# Durable Build Instructions

## Purpose

Build a simple, attractive, local desktop utility that assigns up to 100 students to real-world placement locations. It must respect capacities and configured constraints while optimizing estimated driving time. The data is short-lived working data, and this application is not a system of record.

These instructions are durable for the current build. If a later decision changes them, update this file and `docs/IMPLEMENTATION_PLAN.md` in the same change.

## Product priorities, in order

1. **Useful and mathematically correct core results.** Never silently violate an assignment constraint or substitute straight-line distance for road travel.
2. **Smooth experience for non-technical users.** A normal signed Windows or macOS installer; no terminal, Python setup, Docker, or local-server administration.
3. **Robust recovery.** Preserve entered work, keep valid rows when some input is bad, offer retry or a practical fallback, and avoid turning recoverable provider or file problems into application crashes.
4. **Clear, pleasant utility UI.** Spreadsheet-like manual entry, Excel paste, CSV import/export, concise results, and advanced details kept out of the normal path.
5. **Local-first privacy.** No accounts, telemetry, or cloud database. Online mapping is explicit and transmits only the address/coordinate data needed for that operation—never student names, IDs, choices, constraints, or groups.
6. **Maintainable implementation.** Cohesive typed modules, deterministic behavior, tests around boundaries, and comments explaining non-obvious decisions.

## Scope decisions

- Desktop targets: Windows and macOS.
- Normal run size: no more than 100 students; location counts remain configurable.
- Input methods: manual tables, multi-cell paste, CSV, optional coordinates, and optional manual travel-time matrix.
- Travel metric: stable estimated driving time is primary; road distance is reported.
- Map modes:
  - Manual travel matrix: fully offline, no map dependency.
  - Offline regional map: raw extracts downloaded directly from Geofabrik and prepared locally, with optional ready-made packs; local geocoding and Valhalla road routing.
  - Online maps: no-key shared Nominatim/OSRM for occasional use, or explicit openrouteservice/Google key configuration.
- Constraints in the intended core: exact-one assignment, location capacity, eligibility, ranked choices, pinned/prohibited assignments, commute limits, and together/separate groups.
- Optimization: ordered objectives rather than an unexplained weighted score. Presets cover fair commute and lowest total travel; advanced users may reorder supported objectives or apply bounds.
- Main result: assignment, travel time/distance, preference outcome, capacity use, longest/average commute, and actionable warnings. Solver/map diagnostics live behind an optional troubleshooting view. Do not build a heavy provenance or audit product.
- Data persistence: work in memory by default. Saving a local project is explicit; CSV export is always available. Do not create accounts or remote synchronization.

## Reliability and failure-handling policy

Treat expected failures as states in the workflow, not uncaught exceptions:

- Invalid imported rows remain visible and editable; valid rows survive.
- Ambiguous or failed geocodes are marked for review; never invent `(0, 0)` or silently choose a distant result.
- An unavailable online provider preserves all input and offers retry, provider switch, coordinates, or manual matrix entry.
- A missing or incompatible offline map pack disables only that mode. The application still opens and manual/online modes remain usable.
- Corrupt optional settings fall back to documented defaults. A corrupt project file must not prevent a new blank project from opening.
- Infeasible assignments return an actionable result explaining capacity or constraint conflicts; they are not application crashes.
- Long operations run away from the UI thread, expose progress where meaningful, and can be cancelled safely.
- Prefer a degraded feature over refusing to start the application.

Reasonable defaults are preferred when they cannot change assignment correctness. Never use a fallback that alters the meaning of travel data without clearly asking the user—for example, do not replace missing road routes with straight-line estimates.

## Security scope and threat model

This is a local utility run by the user against their own files and map configuration. Protect against the realistic risks:

- Accidental network disclosure: typed provider requests must structurally exclude names, IDs, choices, and group data.
- Secret leakage: never include API keys in logs, exceptions, exports, or UI diagnostics.
- Accidental data persistence: do not autosave student data to hidden or remote stores; make project saving explicit.
- Corrupt downloads: map-pack checksums protect against incomplete/corrupt downloads and permit retry while retaining the last working pack.

Do **not** add speculative file-identity checks, filesystem allowlists, mount-type checks, startup refusals, mandatory encryption/keyring availability, or similar server-style guards. A guard that can refuse startup must name a concrete attack and the protection it provides, and must include a usable degraded path or override. Local project files are disposable working data; operating-system account controls and disk encryption are outside this tool's scope.

## Technology direction

- Python 3.12 application.
- PySide6 / Qt 6 native desktop UI.
- OR-Tools native solver bindings for advanced constraints and proof status.
- A small independent exact assignment implementation retained as a reference oracle for tests.
- pyvalhalla for in-process offline road routing and local tile preparation; installed regions contain compatible routing tiles and a SQLite address index built from a direct Geofabrik extract or ready-made pack.
- SQLite/FTS for offline address lookup and lightweight local settings where appropriate.
- httpx for opt-in online map requests.
- PyInstaller initially for bundled executables, with platform-native signed installer/notarization steps.
- Avoid pandas and a browser/server stack unless a demonstrated requirement earns them.

The performance-critical work occurs in native OR-Tools, Qt, SQLite, and Valhalla code. Python coordinates the workflow. For 100 students this is comfortably within the performance budget; optimize measured bottlenecks rather than rewriting the application in a lower-level language pre-emptively.

## Model responsibilities and review cadence

Subagents remain depth one and are used only at a few large seams. Do not generate constant review churn.

### Parent agent

The parent agent performs all backend and complex implementation inline in this repository: domain modeling, optimization, provider logic, offline map integration, storage/import/export, packaging, error recovery, integration, and tests.

### UI-only agents

These model restrictions are explicit:

- **Kimi K3 (`kimi-coding/k3`)**: UI mockups, interaction design, and implementation of the approved PySide6 UI using parent-authored application interfaces. It must not design or change backend/solver behavior.
- **GLM 5.3 (`zai/glm-5.3`)**: review UI designs only for taste, human ease of use, practicality, and cleanliness.
- **Terra (`openai-codex/gpt-5.6-terra`)**: review UI implementation only.
- **Luna (`openai-codex/gpt-5.6-luna`)**: not used for this build unless the user changes the role assignment again.

Do not use K3 or GLM 5.3 for backend, architecture, optimization, provider, or security work. K3 may add UI-focused tests as part of UI implementation. Do not use Terra outside UI review.

### Broad implementation reviews

Use **Sol xhigh (`openai-codex/gpt-5.6-sol`)** sparingly at major implementation seams:

1. After the backend vertical slice is complete and tested: manual input/matrix through advanced solve and result export.
2. At release-candidate integration: desktop UI, online/offline providers, recovery behavior, packaging, and complete tests.

A third Sol review is warranted only after a genuinely large architectural change. Reviews are read-only and focus on correctness, maintainability, integration risks, and accidental overengineering. The parent agent applies fixes inline.

## Working rules

- Keep the task tracker synchronized with `docs/IMPLEMENTATION_PLAN.md`.
- Work one active implementation task at a time.
- Test immediately at each boundary; do not call a phase complete with failing or missing relevant tests.
- Use background jobs for dependency installation, full test suites, builds, and packaging.
- Keep user-visible language plain and actionable.
- Do not commit AI attribution or co-author trailers.
