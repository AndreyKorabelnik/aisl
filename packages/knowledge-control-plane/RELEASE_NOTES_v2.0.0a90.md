# analysis-ui 2.0.0a90

This release makes the Analysis Control Plane boundary explicit:

- Knowledge Profile answers **what knowledge is built**.
- Scenario answers **how a user runs that profile on a selected context**.
- Runner remains the sole owner of product validation, dependency resolution, input normalization and execution planning.

There is no compatibility model for the former mixed `ProfileInfo`, no `/masters` route and no per-job knowledge-composition override.
