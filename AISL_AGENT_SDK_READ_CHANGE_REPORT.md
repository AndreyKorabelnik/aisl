# AISL Agent SDK Exact Read — Change Report

Date: 2026-08-15

## Changed package

`knowledge-integration 0.1.8`

## Change

Added `get_knowledge_item(artifact_id, item_kind, local_id)` to the canonical Agent SDK tool catalog and HTTP bindings.

The tool binds to the existing universal AISL item endpoint. `system_id` and `revision_id` remain pinned by the Integration Profile and are not caller arguments.

The tool is a base AISL exact-read operation with no domain capability requirement. It does not perform discovery or semantic search.

Consumer policy now states explicitly:

- `unsupported` / `not_available` are not evidence of absence;
- external semantic/vector retrieval may propose candidates but does not create evidence;
- addressable candidates should be verified by exact AISL read before factual use.

No API, Prepared Knowledge, Core, Runner, KLC or KCP code was changed in this SDK block.
