# Student Placement Optimizer

A local-first desktop utility for assigning a school cohort to placement locations while respecting capacity and practical constraints and optimizing estimated driving time.

The project is under active implementation. See:

- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) for the architecture and staged build plan.
- [`docs/BUILD_INSTRUCTIONS.md`](docs/BUILD_INSTRUCTIONS.md) for durable product and implementation priorities.

The intended release is a normal Windows/macOS installer; end users will not need Python or a terminal.

## Current developer setup

Python 3.12 is pinned through `mise`:

```bash
mise install
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

The current code contains the independent exact reference solver and initial travel-provider boundaries. The desktop application and advanced OR-Tools model are the next implementation phases.
