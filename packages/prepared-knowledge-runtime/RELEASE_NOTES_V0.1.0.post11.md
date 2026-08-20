# prepared-knowledge-runtime 0.1.0.post11

Adds thin read-only Repository Inventory SourceOccurrence queries and ID-only Portfolio propagation.

- Lists normalized source occurrences with filters by knowledge object, path, and localization kind.
- Resolves one occurrence with reverse knowledge-object links and published provenance.
- Repository Inventory query contracts advance to v4 and expose gap localization scope/status.
- Portfolio snapshots propagate occurrence IDs for top concept families, discovery candidates and coverage gaps without copying source paths or bytes.
- No source access, parsing, concept inference, benchmark clustering or representative selection is performed in the runtime.
