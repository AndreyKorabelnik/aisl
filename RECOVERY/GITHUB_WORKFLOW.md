# GitHub / Codex workflow

## Canonical rules

1. `main` contains the complete active code base required to rebuild all four deliveries.
2. Source canonical is a Git commit SHA.
3. Release canonical is an immutable tag + GitHub Release.
4. GitHub Release assets contain the four clean deliveries plus `SHA256SUMS`.
5. Recovery ZIPs and superseded delivery ZIPs are never committed to Git history.
6. Functional work is done on a branch and merged by PR (or intentionally fast-forwarded for a tiny owner-only change).
7. Codex may edit/test/build/inspect Git state; ChatGPT owns architecture/review/task framing.

## Recommended tag convention

Use a platform release tag independent of the four delivery package versions:

`release-YYYY.MM.DD.N`

Example:

`release-2026.08.19.1`

The release notes/manifest must record the exact versions and SHA-256 values of:

- `aisl-producer`
- `aisl-server`
- `aisl-client`
- `aisl-ui`

A source checkpoint does not need a tag. `git rev-parse HEAD` is sufficient.

## Bootstrap rule for public visibility

The current source tree contains validation/acceptance references to real/corporate systems (including UCP/AT900/Sber-related material). Bootstrap the repository as **private** first. Change visibility to public only after an explicit publication/sanitization review. This is a publication-safety gate, not an AISL runtime mechanism.

## Normal development after bootstrap

```text
main
  ↓
feature/<task>
  ↓
Codex: inspect → edit → targeted tests → affected contract tests → compile/import → smoke
  ↓
git diff / status
  ↓
commit
  ↓
push + PR
  ↓
review
  ↓
merge
  ↓
main commit SHA becomes new Source canonical
```

Before a release: update versions → clean transient files → compile/import → build four deliveries → unpack/verify manifests and SHA → tag exact commit → create GitHub Release → attach four deliveries + `SHA256SUMS`.
