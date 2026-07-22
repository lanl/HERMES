# Agent Instructions

## Working Rules

- Read only current source files, current documentation, and user-provided requirements.
- Prefer small, explicit, testable changes.
- Do not introduce broad architecture before the first concrete workflow exists.
- Keep generated artifacts, caches, detector data files, and build products out of version control.
- Use .scratch for non-tracked files that are useful for development but not part of the core codebase.
- Use /tmp for temporary files that are not useful for development and should be cleaned up regularly.
- If Python code is added, prefer typed APIs, focused pytest coverage, and Pixi-managed environments.
- reference .agent/resources and .agent/examples for context on interfaces with the TPX3Cam, data formats from SPIDR readouts, and EMPIR data analysis.
- Strictly follow the architecture laid out in the docs/architecture directory unless directly working on the architecture itself.
- If the achitecture is unclear, ask for clarification or propose a change to the architecture docs before proceeding.
- If the architecture is missing details necessary to implement a workflow, ask for clarification or propose a change to the architecture docs before proceeding.
- If requests do not align with the architecture, ask for clarification or propose a change to the architecture docs before proceeding.
- Loguru is used for logging, and logs should be structured and informative to aid in debugging and understanding the flow of data through the system.
- Use plain language and avoid abstract terms, like artifacts, contracts, shape, patloads, and products; instead use concrete, descriptive terms that clearly convey the meaning.
