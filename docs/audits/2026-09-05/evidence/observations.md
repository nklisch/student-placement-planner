# Audit evidence and replay

Baseline: commit `154011b`, Student Placement Planner `0.1.0b4`, 5 September 2026.

Environment: Linux, Python 3.12.14, PySide6 6.11.2, OR-Tools 9.15.6755, pytest 9.1.1, Hypothesis 6.165.10. Qt probes use the offscreen platform; the separate visible desktop walkthrough used the local Linux desktop.

These are **audit probes, not permanent regression tests or application fixes**. They deliberately inspect implementation-level model/handler interfaces to reproduce user-visible states. Their printed bug observations should change after remediation. The solver oracle, in contrast, asserts that the produced placements are valid and have the best enumerated objective score.

All probe data is synthetic. The scripts do not call online providers or save a real roster. `MainWindow` construction uses normal local UI settings/map-store initialization; temporary CSV files are removed automatically. Run from the repository root in its development environment:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
QT_QPA_PLATFORM=offscreen .venv/bin/python docs/audits/2026-09-05/evidence/workflow_probes.py
QT_QPA_PLATFORM=offscreen .venv/bin/python docs/audits/2026-09-05/evidence/import_probes.py
.venv/bin/python docs/audits/2026-09-05/evidence/solver_oracle.py
```

## Existing suite

```text
188 passed in 8.52s
```

## Workflow probes

```text
UNDO_OTHER_PAGE {"capacity_after_undo_student_name": "1", "expected_capacity": "5"}
UNDO_TRAVEL_VALIDITY {"restored_cell": "10", "calculated_still_stale": true}
ADDRESS_CHANGE {"entered": "Entirely different city", "coordinate": "Coordinate(latitude=51.5, longitude=-0.12)", "geocoder_calls": []}
MANUAL_FALLBACK_STALE {"mode": "manual", "calculated_stale": true, "ready": true, "duration": [[600]]}
INVALID_TRAVEL_IMPORT {"cell": "10", "ready": true, "feedback": ["Filled 0 cells; 1 rows didn't match the current students and locations."]}
EMPTY_TEMPLATE_EXPORT 'student_id,location_id,driving_minutes,distance_km\n'
STALE_RESULT_EXPORT {"stale": true, "export_enabled": true, "print_stale_warning": false}
FAILED_RESULT_EXPORT {"outcome": "infeasible", "placements": 0, "export_enabled": true, "stats_longest": false}
MISSING_ADDRESS {"ui_receives": "an address or latitude/longitude is required", "row_ids_discarded_by_worker": ["s1"]}
DELETE_ONLY_ELIGIBLE_LOCATION {"remaining_rule": "()", "new_assignment": "l2"}
```

`stats_longest` is the `isHidden()` result: `false` means the zero-valued statistics card is not hidden. The stale-print probe checks the generated document for the on-screen stale-warning phrase; source inspection confirms the print builder has no session-staleness input at all.

Not every observation is counted as a defect. The main report explicitly separates travel invalidation and specification-approved empty-rule cleanup from the confirmed findings. Retained manual times on a mode switch can be intentional; the issue is making their meaning clear, not automatically deleting them.

## Import and identifier probes

```text
NAME_ONLY_CSV {"ids": ["", ""], "parser_ids": ["S001", "S002"], "notes": ["Imported 2 students."], "issues": ["ID is required", "ID is required"]}
VISIBLE_COLUMN_NAMES_CSV {"row": "LocationDraft(key='', name='Site A', id='l1', capacity='2', minimum_capacity='', address='', coordinates='', is_placeholder=False)", "issues": [], "notes": ["Imported 1 location."]}
REPAIRED_DUPLICATE_ID {"student_ids": ["s3", "s2"], "pins": [["s3", "l1"], ["s3", "l2"]]}
```

## Independent solver oracle

```text
300 seeded combined-constraint/objective problems matched independent exhaustive enumeration.
```

Seed: `20260905`. Each case has 1–5 students and 1–3 locations, random unavailable routes/capacities, optional hard rules, and all supported optimization dimensions in a shuffled order. Enumeration checks allowed assignments and computes the ordered objective tuple separately from the production model. It includes the implementation's intended per-student-limit override and shared-unplaced semantics for together groups. It does not prove correctness outside the sampled domain or under native solver failures/timeouts.

## Independent UI review probes

The separate UI-only review reported these offscreen reproductions; the parent checked the implicated source:

- Paste student → remove student → click toast Undo twice: the second click undoes the earlier paste.
- One-cell travel grid → paste `5\t6`: cell becomes `5, 6`.
- Add two student limit rows for the same ID → set 20 and 35 minutes → accept: only the first survives.
- Uncheck every allowed location → accept: rule card reads `Alice can only go to .` and the student has no eligible location.

Keyboard spot checks found sensible initial focus and working Esc in Group, Commute, and Ranked choices dialogs; Enter committed a ranked-choice combo without prematurely accepting its dialog. This is not a full keyboard or assistive-technology certification.

## Contrast calculation

Using sRGB linearization (`c / 12.92` when `c <= 0.04045`, otherwise `((c + 0.055) / 1.055) ** 2.4`), relative luminance weights `0.2126, 0.7152, 0.0722`, and `(L_light + 0.05) / (L_dark + 0.05)`:

- White on dark-mode accent `#5E9C89`: **3.1854:1**.
- White on light-mode accent `#2F6F5E`: **5.9051:1**.

## Screenshots

Captured with the real Qt widgets, light theme, synthetic/sample data, at 1120×720 except the explicitly named 960×600 minimum-window capture. Deferred-delete events were processed before capture so replaced capacity widgets do not appear over one another. No full-desktop images were retained.

- [Successful sample result](sample-results.png)
- [Stale result with export still enabled](stale-results.png)
- [No arrangement with zero statistics and export still enabled](no-arrangement-results.png)
- [Travel grid at the minimum window size](manual-minimum-window.png)
- [Built-in user guide](user-guide.png)

Linux emitted a desktop-portal app-registration warning on the visible launch. The app still opened and completed the sample workflow; this was not treated as a supported-platform defect. Offscreen Qt's unsupported-raise notice during help capture was likewise an environment limitation, not a claimed application failure.
