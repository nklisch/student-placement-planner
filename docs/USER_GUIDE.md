# Student Placement Planner user guide

Use this guide to turn a student list, placement spaces, and driving times into a saved placement plan. Start with the sample before entering real student data.

[Install on Windows or Mac](INSTALLATION.md) · [Students CSV](examples/students.csv) · [Locations CSV](examples/locations.csv) · [Driving times CSV](examples/travel-times.csv)

**Save your work explicitly.** There is no automatic roster save. A `.spp` project keeps your editable work; a result CSV is a list to share, not a project you can reopen to continue planning.

## 1. Try the sample

1. Open the app and choose **File → Load sample data**. Save any existing work when prompted.
2. Look through Students, Locations, Rules, and Travel times. The sample already has manual driving times, so no internet or map account is needed.
3. Leave the goal at **Fair commute**, then choose **Find placements**. Results show placements, driving times, and capacity use.
4. Try **Choices first** and calculate again to compare the result. In the built-in sample, Fair commute can give neither of the two students with choices a listed choice. “Every rule is satisfied” still means the required constraints are met: ranked choices are preferences, not promises.
5. Choose **File → Save As…** to save a `.spp` project. You can reopen that file with **File → Open…**.

**Help → Guided walkthrough…** explains each page while leaving the app usable. **Help → User guide…** or F1 opens the built-in reference.

## 2. Enter students and locations

Choose **File → New** for your own project. Use one row per student and one row per placement location. The app is designed for school-sized runs of about 100 students.

Students need names. Locations need names and **Capacity**, the most students that site can take. **Minimum** is optional: it requires at least that many students at the site. Leave it blank for zero. Capacities and minimums are whole numbers, and a minimum cannot exceed capacity.

Each row has an **ID**, a short code used to match travel imports and refer to students or locations. Missing IDs are generated automatically, such as `S001` and `L001`. Keep IDs unique within each table. For a matching travel CSV, use the IDs actually shown in the tables.

Addresses or coordinates are needed only when maps calculate times. Manual times do not need either.

### Import a CSV

A CSV is a spreadsheet saved as comma-separated values with a header row. Download the three linked examples (on GitHub, use **Download raw file**, rather than saving the web page). They contain fictional names and manual times, not addresses for online lookup.

To try them, start a blank project, import `students.csv` on Students, import `locations.csv` on Locations, then import `travel-times.csv` under **Travel times → Enter times myself**. Every pair is provided; choose **Find placements** to see a complete result.

**Roster imports append rows; they do not replace or update existing rows by ID.** Importing the same file twice can create duplicate IDs. Start a new project for a replacement roster, or remove the rows you intend to replace. Review marked cells and the import issues before proceeding.

These displayed headers are accepted, in any order:

```csv
Name,ID,Address,Coordinates
Alex Morgan,S001,,
Sam Rivera,S002,,
```

```csv
Name,ID,Capacity,Minimum,Address,Coordinates
North Clinic,L001,1,0,,
Riverside School,L002,1,0,,
```

| Field | Accepted CSV headers | Meaning |
| --- | --- | --- |
| Student name | `Name`, `student_name` | Name shown in rules and results. |
| Student ID | `ID`, `student_id` | Unique student code; omit or leave blank to generate one. |
| Location name | `Name`, `location_name` | Placement site's name. |
| Location ID | `ID`, `location_id` | Unique location code; omit or leave blank to generate one. |
| Maximum spaces | `Capacity` | Required whole-number maximum. |
| Minimum spaces | `Minimum`, `minimum_capacity`, `min_capacity` | Optional whole-number minimum. |
| Street address | `Address` | Starting address or placement address for map lookup. |
| Coordinates | `Coordinates` | Latitude, then longitude. Quote the pair in CSV, for example `"51.5074, -0.1278"`. |
| Separate coordinates | `latitude` / `lat` and `longitude` / `lon` / `lng` | Alternative to the combined Coordinates field; supply both. |

Headers are case-insensitive. Use one header per field rather than supplying competing aliases. Keep only the fields you want to import; check warnings about unrecognized columns instead of assuming those columns became rules. Ranked choices and other rules are entered on Rules, not through these roster CSVs.

### Paste from a spreadsheet

Copy **data cells without a header row**, select the first destination cell, and paste. Unlike CSV import, paste follows the visible column order:

- Students: Name, ID, Address, Coordinates.
- Locations: Name, ID, Capacity, Minimum, Address, Coordinates.

Include blank cells for optional columns you skip in the middle of a block. You can also paste just names into the Name column and let the app fill IDs. Tab moves across, Enter commits and moves down, and Escape cancels the current cell edit.

To clear cells, use Delete or Backspace. To remove people or sites, select their rows and choose **Remove selected**. **Undo reverses the most recent data edit across the project**, even if it was on another page; Redo reapplies it. A pasted block is one edit. Goal, travel-mode, and file settings are not part of this data history.

## 3. Add only necessary rules

Use **Rules → Add a rule** for these requirements:

- **Keep together / apart:** selected students must share a location, or use different locations.
- **Pin a placement:** a student must use one particular location.
- **Not allowed at a location:** prohibit that student/location pair.
- **Allowed locations only:** restrict a student to the checked locations. Checking none means the student cannot be placed anywhere; it does not mean “no restriction.”
- **Limit driving time:** a strict maximum. An individual student's limit **overrides**, rather than adds to, the general limit. For example, a 45-minute individual limit permits that student up to 45 minutes even if the general limit is 30.
- **Ranked choices:** preferred locations, in order. These guide the goal but do not make other locations forbidden. Use Allowed locations only if a student must receive one of a particular set.

The **commute target** in the goal's **More options…** is different from a strict limit. It counts drives above a preferred threshold so the app can try to reduce them; it does not prohibit them.

## 4. Provide driving times

### Enter times myself: no internet needed

Each row is a student and each column is a location. Fill every student/location pair:

- A number means **driving minutes**, such as `18` or `12.5`.
- `x` or `-` means **no route**. The student cannot be assigned there.
- Blank means **not entered yet**, not zero and not no route.

Paste a rectangular block of times without names or headings. Use **Export times…** to make a template containing every pair of current IDs, including blank cells. Fill it in a spreadsheet and import it back. Travel import matches pairs by ID and updates those cells; it does not append students or locations.

```csv
student_id,location_id,driving_minutes,distance_km
S001,L001,12,
S001,L002,25,
S002,L001,22,
S002,L002,10,
```

Distance is optional; do not invent it if you only know the time. The importer also accepts `minutes` or `duration_minutes` for minutes, `duration_seconds` for seconds, and `distance_meters` for metres. Use one time field and at most one distance field. Keep each student/location pair unique. In a template, leave unfinished times blank until you know them; use `x` only for a genuinely unavailable route.

### Offline map pack

Download a region inside the app and let it prepare the map. The first download needs internet, enough free disk space, and time to prepare; later address lookup and driving calculations run locally. Choose a matching region suggestion and wait for both download and preparation to finish. The region must cover the addresses and routes you need. Review address matches before calculating.

A missing or unusable pack does not stop you using manual times or online maps. See [offline map details](MAP_PACKS.md) for pack management and troubleshooting.

### Online maps

Online lookup sends only street addresses or coordinates to the selected service—not student names, IDs, choices, capacities, or rules. Addresses can still be sensitive: use this mode only when your school's data policy permits it.

- **Community service:** no key; intended for occasional use, subject to shared-service limits and availability.
- **openrouteservice:** needs an account/key and is subject to plan quotas.
- **Google:** needs a key, the required APIs enabled, and billing configuration. Usage may incur charges.

Follow [online routing setup](GOOGLE_MAPS_SETUP.md), review matches, then calculate times. Keys are not saved in the project. If a service is unavailable, keep your work and retry, choose another service, or enter manual times. No missing route is silently replaced with straight-line distance.

### Repair an address or input

Marked cells and the issue list identify missing or unusable input. Correct the text in place; valid imported rows remain. Check travel import issues too: unknown IDs cannot fill a cell, and an invalid time is not a successful replacement.

**Coordinates control the route when present**, even if an address is also shown. When changing an address that has coordinates, choose whether to use the new address or keep the coordinates. Using the new address clears the old coordinates; keeping them continues to route from that point. You can also clear Coordinates explicitly before looking up an address again.

Review successful and unresolved address rows before calculation. Correct a missing address in its roster row, or supply accurate coordinates for a location the map cannot match, then retry. Do not accept a distant match just to finish the step. After changing travel inputs, recalculate and check that the times are current.

## 5. Choose a goal and review placements

Goals are considered **in order**, not averaged into a single score:

- **Fair commute:** shorten the longest drive first, then reduce the count over the commute target, total driving, and finally choice penalties.
- **Lowest total driving:** reduce everyone's combined driving time first, then the longest drive and choice penalties.
- **Choices first:** reduce the total ranked-choice penalty first, then the longest drive and total driving.

For choices, first choice has penalty 0, second 1, third 2; an unlisted placement has penalty equal to the number of choices that student listed. A student with no listed choices contributes no choice penalty. Choices first minimizes the **sum of these penalties**, not the number of students receiving any listed choice, and it never overrides a required constraint.

Choose **Find placements**. If something is missing, use the readiness button to jump to the relevant step. Check the result banner, longest and average drives, capacity use, and individual placements. A valid result may still be described as capable of improvement if calculation stopped before proving it best.

If no arrangement fits, check total capacity, minimums, no-route cells, strict driving limits, and conflicting pins or groups. Your inputs remain available to change. **Allow students to be left unplaced**, in More options, is an explicit choice; review every unplaced student rather than treating that result as complete.

Changes to inputs make previous results out of date. Choose **Update placements** before sharing a current plan. If you deliberately share previous placements, make their previous-result status clear to recipients.

## 6. Save, reopen, and share

- **File → Save / Save As…:** save an editable `.spp` project with rosters, rules, travel data, and planning settings. Save regularly and before closing. There is **no autosave of student data**.
- **File → Open…:** reopen a saved `.spp` project. Recalculate placements after reopening when you need results; a project is your planning input, not a permanent results report.
- **Export results… / Export CSV:** share the calculated placement list with a spreadsheet user. This CSV does not contain everything needed to restore the project.
- **Print…:** preview by student or grouped by placement. You can omit driving time and distance when recipients need only names and placements.
- **Export times…:** share or edit the travel grid. This is neither a full project nor a placement list.

Project files, exported CSVs, and printouts can contain student information. Store and share them under your school's usual rules; selecting a cloud-synced folder can upload a file through that folder's own service. The app itself has no cloud database, accounts, telemetry, or background roster synchronization.

If opening a project fails, keep the original file, try another saved copy, or start a blank project. When reporting a problem, include the app version and what you were doing, not real rosters or API keys.
