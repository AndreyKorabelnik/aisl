# Tests and acceptance

Date: 2026-08-19

## Latest changed component

`aisl-reporting 0.4.3`

- targeted reporting tests: **104/104 PASS**
- headers + redirect contract: **PASS**
- error diagnostics contract: **PASS**
- compile/import: **PASS**
- clean wheel build/install smoke: **PASS**
- real corporate endpoint post-fix acceptance: **PENDING**
- full framework regression: **NOT RUN / NOT CLAIMED PASS**

## Last confirmed real UCP E2E

Revision `rev-8bed9d612efcdac7198640ad` successfully served the published data-model/storage knowledge through AISL Server and `aisl-sdk`/`aisl-cli`.

Important semantic acceptance:

- ambiguity is preserved;
- `not_observed` is not promoted to absence;
- strongly-supported executable storage joins do not become confirmed physical SQL/PDM joins;
- consumers work from published pinned revision knowledge rather than re-running Core/Runner.

## Migration validation

GitHub migration changes are repository metadata/hygiene only. No full framework regression is claimed for migration.
