# Knowledge Control Plane 1.2.0a12

Default static-analysis outputs are now grouped for human navigation:

`<analysis_output_root>/<system_id>/<scenario_id>/<created-at-UTC>__<short-job-id>/`

The full technical `job_id` remains unchanged and is recorded in `RUN_INFO.json`. Explicit output paths are preserved exactly. The layout is presentation-only and does not participate in producer/materialization cache identity.
