# static-analysis-runner 0.9.7

Security release fixing destructive output handling.

## Fixed

- Empty `--output` values can no longer resolve to and delete the current working directory.
- Filesystem root, home, current directory, ancestors of the current directory and detected project roots are rejected.
- Output paths may not overlap repositories, profiles, suites, foundation artifacts or input manifests.
- `--replace` is now opt-in.
- A non-empty directory is replaceable only when it contains a valid runner ownership marker.
- `code-analyzer-core` and candidate-selector executable preflight happens before output replacement.
- Repository, suite, workspace and low-level knowledge materialization use the same guarded output policy.

## Compatibility

Existing non-empty output directories created by 0.9.6 or earlier do not contain the ownership marker and are intentionally not auto-adopted. Choose a new output path or manually remove the old output after verification.
