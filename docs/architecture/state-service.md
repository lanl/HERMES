# State_Service Module #

## Overview ##
The `src/hermes/state_service/` module is the control layer that manages all interaction with the measurement state. It acts as a gatekeeper to ensure safe, validated, and auditable changes.

Purpose
- Provide controlled access to the state
- Enforce validation and consistency
- Implement approval workflows for user- and AI-originated changes
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
        - Require explicit approval before applying user- and AI-originated changes
        - Allow trusted workflow code to apply validated changes when an
          approval-bypass setting is enabled
        - Record whether each applied change was explicitly approved or applied
          through a trusted workflow bypass
        Example:
        - approve_change(change_id)
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
    6. External Payload Handling
        - Store large durable state values as payload files under
          `logs/payloads/` when they should not be duplicated inline
        - Compute payload size and hash
        - Replace the proposed state value with an ExternalPayloadRef before
          applying and logging the change
        Examples:
        - externalize_payload("detector.pixel_config", pixel_config)
        - externalize_payload("detector.dacs", dacs)
    7. High-Level Actions
        - Provide safe operations that encapsulate common workflows
        Examples:
        - load_hermes_record_from_yaml("LC-20231023.yaml")
        - set_acquisition_mode("serval")
        - update_working_dir("/data/LC-20231023")

State_Service Module Design Principles
- Single entry point for mutation: no direct state edits allowed elsewhere
- AI safety: Future AI agents can propose changes but cannot apply them without
  explicit approval
- Trusted workflows may apply validated changes without per-change approval only
  when the approval-bypass setting is enabled
- Auditability: every change is tracked and reversible (if designed)
- Extensibility: can later integrate hardware triggers or side effects

## Approval Policy

All durable state changes must go through `StateManager`; the approval
requirement depends on the origin of the change:

- `user` and `ai` changes must be proposed as `ChangeRequest` objects and
  explicitly approved before they are applied.
- `trusted_workflow` changes may be applied after validation without explicit
  per-change approval when a controlled approval-bypass setting is enabled.
- If the approval-bypass setting is disabled, trusted workflow changes should
  create pending `ChangeRequest` objects like any other proposed change.

The approval-bypass setting should be explicit in the state service
configuration, for example `allow_trusted_workflow_bypass`. Bypassed changes are
not direct mutations: they still pass validation, go through `StateManager`, and
are logged with their source, validation result, bypass flag, proposer, and
timestamp.

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
        - `apply_change(change_id)`: applies the proposed change if it passes validation and is approved, or if it is a trusted workflow change and approval bypass is enabled.
        - `reject_change(change_id)`: rejects the proposed change and logs the rejection.

- `change_requests.py`: 
    - the ChangeRequest data model and related logic for tracking proposed changes.
    - includes fields for change ID, path, new value, proposer, origin, timestamp, status (pending/approved/rejected/applied), optional approver, optional approval bypass flag, and optional justification.
    - StateManager owns the in-memory pending-change workflow.

- `state_io.py`: 
    - functions for loading and saving `HermesRecord` YAML files.
    - handles serialization and deserialization of the `HermesRecord` object,
      ensuring that the state can be persisted across sessions and easily edited
      by users if needed.
    - parses YAML safely, validates loaded data through the Pydantic
      `HermesRecord` model, and writes predictable YAML without relying on
      advanced YAML features such as anchors.
    - may support JSON import/export as a secondary machine-readable format, but
      YAML is the primary persisted run-record format.
    - functions include:
        - `load_hermes_record_from_yaml(file_path)`: loads a `HermesRecord` from a YAML file.
        - `save_hermes_record_to_yaml(record, file_path)`: saves the given `HermesRecord` to a YAML file.

- `payload_store.py`:
    - writes large state-owned payloads to the run `logs/payloads/` directory.
    - does not use or create a separate `state_payload_dir`.
    - computes `sha256`, `size_bytes`, media type, creation timestamp, and a
      stable relative path.
    - returns an `ExternalPayloadRef` that can be stored in the HERMES record and
      written to the state log.
    - does not decide acquisition or analysis behavior; it only materializes
      durable state payloads.

- `state_logger.py`: 
    - handles logging of all state changes for traceability and audit purposes.
    - logs the initial state record and later state changes, including details
      of the change, proposer, timestamp, and status.
    - logs `ExternalPayloadRef` values when large state fields have been
      externalized.
    - does not configure Loguru sinks or write external payload files.
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
        ├── state_io.py         # functions for loading and saving HermesRecord YAML files
        ├── payload_store.py    # writes large state-owned payloads under logs/payloads and returns ExternalPayloadRef values
        ├── state_logger.py     # functions for logging state changes and maintaining an audit trail
        └── shared_types.py     # shared types and enums for the state service
``` 
