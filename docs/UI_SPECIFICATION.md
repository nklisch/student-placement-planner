# Desktop UI Specification

Status: **approved for implementation** after Kimi K3 design and GLM 5.3 design review.

This specification is the source of truth for the PySide6 interface. It applies the accepted review changes and intentionally avoids additional design rounds unless implementation reveals a concrete usability problem.

## 1. Product character

A calm, attractive, spreadsheet-first desktop utility. It should feel like a small built-in school administration tool, not enterprise software and not a technical optimization console.

Principles:

1. One visible path from roster to placement result.
2. Guided steps, but never a blocking wizard.
3. Typing, Excel paste, and CSV import are equal first-class inputs.
4. Expected failures appear inline, preserve work, and offer the next useful action.
5. Optional power is discoverable but folded away.
6. Native, quiet visual treatment with no branding chrome.
7. Normal screens avoid the words solver, matrix, geocode, optimal, and infeasible.

## 2. Application shell

Default window: 1120 × 720. Minimum: 960 × 600.

- Standard menu bar.
- 200-point left navigation rail.
- Resizable central content stack.
- 56-point persistent footer.
- Window title: `<Project name> — Student Placement Planner`.
- Platform-standard modified indicator when unsaved work exists.

### Five navigation steps

1. Students
2. Locations
3. Rules
4. Travel times
5. Results

Each item shows its number, label, and a text/icon status that is not color-only:

- `○` not started
- `●` has content
- `✓` ready
- `!` needs attention
- Rules shows a numeric rule count instead of readiness.

Users may move between steps at any time. Results is visually quiet before the first run and displays `Find placements to see results here.` when selected.

### Persistent footer

Exactly three concepts:

1. **Readiness button** — `Ready to find placements` or `2 steps need attention`.
2. **Goal combo** — `Fair commute (recommended)`, `Lowest total driving`, `Choices first`, `More options…`; after custom ordering it reads `Custom`.
3. **Primary button** — `Find placements`, changing to `Update placements` when prior results are stale.

The readiness button opens a plain `QMenu` of jump actions, for example `Travel times — 26 cells empty`. If exactly one step needs attention, it may jump directly to it.

The run button always acts or explains. If ready, it starts and moves to Results. If not ready, it opens the readiness menu. It never silently does nothing.

### Menus

- **File:** New, Open…, Save, Save As…, Export results…, Print…, Load sample data, Quit.
- **Edit:** Undo, Redo, Copy, Paste, Add row, Delete rows.
- **Help:** User guide…, Guided walkthrough…, Troubleshooting details…, About.

## 3. Students

Header:

- Title: `Students`
- Description: `The students who need a placement. Type rows, paste from a spreadsheet, or import a CSV.`
- Actions: `Add student`, `Paste from spreadsheet`, `Import CSV…`
- Quiet count at right.

Columns:

1. Name
2. ID
3. Address
4. Coordinates (optional), displayed and edited as `latitude, longitude`

IDs auto-fill as `S001`, `S002`, and remain secondary in visual weight.

### Empty state

A centered surface with:

- `Add your students`
- `Paste from spreadsheet`
- `Import CSV…`
- `Type the first row`
- quiet `Load sample data` action

### Validation

- Invalid cells receive a warm error tint and tooltip.
- Missing required values receive an amber tint rather than an alarm-red treatment.
- A slim issue strip above the table lists clickable issues and jumps to their cells.
- Imported invalid rows remain in the table using their original text and a marked left edge; users repair them in place.
- More than 100 students produces a non-blocking note: the app is designed for 100, but does not refuse to continue.

## 4. Locations

Same table interaction as Students.

Columns:

1. Name
2. ID
3. Capacity
4. Minimum (optional)
5. Address
6. Coordinates (optional)

Capacity has no invented default. A blank capacity remains visibly unresolved with `How many students can this location take?`

If total maximum capacity is below the student count, show a quiet information strip explaining the shortfall. Do not block editing or application startup.

## 5. Rules

Title: `Rules (optional)`.

Empty copy: `Most placements need no rules at all. Add one only when something must be true.`

`Add a rule` menu:

- Ranked choices…
- Keep students together…
- Keep students apart…
- Pin a placement…
- Not allowed at a location…
- Limit commute time…
- Allowed locations only…

Existing rules display as concise sentence cards, for example:

- `Aisha prefers 1. North Clinic, 2. Riverside.`
- `Mateo and Ana are placed at the same location.`
- `Nobody drives more than 45 minutes.`

Cards show quiet Edit and Delete actions. Editors are small native `QDialog` windows—not bespoke inline expansion. Dialogs use normal Esc, default-button, label, and tab-order behavior.

Ranked choices open a bulk student-by-rank grid dialog because choices are normally entered for many students. Together/apart use searchable multi-selection. Pin/prohibit use student and location combos. Commute limits provide a global minutes field and a collapsed per-student table. Allowed locations use one student picker and location checkboxes.

Deleting a referenced student/location updates affected rules and reports the result in a temporary toast with Undo. Empty rules are removed. This cleanup is one undoable operation.

## 6. Travel times

Intro: `Driving times decide the placements. Choose how to get them—you can switch modes later without losing your roster or rules.`

Three equal radio cards:

### Enter times myself

`Type or paste each home-to-location drive. No internet needed.`

The primary Phase D workflow is a minutes grid:

- Rows: student names in the vertical header.
- Columns: location names in the horizontal header; truncated names have tooltips.
- Numeric cell: driving minutes.
- `x` or `-`: no route.
- Blank: not filled yet.

Toolbar: Paste, Import CSV…, Export times….

Completeness is always visible: `Filled 214 of 240`, plus a progress bar. Every cell needs a number or explicit no-route before the mode is ready.

Grid edits set driving minutes only. Distances are present when supplied by CSV or a map provider; manually entered times need not invent distances. Results prioritize driving time and omit unavailable distance values cleanly.

Adding/removing students or locations preserves all unaffected cells and introduces only the new required pairs as blank.

### Offline map pack

`Download a map of your region once, then it works with no internet. Nothing is sent anywhere.`

Phase D may show a clean not-yet-configured panel. Phase E adds prepared-pack listing, download/resume/cancel, compatible installed-pack state, local calculation, and pack repair. A missing, corrupt, or incompatible pack disables only offline mode and offers redownload or another travel mode.

### Online maps (Google)

`Addresses are sent to Google to get driving times. Names and choices are never sent.`

Phase D may show a clean provider-setup panel. Phase E adds API-key entry, test connection, calculation, cancellation, address review, and failure recovery.

Required full disclosure:

`Only street addresses (or coordinates) are sent to Google. Student names, IDs, choices, and rules never leave this computer.`

### Travel state semantics

- A calculated matrix shows `Travel times ready — 38 students × 6 locations` with View times and Recalculate.
- Any roster/location change marks calculated travel as `Needs updating — N new pairs`; unaffected data remains.
- Recalculate replaces the provider-calculated matrix.
- Manual edits made after a provider fill survive until the user explicitly recalculates.
- No-route pairs are unavailable assignments; they are never replaced by straight-line estimates.
- Provider failure preserves all data and offers Try again, Use offline map, or Enter times myself.

## 7. Results

Order:

1. Outcome banner.
2. Optional quiet warnings strip.
3. Conditional statistic cards.
4. By student / By location toggle.
5. Assignment table and capacity panel.
6. Export CSV and Print actions.

### Success

Banner: `Placements found — every rule is satisfied.`

Stats:

- Longest drive
- Average drive
- `Got one of their choices — 35 of 38` only when choices exist
- Total driving

Assignment columns:

- Student
- Placement
- Drive
- Choice only when choices exist
- Changed only when prior assignments exist

Capacity panel uses restrained bars plus numeric assigned/capacity text.

### Other outcomes

- **Usable but unproven:** plain explanation that assignments are valid but might improve with more calculation time.
- **Unassigned:** amber banner; unassigned students sort first.
- **No arrangement fits:** explanation plus practical next actions; inputs unchanged.
- **Not solved in time:** suggest more time or fewer rules.
- **Cancelled:** neutral status; restore previous results if present.
- **Stale:** keep prior results visible under `These placements predate your latest changes`; footer changes to Update placements.

Warnings such as over-target commutes or relevant no-route pairs live in a quiet bulleted strip directly under the banner.

Solving progress appears only after about 750 ms, runs away from the UI thread, and can be cancelled.

## 8. Table interaction contract

This section is normative for Students, Locations, manual times, and bulk choices.

- Single click selects.
- Enter, F2, double click, or typing begins editing.
- Tab/Shift+Tab commit and move horizontally.
- Enter commits and moves down.
- Escape cancels the current edit.
- Arrows navigate when not editing.
- Delete/Backspace clears selected cells.
- A final live new-row position allows keyboard-only entry.
- Click-drag and Shift navigation select ranges.
- Ctrl/Cmd+A selects the table; Ctrl/Cmd+C copies TSV suitable for Excel.
- Ctrl/Cmd+V parses a TSV block anchored at the active cell and appends overflow rows when applicable.
- Valid pasted cells always land. Invalid cells retain their original text and are marked for repair.
- A paste block is one undo operation.
- Validation runs after editing settles, never blocks typing, and updates issue/readiness state.
- Add row: Ctrl/Cmd+Plus or Ctrl/Cmd+=.
- Delete rows: Ctrl/Cmd+Minus.
- CSV file drop onto a roster/location table behaves exactly like Import CSV.
- Pasting split latitude and longitude columns into the combined coordinate column joins them as `latitude, longitude`; it keeps both values and avoids unnecessary repair.
- Undo is scoped to table operations, paste blocks, and the most recent rule deletion. There is no complicated global cross-step command history.

## 9. Import and recovery dialogs

Partial CSV import states how many rows were accepted and lists row-level issues. Invalid draft rows are already visible in the table. Actions: `Fix them in the table` and `Discard import`.

Corrupt project copy: `This file couldn't be opened—it may be damaged or from another app.` Actions: Start a new project, Choose another file….

Expected provider failures render inline rather than as blocking message boxes. Details expand to one sanitized technical line; never a stack trace, API key, or roster content.

## 10. Advanced options and diagnostics

Choosing `More options…` from Goal opens one dialog:

- Ordered goals with up/down controls.
- Commute target in minutes.
- Calculation time limit in seconds.
- Allow students to be left unplaced.
- Restore defaults.

The first goal is made as good as possible before the next begins. Returning from manual ordering sets the footer Goal to Custom.

Help → User guide opens a modeless plain-language reference covering the five-step workflow, field meanings, rules, travel-time cells, goals, results, and spreadsheet controls. F1 opens the guide. Input-table column headings expose the same concise definitions as tooltips and assistive descriptions.

Help → Guided walkthrough opens an optional modeless five-step companion that moves the main window to each real page while explaining what to do. It never changes project data, never blocks interaction with the app, and is not shown automatically.

Help → Troubleshooting details opens a small read-only panel with application version, OS, travel mode, optional pack metadata, and sanitized last-error text. It structurally excludes student data and keys. This is not an audit screen.

## 11. Visual system

Use the operating-system UI font: SF Pro on macOS, Segoe UI on Windows.

- Page title: 15 pt semibold.
- Body and tables: 11 pt.
- Secondary text: 10 pt.
- Stat values: 17 pt semibold.
- Sentence case throughout.

Spacing uses a 4-point base: page padding 24, card padding 16, table row about 32, toolbar gap 8. Cards/dialogs use 8-point radius; controls use 6. Tables use horizontal hairlines and a subtle alternate row tint, not dense vertical boxes.

Light tokens:

- Window `#F6F6F4`
- Surface `#FFFFFF`
- Border `#E3E1DC`
- Text `#23251F`
- Secondary `#6E6B64`
- Accent `#2F6F5E`
- Accent pressed `#276050`
- Success `#2F8F4E`
- Warning `#B5760A`, background `#FFF4E0`
- Error `#C23535`, background `#FCECEC`

Provide corresponding dark tokens following the same restrained contrast relationships. Follow OS color-scheme changes. Status never relies on color alone.

Component hierarchy: one filled accent primary action; tinted banners; outlined secondary actions; quiet text actions; ghost row actions. Almost no shadows.

## 12. Accessibility and keyboard

- Ctrl/Cmd+1…5 navigates steps.
- Ctrl/Cmd+Enter runs Find placements.
- Standard file/edit shortcuts appear in menus.
- Full keyboard operation and visible two-point accent focus ring.
- Accessible names and useful descriptions for terse controls.
- Announce status changes politely; do not steal focus for non-blocking banners.
- Focus moves only for action-requiring dialogs.
- Text/icon accompanies every color status.
- Numeric text accompanies capacity bars.
- Minimum interactive target 28 points.
- Layouts remain usable under OS text scaling.
- Progress respects reduced motion.

## 13. PySide6 implementation boundaries

- `QMainWindow`, a rail `QListView`, central `QStackedWidget`, and fixed footer `QFrame`.
- `QTableView` + `QAbstractTableModel`, never `QTableWidget`, for editable grids.
- Validation state belongs to models; delegates supply special editors.
- Fusion style plus one token-based QSS layer for consistent Windows/macOS treatment.
- OS light/dark palette updates.
- The UI consumes parent-authored application/session interfaces and does not formulate optimization or provider requests.
- Solver, provider, pack, and bulk parse work never runs on the UI thread.
- Worker signals carry immutable application result objects.
- Long-work progress appears only after approximately 750 ms.
- `QSettings` stores only interface preferences such as geometry, last mode, units, and directories. It never autosaves rosters.
- Save/open use the application project service. Export/Print enable only when results exist.
- UI state changes use one parent-authored draft session/version source; results compare their input version with the current version to determine staleness.

## 14. Deliberately absent

- No map canvas or GIS editing.
- No splash screen, forced onboarding, hero image, or branding panel. The optional walkthrough is opened only from Help.
- No dashboard.
- No charts beyond capacity bars.
- No accounts, cloud sync, collaboration, telemetry, or audit view.
- No autosave of roster data.
- No modal navigation wizard.
- No visible technical jargon in the default path.
- No per-row icon clutter.
- No custom popover framework.
- No bespoke inline rule editor framework.
