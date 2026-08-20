# Knowledge API 0.33.0

- Separates published artifact content identity from filesystem location.
- AISL Artifact Store publication now emits backend-independent `aisl+sha256://<digest>` locators instead of absolute `file://` CAS paths.
- Published reads resolve the content locator against the currently configured AISL Artifact Store root.
- Moving the filesystem Artifact Store therefore does not require rewriting or republishing a KnowledgeRevision/KnowledgeProduct.
- Producer-side publication input remains validated from explicit source files before import/finalize.
- Exact SHA/size validation is preserved after relocation; locator digest and artifact digest mismatches are rejected explicitly.
- No second registry, SQLite normalization, dual-read/dual-write, or semantic producer changes were introduced.
