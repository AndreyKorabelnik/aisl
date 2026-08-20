# AISL Reporting Extraction Change Report

Date: 2026-08-17

## Decision

Reporting is a presentation consumer, not a producer or AISL persistence responsibility. The framework now ends at published AISL knowledge + Knowledge API + integration contracts.

## Framework changes

- removed `packages/knowledge-reporting`;
- Knowledge Control Plane no longer plans, invokes, validates or stores a reporting stage;
- Knowledge API revision publication no longer accepts/stores/imports a `report`;
- removed `/systems/{system_id}/reports...` routes and `prepared_reports`;
- report bytes are no longer AISL CAS reachability members;
- report SHA is no longer part of revision identity;
- KCP report-specific settings, commands and artifact kinds were removed.

## New external module

`aisl-reporting 0.1.0` consumes only `api_url + system_id + revision_id` and published Knowledge API capabilities. It has no runtime dependency on Core, Runner, KLC, KCP or evidence-common. The former direct local `git-change-impact-report/v1` path was intentionally not retained because it violated the single AISL consumer boundary.

## Unchanged owners

Core observed-evidence semantics, Runner planning, KLC knowledge semantics, AISL storage semantics and Knowledge Integration consumer contracts were not changed by this extraction.
