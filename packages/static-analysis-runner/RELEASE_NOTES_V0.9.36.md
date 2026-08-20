# static-analysis-runner 0.9.36

Adds the independent `data-model-discovery` portfolio workflow.

The workflow downloads one repository at a time, runs the lightweight `repository-data-model-discovery` Core profile, publishes one compact candidate profile, removes the working copy and continues. It produces `data-model-candidates.json` and never creates a data-model workspace or starts full data-model analysis.

`--repository-limit` / `--max-repositories` is supported for pilot runs exactly as in `portfolio-topology`.
