# Changed files — knowledge-layer-core 0.61.0a35

- `knowledge_layer_core/concept_detector_registry.py` — one KLC-owned ordered registry for the six current concept detectors, their relevant evidence contracts, claim boundaries and dispatch.
- `knowledge_layer_core/repository_inventory_builder.py` — consumes the registry; removes embedded concept boundary map, detector dispatch and relevant-evidence map.
- `tests/test_concept_detector_registry.py` — registry ownership and semantic preservation tests.
- `knowledge_layer_core/version.py`, `pyproject.toml` — version bump to 0.61.0a35.
- `RELEASE_NOTES_V0.61.0a35.md`, `CHANGED_FILES_V0.61.0a35.md` — release provenance.
