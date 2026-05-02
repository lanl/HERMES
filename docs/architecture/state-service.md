# State_Service Module #

## Overview ##
The `src/hermes/state_service/` module is the control layer that manages all interaction with the measurement state. It acts as a gatekeeper to ensure safe, validated, and auditable changes.

Purpose
- Provide controlled access to the state
- Enforce validation and consistency
- Implement approval workflows for changes
- Track history and ensure traceability
- Prevent direct mutation by external components (especially AI)

Responsibilities
    1. State Access
        - Read full state or specific values
        Example:
        - get_state()
        - get_value(path)
    2. Change Proposals
        - Create structured change requests instead of applying edits directly
        Example:
        - propose_change(path, new_value)
    3. Approval Workflow
        - Require explicit approval before applying changes
        Example:
        - apply_change(change_id)
        - reject_change(change_id)
    4. Validation
        - Ensure all changes meet constraints before being applied
        Examples:
        - value ranges
        - field existence
        - compatibility between components
    5. Change Tracking / History
        - Log all approved (and optionally rejected) changes
        - Maintain audit trail for experiments
    6. High-Level Actions
        - Provide safe operations that encapsulate common workflows
        Examples:
        - load_state_from_yaml("LC-20231023.yaml")
        - set_acquisition_mode("serval")
        - update_working_dir("/data/LC-20231023")

State_Service Module Design Principles
- Single entry point for mutation: no direct state edits allowed elsewhere
- AI safety: Future AI agents can propose changes but cannot apply them
- Auditability: every change is tracked and reversible (if designed)
- Extensibility: can later integrate hardware triggers or side effects

### module structure ###
The `src/hermes/state_service/` module is organized into several key components:
- `state_manager.py`: 
    - core logic for managing state access, change proposals, validation, and approval workflow.
    - provides the main interface for other components to interact with the state.
    - functions include:
        - `get_state()`: returns the current state object.
        - `get_value(path)`: returns the value at the specified path in the state.
        - `propose_change(path, new_value)`: creates a new ChangeRequest for the proposed change.
        - `approve_change(change_id)`: approves a pending ChangeRequest and can apply it immediately.
        - `apply_change(change_id)`: applies the proposed change if it passes validation and is approved.
        - `reject_change(change_id)`: rejects the proposed change and logs the rejection.

- `change_requests.py`: 
    - the ChangeRequest data model and related logic for tracking proposed changes.
    - includes fields for change ID, path, new value, proposer, timestamp, status (pending/approved/rejected), and optional justification.
    - StateManager owns the in-memory pending-change workflow.

- `state_io.py`: 
    - functions for loading and saving the state to/from config files (e.g. YAML).
    - handles serialization and deserialization of the MeasurementState object, ensuring that the state can be persisted across sessions and easily edited by users if needed.
    - functions include:
        - `load_state_from_yaml(file_path)`: loads the state from a YAML file and returns a MeasurementState object.
        - `save_state_to_yaml(state, file_path)`: saves the given MeasurementState object to a YAML file.

- `state_logger.py`: 
    - handles logging of all state changes for traceability and audit purposes.
    - integrates with loguru to write logs to a specified log directory, including details of the change, proposer, timestamp, and status.
    - functions include:
        - `log_change(change_request)`: logs the details of a ChangeRequest when it is proposed, approved, or rejected.

- `shared_types.py`: 
    - common types and enums used across the state service (e.g. ChangeStatus).

## State-Service Module Structure 

```text
src/
└── hermes/
    └── state_service/          # state management, change proposal, validation, and approval workflow
        ├── __init__.py         # makes hermes.state_service a Python package. Keep __init__.py empty!
        ├── state_manager.py    # core logic for managing state access, change proposals, validation, and approval workflow
        ├── change_requests.py  # the ChangeRequest data model and related logic for tracking proposed changes
        ├── state_io.py         # functions for loading and saving the state to/from config files (e.g. YAML)
        ├── state_logger.py     # functions for logging state changes and maintaining an audit trail
        └── shared_types.py     # shared types and enums for the state service
``` 
