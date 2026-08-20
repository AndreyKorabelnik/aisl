# aisl-reporting 0.8.1

## Visible progress and durable logs

`aisl-reporting build` now prints stage-level progress and writes the same events to
`report-run.log`. Long-running dataset and LLM stages emit configurable heartbeats.

## Report preservation on validation issues

The rendered Markdown is saved before structural validation. Missing headings or evidence
citations are warnings by default and are recorded in `report-validation.json` and
`report-run-manifest.json`. `--strict-validation` restores fail-fast CI behaviour, while still
preserving the report and validation artifacts.

## More tolerant heading validation

Required sections are recognized at any Markdown heading level and with common numeric prefixes,
for example `# Резюме`, `### 2. Резюме`, and `## 2) Резюме`.

## New CLI options

- `--strict-validation`
- `--heartbeat-sec N`
- `--quiet`
- `--debug`
