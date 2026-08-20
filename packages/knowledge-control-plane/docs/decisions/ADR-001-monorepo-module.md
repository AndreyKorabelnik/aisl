# ADR-001: knowledge-control-plane is a module in the framework monorepository

Status: accepted  
Date: 2026-07-28

## Decision

Place the UI at `code_analysis/packages/knowledge-control-plane` rather than creating a separate repository.

## Rationale

The UI evolves together with public CLI contracts, artifact schemas, reporting profiles, and data-model endpoints. Atomic changes and end-to-end validation are more valuable at this stage than independent repository release management.

## Constraint

Monorepo placement does not permit internal Python imports from sibling modules. Integration still occurs only through public interfaces.
