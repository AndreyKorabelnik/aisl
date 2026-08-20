# Current change summary — 2026-08-19

Current block: **GitHub/Codex canonical-state migration bootstrap**.

Migration-only changes:

- prepared complete source tree for Git bootstrap;
- removed generated Python bytecode/cache files;
- added repository `.gitignore` / `.gitattributes`;
- added canonical `README.md` and `RECOVERY/*` state documents;
- preserved pre-Git checksum manifests under `RECOVERY/PRE_GIT_CHECKSUMS/`;
- changed continuation pointers from ZIP-centric recovery to Git commit/release canonical rules.

No AISL runtime mechanism or knowledge semantics changed.

Latest preceding functional block remains `aisl-reporting 0.4.3` HTTP parity/diagnostics; targeted tests were 104/104 PASS and full framework regression was not run.
