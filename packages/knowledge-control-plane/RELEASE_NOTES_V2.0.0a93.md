# analysis-ui 2.0.0a93

## Knowledge Profile Registry backend

- Persistent platform/user Knowledge Profile registry in Control Plane.
- Create / update / copy / delete user profiles; platform profiles remain read-only.
- Runner-owned `knowledge-profile-resolve` is used for validation and dependency preview.
- Job may select a saved Knowledge Profile while Scenario continues to provide the default profile and UX context.
- Knowledge Product HTTP projection exposes Runner-owned dependencies, materialization/capability and source metadata.
- Read-only job Production Structure endpoint projects immutable profile/plan/result artifacts without rebuilding semantics.
