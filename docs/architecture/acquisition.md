# Acquisition

`src/hermes/acquisition/` owns runtime interaction with SERVAL and detector-facing
workflows.

Expected responsibilities:

- connect to SERVAL
- read dashboard, detector info, detector health, detector layout, and detector configuration
- upload detector configuration
- configure SERVAL destinations
- start and stop measurements
- poll acquisition status
- produce acquisition artifacts and update the central record

The acquisition layer may use ASI SERVAL concepts directly, but the rest of the
codebase should interact through HERMES models and workflow functions.
