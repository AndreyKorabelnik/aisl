# AISL Publication Bundle v2 — Test Status

Targeted tests only.

- Producer/Server boundary suite: 43/43 PASS (6.49s).
- Cross-module E2E: real KCP v2 bundle builder -> real Server importer -> Server-owned CAS/revision: PASS.
- External publishable Core evidence outside execution tree is included in bundle: PASS.
- Server import with Producer root absent from allowed roots: PASS.
- Empty bundle member identity: PASS.
- Tampered bundle member rejection: PASS.

Full regression was not run for this fix.
