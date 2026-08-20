# ADR-003: preserve visible UI during internal replacement

Status: accepted  
Date: 2026-07-28

## Decision

Retain the visible layout, styling, report rendering, progress presentation, and core workflows of UI2 1.4.7 until backend and API functionality is restored.

## Verification

Iteration 1 copies frontend runtime files byte-for-byte and records their SHA-256 values. Existing source-contract tests continue to protect key UI behavior. Deliberate UX changes will be handled only after functional migration.
