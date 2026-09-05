# Correctness and usability audit

**Date:** 5 September 2026

**Baseline:** `154011b`, version `0.1.0b4`

**Disposition:** historical findings at the baseline above; beta 5 remediation is recorded at the end of this document.

## Overall assessment

The basic application works, and the assignment engine performed well under testing. The biggest risks are **losing or changing the user's intended inputs before calculation**, and **making incomplete or old results look ready to use**. Those are correctness problems for a school user even when the solver faithfully solves the data it receives.

The five-step layout, optional rules, sample project, offline fallback, and concise built-in help are good foundations. However, spreadsheet import, Undo, address repair, and the path from download to a first real project need more work before this feels dependable to a non-technical user.

**17 findings: 5 high priority, 12 medium priority.** High means a plausible editing/import workflow can lose work or change the intended placement problem. Medium means a blocked or misleading workflow, unsafe handoff, or material accessibility problem. These are remediation priorities, not claims that every user encounters every issue.

### Fix first

1. Stop cross-page Undo from restoring unrelated data (**F-01**).
2. Stop CSV imports from silently dropping constraints or retaining invalid replacements as old valid values (**F-02**, **F-03**).
3. Make address/coordinate precedence explicit when an address changes (**F-04**).
4. Make identifier edits preserve the correct rule ownership (**F-05**).
5. Then repair import guidance, address recovery, and result export/print states.

## Scope and evidence

Reviewed the build requirements, implementation plan, UI specification, application draft/session and solve boundaries, optimization model, CSV/project persistence, travel/address workflow, UI implementation, built-in help, README, website source, online setup, offline map documentation, and release instructions. A separate read-only UI review checked table operations, rule dialogs, and recovery states.

Verification performed:

- Ran the existing suite: **188 passed in 8.52 seconds** with `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`.
- Ran **300 seeded small problems against an independent exhaustive enumeration**, combining minimum/maximum capacity, unavailable routes, eligibility, pins, prohibitions, together/apart groups, global/student commute limits, preferences, prior assignments, unplaced outcomes, and shuffled objective priorities. All matched.
- Launched the real desktop application on Linux; exercised empty state, sample loading, solving, results, travel-mode navigation, and help-related UI inspection.
- Ran synthetic, offscreen Qt/application probes for the editing/import/result defects below. These call actual application models and handlers; they are not claims of Windows/macOS installer testing.
- Captured only application windows containing synthetic/sample data. The screenshots are Linux offscreen Qt renders with settled deferred widget deletion, not photographs of a Windows/macOS release.

**Not verified here:** clean Windows/macOS installation, actual OS warning screens, native screen-reader behavior, live provider availability/quotas, a fresh large regional-map build, or physical printing. No real roster was sent to an online service. Passing tests and this audit do not establish that every mapping/packaging path is correct.

[Reproduction scripts and observations](audits/2026-09-05/evidence/observations.md) · [UI inventory](../.mockups/adoption-report.md)

## High-priority findings

### F-01 — Undo on one page can erase later work on another

**Verified twice independently.**

- **Reproduce:** edit a student's name; switch to Locations and change a capacity from 1 to 5; return to Students and Undo.
- **Observed:** the name is undone, but the location capacity also returns to 1. A second reproduction—paste a student, paste a location, Undo on Students—removed both.
- **Why it matters:** the interface and help promise table-scoped Undo. Users can unknowingly lose later rosters, constraints, or driving-time edits on another page.
- **Evidence:** `src/placement_optimizer/ui/tablemodels.py:35–43,80–83,334–338`; `src/placement_optimizer/application/draft.py:392–415`. Each table has its own history, but each snapshot restores all rosters, rules, and manual travel cells.
- **Suggested fix:** store operation-specific changes, including only the related rule/travel cleanup for a row deletion. Alternatively use one coherent global history and change the interaction contract; do not combine independent histories with whole-project restoration.
- **Regression:** interleave edits across all three grids and Rules, then Undo/Redo from each page without changing unrelated later work.

### F-02 — CSV headings copied from the UI silently lose minimum capacities and coordinates

**Verified.**

- **Reproduce:** import a location CSV with `Name,ID,Capacity,Minimum,Address,Coordinates` and a row containing minimum `1` and coordinates `51.5, -0.12`.
- **Observed:** “Imported 1 location.” The minimum and coordinates are empty, with no issues. The importer expects `minimum_capacity`/`min_capacity` and separate latitude/longitude fields instead.
- **Why it matters:** dropping the minimum removes a hard assignment constraint. Dropping coordinates changes how mapping will resolve that location. Using the application's own column names is a reasonable user action.
- **Evidence:** `src/placement_optimizer/projects/csv_io.py:90–143,237–260`; `src/placement_optimizer/ui/pages/roster.py:375–389,426–443`.
- **Suggested fix:** accept displayed headings and the combined coordinate format; show a preview or explicit warning for populated columns that will not be imported. Do not announce an unqualified successful import when data was ignored.
- **Regression:** import files using the displayed student/location headers and verify every populated field survives, especially Minimum.

### F-03 — Invalid travel imports leave old values ready to solve, with the wrong explanation

**Verified.**

- **Reproduce:** start with a valid 10-minute cell. Import `s1,l1,ten` under `student_id,location_id,driving_minutes`.
- **Observed:** the old `10` remains; readiness remains true. The transient message says “Filled 0 cells; 1 rows didn't match the current students and locations,” although both IDs matched. The invalid replacement text is not retained for repair.
- **Why it matters:** a user updating an existing grid can solve the previous data rather than the intended new inputs. The error points them at identifiers instead of the invalid time.
- **Evidence:** `src/placement_optimizer/ui/pages/travel.py:916–950`; `src/placement_optimizer/projects/csv_io.py:146–195`. Only valid `batch.items` are applied; invalid `draft_rows` and their individual reasons are unused.
- **Suggested fix:** retain matched invalid values as marked draft cells, or stage the import with a persistent row-level repair report. Distinguish bad numbers, duplicate pairs, and unknown IDs. Explicitly identify any old values retained.
- **Regression:** import mixed valid/invalid replacements into a complete grid; successful rows must survive, and failed replacements must remain visible rather than looking current.

### F-04 — Changing an address can still calculate from its old coordinates

**Verified behavior; a correctness/usability hazard caused by implicit precedence.**

- **Reproduce:** use a row with an address and coordinates, then replace its address with an address in another city and recalculate.
- **Observed:** address resolution uses the existing coordinates and makes no geocoder call for the changed address. Review shows the new entered address next to “Coordinates provided,” still using the old point. A probe changed the address but retained `51.5, -0.12`.
- **Why it matters:** coordinates legitimately override addresses, but there is no warning at the address edit. This is particularly easy to encounter after importing coordinates or correcting a match in the review dialog. “Recalculate” sounds like it will use the corrected address.
- **Evidence:** `src/placement_optimizer/application/draft.py:250–259,299–310`; `src/placement_optimizer/travel/service.py:123–141`; `src/placement_optimizer/ui/pages/travel.py:655–668`.
- **Suggested fix:** distinguish explicit coordinate overrides from address-derived values. When an address changes while coordinates exist, offer “Use the new address” versus “Keep these coordinates,” and clearly label which controls the route. Do not blindly discard intentional overrides.
- **Regression:** edit addresses after coordinate import and review correction; ensure the user cannot mistake retained coordinates for a newly resolved address.

### F-05 — A temporary duplicate ID can transfer another student's rules

**Verified.**

- **Reproduce:** Student A is `s1`, pinned to `l1`; Student B is `s2`, pinned to `l2`. Change A's ID to `s2`, then repair it to `s3`.
- **Observed:** the final IDs are valid (`s3`, `s2`), but both pins now belong to `s3`. B has lost their pin and A has conflicting pins.
- **Why it matters:** users are allowed to repair invalid cells in place. A temporary duplicate must not permanently change another student's rules. Similar raw-ID rewriting exists for locations.
- **Evidence:** `src/placement_optimizer/application/draft.py:250–259,299–310,774–819`.
- **Suggested fix:** preserve rule ownership through stable row identities, or validate and apply ID changes transactionally with an unambiguous old-to-new mapping. Never rewrite every matching reference after the identifiers have collided.
- **Regression:** duplicate-then-repair, ID swaps through paste, and whitespace edits must preserve each original row's rules.

## Medium-priority workflow and UI findings

### F-06 — Name-only CSV imports contradict the automatic-ID promise

**Verified.** Import `name` followed by two names. The parser generates `S001`/`S002`, but the UI discards those parsed items and inserts raw rows with empty IDs. It says “Imported 2 students,” while both rows have blocking “ID is required” errors.

**Evidence:** `src/placement_optimizer/ui/pages/roster.py:226–250,375–389,426–443`; `src/placement_optimizer/projects/csv_io.py:59–86`; `src/placement_optimizer/ui/help_content.py`, “Quick start” and “Student fields.”

**Suggested fix:** generate collision-free IDs for imported rows without IDs, just as manual entry does; preserve invalid raw fields without throwing away successful normalization. Determine the import summary from the resulting draft validation. Test imports into both empty and populated projects.

### F-07 — One missing/bad address aborts the review instead of producing repairable rows

**Verified missing-address path; source-confirmed failed-match behavior.** A student with neither address nor coordinates produces only “an address or latitude/longitude is required.” The error contains an item ID internally, but the worker reduces it to a string. Resolution stops on the first failed row, so the promised review list never appears and successful matches from that operation are not returned to the UI.

**Evidence:** `src/placement_optimizer/travel/service.py:123–165`; `src/placement_optimizer/ui/workers.py:59–74`; `src/placement_optimizer/ui/pages/travel.py:670–676`.

**Suggested fix:** preflight absent addresses/coordinates with named row links. Return successful and unresolved matches together, marking unresolved rows for correction. Preserve progress on retry, and use the structured item IDs to focus the right local row without putting them into provider requests or diagnostics.

### F-08 — The recommended travel CSV template exports no pairs when the grid is empty

**Verified.** With students and locations present but all times blank, Export times writes only a header. The guide recommends that export as the exact import format; the button tooltip explicitly says it includes blank cells. In fact, `if not raw: continue` omits every missing pair.

**Evidence:** `src/placement_optimizer/ui/pages/travel.py:178–179,972–1003`; `src/placement_optimizer/ui/help_content.py`, Travel times → Import and export.

**Suggested fix:** provide an explicit template export containing all student/location ID pairs and blank time fields. Keep blanks distinct from “no route.” Test complete, partial, and entirely blank grids.

### F-09 — Stale placements can be exported/printed without carrying their warning

**Verified.** Solve a valid project, change capacity to invalidate those assignments, then use File → Export or Print. Both remain enabled. The on-screen stale banner is absent from print output; CSV contains only assignments and has no stale notice. The operations correctly use the old result's roster snapshot, but recipients cannot tell it is old.

**Evidence:** `src/placement_optimizer/ui/mainwindow.py:785–810`; `src/placement_optimizer/ui/printing.py:35–82`; `src/placement_optimizer/ui/pages/results.py:236–237,259–266`. [Screenshot](audits/2026-09-05/evidence/stale-results.png).

**Suggested fix:** offer Update first or explicitly Export/print previous placements. Put a clear previous-result warning in print output; use a confirmation and/or distinctly labeled filename for CSV so its tabular format remains usable. Do not silently prohibit a deliberate old-result export.

### F-10 — Failed calculations still show success-shaped statistics and enable export

**Verified.** A capacity-infeasible result displays 0-minute statistics, a ready check beside Results, and enabled Export/Print actions despite containing no placements. Export produces a header-only assignment file. A non-null result object is being mistaken for a usable assignment.

**Evidence:** `src/placement_optimizer/ui/pages/results.py:236–237,251–301`; `src/placement_optimizer/ui/mainwindow.py`, `_update_steps`. [Screenshot](audits/2026-09-05/evidence/no-arrangement-results.png).

**Suggested fix:** distinguish an outcome/report object from an actual usable assignment. For no arrangement/time-out, show recovery guidance rather than zero-value achievement cards, mark Results as needing attention, and disable assignment export. If printable failure guidance is useful, label it separately.

### F-11 — A removal toast's Undo button can undo more than the removal

**Verified by the independent UI review; source checked.** Paste a student, remove them, then click the toast's Undo twice. The first click restores the student; the second undoes the earlier paste. The toast still describes the original removal.

**Evidence:** `src/placement_optimizer/ui/widgets.py:126–155`; `src/placement_optimizer/ui/pages/roster.py:186–198`.

**Suggested fix:** make toast recovery one-shot, dismiss it after use, and bind it to the specific deletion rather than whatever happens to be atop the undo stack. Test double-click and an intervening edit before clicking the toast.

### F-12 — One extra pasted travel column corrupts a valid destination cell

**Verified by the independent UI review; source checked.** Paste `5<Tab>6` into a one-student/one-location travel grid. The valid `5` becomes invalid `5, 6`. Extra rows, conversely, are silently dropped. Coordinate-column merging was reused for a numeric time grid where it has a different meaning.

**Evidence:** `src/placement_optimizer/ui/tablemodels.py:434–458`.

**Suggested fix:** keep all in-bounds values intact and report overflow dimensions, or preview the mismatch before applying the block. Never merge extra numbers into a valid time. Test oversized blocks in both directions.

### F-13 — Duplicate student-specific driving limits silently discard one entry

**Verified by the independent UI review; source checked.** Add two limit rows for the same student with 20 and 35 minutes. Both are editable, but accepting keeps only the first. “Add a student limit” always starts with the first student, making duplicates easy to create accidentally.

**Evidence:** `src/placement_optimizer/ui/pages/ruledialogs.py:363–381,442,466–469`.

**Suggested fix:** add the next unused student, prevent duplicates, or show a clear conflict before accepting. Do not silently choose a limit. Label whether student-specific limits override the general limit; currently they do.

### F-14 — Selecting no allowed locations creates an unexplained impossible rule

**Verified by the independent UI review; source checked.** Uncheck every location in Allowed locations only and accept. The card reads “Alice can only go to .” The rule means the student cannot be placed anywhere, but neither the dialog nor card explains that consequence.

**Evidence:** `src/placement_optimizer/ui/pages/ruledialogs.py:541–559`; `src/placement_optimizer/ui/pages/rules.py:42–46,264–265`.

**Suggested fix:** explicitly say “No locations allowed — this student cannot be placed,” with confirmation or inline attention. Preserve an intentional no-eligible-location state where partial placement is useful; do not simply forbid legitimate input.

## Documentation and accessibility findings

For this review, the brief was inferred from the approved product documents: **school staff; website/README/in-app reference; install and complete a placement without technical help; task-ordered guidance; plain, calm language; preserve privacy and manual/offline fallback explanations.** The reader paths below were derived from the actual documents, not an invented outline. Audience, structure, clarity, and accuracy were reviewed; no stylistic rewrite was attempted.

### F-15 — Installation guidance sends readers to instructions that do not exist

**Medium; material accuracy/audience finding.** The website FAQ says to follow the one-time confirmation instructions in the download section, but that section only warns that a confirmation might be needed. The README repeats the warning without telling a school user what to do. Maintainer signing instructions are not a user installation guide.

**Evidence:** `docs/index.html:130–152`; `README.md:15–19`; `docs/RELEASING.md`, Preview signing and operating-system warnings.

**Suggested fix:** provide version-appropriate Windows and macOS installation steps, the expected publisher/signature warning, how to verify the official download, and a route to school IT when policy prevents installation. Link directly from the download section. Validate the instructions on actual supported machines; do not promise a universal right-click workaround or instruct users to disable OS protections.

### F-16 — There is no complete user-facing handoff from download to saved, reusable work

**Medium; material audience/structure finding.** The README goes from release status straight to Developer setup. The site's “Interface guide” opens the UI implementation specification, including Qt class names and delivery phases. The built-in guide is pleasantly written, but lacks a Save/Open topic, the distinction between a project and result CSV, and concrete roster CSV examples/header definitions. Its “Import and export” guidance covers travel IDs without giving a complete starting artifact.

**Evidence:** `README.md:15–45`; `docs/index.html:165–170`; `src/placement_optimizer/ui/help_content.py`, all `HELP_TOPICS`. [Built-in guide screenshot](audits/2026-09-05/evidence/user-guide.png).

**Suggested fix:** add a short public user guide, link it instead of the implementation specification, and reuse the same material in Help. Cover:

1. Install, open, and run the sample before entering real data.
2. Create students/locations from downloadable CSV examples or a paste block, explaining column order, headers, automatic IDs, and append-versus-replace behavior.
3. Choose manual, offline, or online travel with clear prerequisites and cost/privacy implications.
4. Repair an invalid cell or address and tell when an old value is still being used.
5. Explain strict limits versus the commute target and ranked choices versus hard rules. In particular, individual limits override the general limit, and Choices first optimizes rank penalties rather than guaranteeing everyone a listed choice.
6. Save a `.spp` project explicitly, reopen it, and distinguish that from sharing a result CSV or printout. Explain that there is no automatic roster save.

The default sample yields **0 of 2** students receiving a choice while saying every rule is satisfied. That is consistent with the fair-commute objective, not a solver defect, but a short explanation or a “try Choices first” hint would prevent the sample from teaching the wrong lesson.

**Documentation verdict:** two standalone material document-collection findings above, plus copy/behavior mismatches attached to F-06 and F-08 rather than counted twice. Existing strengths to preserve are the clear five-step framing, short field explanations, optional walkthrough, and explicit online data disclosure.

### F-17 — Primary action text fails normal-text contrast in dark mode

**Medium; measured accessibility finding.** Dark mode draws white 11-point primary-button text on `#5E9C89`, a contrast ratio of **3.19:1**, below the usual 4.5:1 normal-text benchmark. This includes the main Find placements action. The light-mode equivalent measures 5.91:1.

**Evidence:** `src/placement_optimizer/ui/theme.py:42–43,170–174`. Calculation uses standard sRGB relative luminance. This is a color-token finding, not a claim of a completed screen-reader audit.

**Suggested fix:** choose a darker button fill or dark foreground for the lighter dark-mode accent, and check normal, hover, pressed, selected, and focus states in both themes. Add contrast assertions for the actual foreground/background pairs.

## Usability improvements worth pairing with the fixes

These are recommendations, not additional confirmed defects:

- **Put essential travel syntax in view:** “Minutes · x = no route · blank = not entered.” A tooltip/help page should not be necessary to learn the cell units or the difference between blank and unavailable.
- **Make repair persistent:** row-level import results and a short “needs attention” summary are more useful than a six-second toast when many rows need checking.
- **Give the grid more space at small window sizes:** at the 960×600 minimum, mode descriptions occupy a large portion of the page and only about three full student rows fit. Consider collapsing the chosen-mode description after selection, while keeping switching easy. [Screenshot](audits/2026-09-05/evidence/manual-minimum-window.png).
- **Identify the travel source near ready data:** make it clear whether times are manual, retained from an earlier calculation, or freshly calculated by a particular provider. This need not become a technical provenance screen.
- **Make “no arrangement fits” more specific:** the current capacity-shortfall explanation is useful; conflicting pins/groups/eligibility generally receive a broad list. Where cheap to determine, name the affected students, locations, or rules and offer direct jumps.

## Lower-confidence risks and exclusions

- **Unexpected solver exceptions lack a recovery boundary:** `SolveWorker.run` directly calls `solve_project` without converting unexpected failures into a UI outcome (`ui/workers.py:135–137`). Source-confirmed gap, but not reproduced through an ordinary supported input in this audit; not counted as a confirmed workflow defect.
- **Travel freshness is coarse:** name/capacity edits bump the travel-input version, and Undo of a manual time can leave a previously calculated matrix marked stale. The probes reproduce unnecessary invalidation, but a safe fix needs a deliberate dependency model. Do not solve this by allowing genuinely stale routes through.
- **Displaying a failed address locally was not counted as a privacy leak.** A review candidate flagged raw address text on the Travel page. That page already displays roster data, and identifying the failed address can help the user. The important boundary is not sending names/IDs/rules to providers or including addresses/keys in shareable diagnostics. No new evidence here establishes a leak across that boundary.
- **Removing the only allowed location currently removes the empty eligibility rule.** The probe records this, but the approved UI specification explicitly calls for empty-rule cleanup. Treat any change as a product decision about confirmation and retained intent, not a proven deviation from the current specification.

## Recommended delivery order

1. **Protect input intent:** F-01–F-05, with cross-page and round-trip regression tests.
2. **Repair first-use and repair workflows:** F-06–F-08, F-11–F-14; make CSV failures persistent and actionable.
3. **Make sharing trustworthy:** F-09–F-10; label previous results and never export an empty failure as placements.
4. **Finish the user handoff:** F-15–F-17 and the short in-page hints above. Verify on Windows/macOS with a person starting from the download page and a small, imperfect spreadsheet.

The sections above preserve the original audit. The subsequent user request authorized implementation, a final review, and release; see the remediation record below.

## Beta 5 remediation record

All 17 findings have implementation and focused verification. The final independent
review has been adjudicated below. Native release gates remain pending.

| Finding | Resolution | Focused coverage |
| --- | --- | --- |
| F-01 | One chronological data Undo/Redo history, including rules and calculated travel; page changes never select an old independent history. | `test_audit_edit_history.py`, `test_rules_page.py` |
| F-02 | Displayed Minimum/Coordinates headers accepted; conflicting coordinates retained invalid; populated unknown fields have compact persistent notes and scrollable details. | `test_files_and_import.py`, `test_project_workflow.py` |
| F-03 | Invalid replacement cells block readiness and retain original input in a persistent report; seconds remain correctly converted in the minutes grid. | `test_travel_placeholders.py`, `test_audit_edit_history.py` |
| F-04 | Address edits clear prior coordinates unless the user explicitly retains them; review labels overrides and preserves unedited provider precision. | `test_audit_draft_recovery.py`, `test_audit_edit_history.py`, `test_address_review.py` |
| F-05 | Last unambiguous rule-reference identity survives invalid IDs and Save/Open; swaps rewrite all references atomically. | `test_audit_draft_recovery.py` |
| F-06 | Missing import IDs generated without collisions; usable-row counts reflect resulting draft validation. | `test_files_and_import.py`, `test_project_workflow.py` |
| F-07 | Review returns unresolved and successful rows together, offers local address repair, and reuses unchanged matches on retry. | `test_travel_service.py`, `test_address_review.py`, `test_travel_placeholders.py`, `test_audit_edit_history.py` |
| F-08 | Travel export includes every pair and leaves unfinished times blank. | `test_travel_placeholders.py` |
| F-09 | Explicit previous-result sharing choice; previous-result print warning and distinct suggested CSV filename. | `test_audit_sharing.py`, `test_results.py` |
| F-10 | Failed results show recovery rather than achievement cards, cannot export placements, and mark Results as needing attention. | `test_audit_sharing.py`, `test_results.py` |
| F-11 | One-shot toast recovery is bound to its operation and cannot undo an intervening edit. | `test_audit_widgets.py`, `test_audit_edit_history.py` |
| F-12 | In-bounds time cells remain intact; extra pasted cells are counted and reported. | `test_audit_edit_history.py` |
| F-13 | Add-limit chooses an unused student; duplicate acceptance is rejected explicitly; override semantics are explained. | `test_rules_page.py` |
| F-14 | Empty eligibility clearly states that the student cannot be placed and requires deliberate confirmation. | `test_rules_page.py` |
| F-15 | Actual conditional Windows/macOS installation instructions, official verification links, and managed-device IT fallback. | `docs/INSTALLATION.md`; source/link review (native warning interaction remains untested locally) |
| F-16 | Public/built-in user guidance, CSV examples, project Save/Open versus result sharing, choices/limits explained. | `test_help.py`; `docs/USER_GUIDE.md` |
| F-17 | Theme-specific primary text colors and contrast coverage for normal/pressed/disabled/selected pairs. | `test_audit_widgets.py` |

Additional bounded corrections: worker error boundaries; provider labels in troubleshooting;
rule-choice delegates now display names while storing IDs; name/capacity-only changes no
longer force routing; travel headings still refresh without disrupting the selected cell.
The travel legend stays visible, descriptions can be collapsed under About travel options,
and failed-result layouts retain compact banners.

Verification before final review: **239 tests passed**, complete Ruff lint/format gates
passed, **300 mixed-rule oracle comparisons passed**, local OR-Tools and offline-builder
self-tests passed, and user documentation links resolved. The screenshots below show the
actual corrected Qt layouts (synthetic/sample data, offscreen Linux), not target-platform
installer verification:

- [Beta 5 travel grid at minimum size](audits/2026-09-05/evidence/beta5-manual-minimum-window.png)
- [Beta 5 failed-result recovery](audits/2026-09-05/evidence/beta5-no-arrangement-results.png)

### Final review and parent adjudication

The authorized single Astra high review reported three high-severity issues and one
medium-severity issue. The parent accepted all four based on concrete reproductions:

1. **Ignored rows taking rule ownership:** placeholder rows now have no reference
   identity. Activating or deleting them cannot steal another row's pins. Student and
   location cases cover both deletion and duplicate-ID repair.
2. **Collapsed limits being deleted:** disclosure now affects visibility only. Retained
   rows are always returned and validated; hidden duplicate rows reopen for repair.
3. **Discard reversing another import:** roster and travel import application share a
   FIFO disposition queue. Modal reports finish before another import is applied, and
   queued completions retain the original session even after their worker cleans up.
4. **Sharing a replaced result:** export and print capture the selected immutable
   outcome/project before any confirmation or file dialog processes other completions.

`tests/ui/test_final_review_regressions.py` pins these repairs. The original review's
real Qt placeholder, modal-import, and running-solver/export reproductions were also
rerun successfully. A related parent check now rejects address reviews invalidated by
roster or region changes during the modal dialog instead of calculating an old positional
matrix (`test_review_rechecks_roster_after_modal_dialog`).

Post-adjudication gates: **249 tests passed**, Ruff lint and formatting passed, **300
independent oracle comparisons passed**, and optimization/offline-builder entrypoint
self-tests passed. Both print layouts produced PDFs; extracted previous-result output
contains its warning. No additional independent review round was commissioned. Native
installer builds/smoke checks and publication are the remaining release gates; this record
does not claim physical printing or native accessibility/installation-warning testing.
