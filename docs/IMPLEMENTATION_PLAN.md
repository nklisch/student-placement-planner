# Student Placement Planner — Implementation Plan

## 1. Product outcome

Deliver a polished local desktop utility for Windows and macOS that lets a non-technical school user:

1. Enter students and placement locations manually, paste from Excel, or import CSV.
2. Configure capacities, eligibility, preferences, commute limits, and simple group rules.
3. Obtain driving times through an offline regional map pack, an explicit online provider, or a manually supplied matrix.
4. Choose a straightforward optimization preset and solve up to 100 students.
5. Review and export a clear assignment table and summary.

The normal workflow must not expose solver jargon, map infrastructure, or provenance machinery. Troubleshooting details exist only to help diagnose a failed operation.

## 2. Architecture

```text
PySide6 desktop UI
        │ typed application commands/results
Application services
  ├── input validation + project session
  ├── travel-data orchestration
  ├── optimization orchestration
  └── export + user-facing recovery states
        │
Core boundaries
  ├── domain/          pure student, location, rule, and result types
  ├── optimization/    OR-Tools model + independent reference solver
  ├── travel/          manual, online, and offline provider protocols
  ├── projects/        explicit project open/save and CSV import/export
  └── diagnostics/     sanitized technical details, never roster contents/keys
        │
Native engines and local data
  ├── OR-Tools
  ├── Valhalla regional routing tiles
  └── SQLite regional address index
```

The UI never calls map providers or the solver directly. Application services return typed success, needs-attention, infeasible, cancelled, or unavailable states so routine failures do not escape as crashes.

## 3. Optimization design

### Variables and hard rules

For each eligible student/location pair, binary `x[s,l]` indicates assignment.

- Exactly one location per student unless the user explicitly enables an unassigned outcome.
- Location minimum/maximum capacities.
- Ineligible and prohibited pairs have no decision variable.
- Pinned assignments are fixed.
- Commute limits remove over-limit pairs.
- Together groups share a location.
- Separate groups may not share a location.

### Ordered objectives

Objectives are optimized one at a time; each proven result is fixed before the next objective. Initial supported dimensions:

- Smallest longest driving time.
- Fewest students over a configurable target.
- Smallest total driving time.
- Best ranked-choice outcome.
- Least disruption from a prior assignment, when supplied.

Presets:

- **Fair commute:** longest time → threshold count → total time → choices.
- **Lowest total:** total time → longest time → choices.
- **Choices first:** choice penalty → longest time → total time.

The application clearly distinguishes an optimal result, a usable result not yet proven optimal, and an infeasible model. At this scale, the expected path is a proven result in seconds or less.

### Correctness testing

- Hand-calculated examples for every constraint and objective.
- Exhaustive enumeration of small random problems against the solver result.
- Property tests: exact-one assignment, capacities, eligibility, group behavior, total calculations, determinism.
- The independent min-cost-flow solver cross-checks simple OR-Tools cases.
- Infeasibility fixtures verify actionable explanations.

## 4. Travel-data design

All modes produce the same rectangular matrix of integer driving seconds and road metres. `None` means no route; it is never replaced silently.

### Manual matrix

First vertical slice and permanent privacy fallback. Users can paste or import `(student_id, location_id, minutes, distance)` rows and can edit cells. It requires every pair, with an explicit no-route value allowed.

### Online provider

Addresses are geocoded and coordinates are sent for matrix routing. Provider request types contain only address or coordinate values. Requests are batched, cancellation-aware, and errors preserve the project session. The initial adapter is Google Maps because it is familiar and requested; the provider boundary remains vendor-neutral.

### Offline regional pack

A downloadable pack contains:

- Valhalla routing tiles built for the application’s pinned engine version.
- A SQLite FTS address index built from the same OpenStreetMap extract.
- Region name, data date, engine compatibility version, size, and corruption checksum.

The application downloads prepared packs; users never import raw OSM data. Missing coverage offers manual coordinates or online lookup. Incompatible/corrupt packs disable offline routing for that region without preventing application startup.

## 5. Desktop interaction design

Normal flow:

1. **Students:** spreadsheet table with add-row, Excel paste, and CSV import.
2. **Locations:** table with capacity and the same input conveniences.
3. **Rules:** simple optional controls; advanced constraints remain collapsed until used.
4. **Travel:** choose Offline map, Online maps, or Manual times, with one-sentence data disclosure.
5. **Review addresses:** only unresolved or ambiguous rows demand attention.
6. **Optimize:** select a preset and run in a cancellable worker.
7. **Results:** assignment table, capacity panel, longest/average commute, warnings, CSV export, and print.

Inputs survive failed geocoding, routing, solving, or export operations. Error messages describe the next useful action rather than presenting stack traces or provider payloads.

UI design and implementation follow the restricted model roles in `docs/BUILD_INSTRUCTIONS.md`.

## 6. Delivery phases and gates

### Phase A — Foundation validation

- [x] Pure typed domain and independent exact capacity solver.
- [x] Provider-neutral travel interfaces.
- [x] Initial manual, OSRM/Nominatim development, and Google adapters.
- [x] Install development dependencies in a supported Python 3.12 environment.
- [x] Run and repair foundation tests.
- [x] Replace provisional stack metadata with desktop dependencies and module layout.

**Gate:** all foundation tests pass; imports are lazy enough that an unavailable optional map engine cannot prevent core/manual use.

### Phase B — Backend vertical slice

- [x] Define application request/result/error-state types.
- [x] Add OR-Tools advanced assignment model and ordered objectives.
- [x] Add constraints: eligibility, preferences, commute limits, pins/forbids, together/separate.
- [x] Add manual table/matrix validation and CSV import/export.
- [x] Add in-memory project session and explicit project save/open.
- [x] Produce a result summary/export through an application service without any UI.
- [x] Add exhaustive/property/integration tests.

**Gate:** a complete manual-input problem can be solved and exported through typed application APIs; all backend tests pass.

**Large-seam review 1:** Sol xhigh, read-only. Parent fixes findings inline before UI work proceeds. **Completed:** no critical issues; strict project decoding, editable import drafts, keyed-exception redaction, provider validation, and permanent regression tests were added from the review.

### Phase C — UI design seam

- [x] Parent provides K3 only the stable UI-facing types, workflows, and constraints.
- [x] K3 produces desktop utility mockups and interaction states—no backend work.
- [x] GLM 5.3 reviews the design for taste, ease, practicality, and cleanliness.
- [x] Parent resolves feedback into a concise UI specification.

**Gate:** agreed screens, component states, keyboard/paste behavior, empty/loading/error states, and visual direction are recorded before UI implementation.

### Phase D — Desktop UI implementation

- [x] Kimi K3 implements the agreed PySide6 UI against stable application interfaces only.
- [x] Parent integrates and fixes backend/interface issues inline.
- [x] Add responsive worker execution, cancellation, manual tables, results, exports, and settings.
- [x] Terra reviews UI implementation only; parent/K3 apply scoped fixes.
- [x] Add pytest-qt tests and manual accessibility/keyboard checks.

**Gate:** the full manual-matrix workflow works in the desktop application and does not require a terminal.

### Phase E — Mapping modes

- [x] Harden Google batching, cancellation, address review, and privacy-shaped requests.
- [x] Implement pyvalhalla matrix adapter behind lazy optional loading.
- [x] Define/build a small test regional pack and SQLite address index.
- [x] Add pack manager with resumable download, progress, compatibility check, retry, and last-working-pack retention.
- [x] Add offline geocoding review and coordinate override.
- [x] Test offline mode with network access blocked.

**Gate:** online, offline-pack, and manual modes all feed the same solver workflow; losing one mode does not break the others or startup.

### Phase F — Packaging and release candidate

- [ ] Bundle Windows and macOS applications with pinned runtimes/dependencies.
- [ ] Create platform installer, signing, and macOS notarization workflows.
- [ ] Test clean-machine install, first launch, map-pack setup, upgrade, and uninstall.
- [ ] Add sample data and concise user documentation.
- [ ] Run full unit, property, integration, UI, privacy, and packaging tests.
- [ ] Exercise provider outages, corrupt input/project, missing map pack, cancellation, and infeasibility.

**Large-seam review 2:** Sol xhigh reviews the release candidate. Parent fixes findings inline.

**Gate:** clean Windows/macOS users can install, complete a sample run, export results, and recover from expected failures without technical help.

## 7. Performance budgets

These are user-experience targets, not premature microbenchmarks:

- Table editing/paste feedback: visually immediate; validation does not block typing.
- Basic solve at 100 students: normally under 1 second.
- Advanced solve at 100 students: normally under 5 seconds; remains cancellable.
- Manual CSV import/export: under 1 second at supported scale.
- Cached/local matrix retrieval: progress shown if over 500 ms.
- UI thread: never performs solver, provider, map-pack, or bulk-parse work.

## 8. Deliberately deferred

- Cloud sync, accounts, collaboration, telemetry, or centralized administration.
- Automatic background roster persistence.
- Public transit scheduling or live-traffic optimization.
- Rich GIS map editing.
- Arbitrary user-authored mathematical expressions or raw objective weights.
- Heavy audit/provenance workflows.
- Speculative operating-system/filesystem hardening.
- Scale beyond the supported school-sized workflow until measured demand exists.
