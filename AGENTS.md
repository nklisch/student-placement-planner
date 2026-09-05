# Repository Agent Instructions

Before changing this repository, read and follow:

1. [`docs/BUILD_INSTRUCTIONS.md`](docs/BUILD_INSTRUCTIONS.md) — durable product priorities, implementation constraints, failure-handling policy, and model responsibilities for this build.
2. [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — architecture, staged delivery plan, quality gates, and review seams.
3. [`docs/UI_SPECIFICATION.md`](docs/UI_SPECIFICATION.md) — approved desktop interaction and visual specification for UI work.

These documents govern the current implementation program. Keep them current when a product or architectural decision changes; do not let code and the recorded plan silently diverge.

In particular:

- This is a small, local desktop utility whose priorities are useful results, mathematical correctness, smooth operation, and a pleasant interface.
- Do not add speculative file, operating-system, or startup security guards that can prevent legitimate installations from running. Follow the concrete threat-model rule in `docs/BUILD_INSTRUCTIONS.md`.
- The parent agent owns architecture, integration, adjudication, and release; bounded implementation may be delegated under the current model agreement in `docs/BUILD_INSTRUCTIONS.md`.
- Follow that document's current model responsibilities and sparse final-review schedule.
