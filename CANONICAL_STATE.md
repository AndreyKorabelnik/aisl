# Canonical state — Git migration bootstrap

Date: 2026-08-19
Status: `GITHUB_BOOTSTRAP_PREPARED`

The code base retains the last accepted real UCP storage-join/publication behavior and the latest `aisl-reporting 0.4.3` HTTP parity/diagnostics changes.

No framework/runtime semantics were intentionally changed by this migration preparation.

Pre-Git provenance archive SHA-256:

`f6b39783676cea949e76d47d7982436deafded3ab644266d92c6b53b2603465f`

After the bootstrap commit is pushed, Source canonical is the exact `git rev-parse HEAD` commit SHA. Release canonical is an immutable `release-YYYY.MM.DD.N` tag and matching GitHub Release.

See `RECOVERY/CURRENT_STATE.md` and `RECOVERY/HANDOVER.md`.
