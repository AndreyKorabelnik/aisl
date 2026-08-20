# aisl-reporting 0.1.0

`aisl-reporting` is an independent presentation consumer for published AISL knowledge. It is not part of the automatic code-analysis framework producer/runtime.

Canonical boundary:

```text
Published immutable AISL revision
        ↓
Knowledge API
        ↓
aisl-reporting
        ↓
deterministic report_dataset/v1
        ↓
renderer (file or OpenAI-compatible model)
        ↓
validated Markdown
```

The report lifecycle is independent from AISL revision lifecycle: generating or regenerating a report never republishes knowledge and never changes the source `revision_id`.

## Runtime boundary

Required inputs are only:

- Knowledge API URL;
- `system_id`;
- optional explicit `revision_id` (active revision is used when omitted);
- report profile and presentation options.

The module has no runtime dependency on `code-analyzer-core`, `static-analysis-runner`, `knowledge-layer-core`, `knowledge-control-plane` or `evidence-common`.

There is no direct local artifact fallback. The former `git-change-impact-report/v1` direct-input profile was intentionally removed during extraction.

## Profiles

Current API-backed profiles include:

- `system-description/v1`;
- `data-model-report/v1`;
- `reference-data-report/v1`;
- `foreign-data-persistence-report/v1`;
- `workspace-interaction/v1`;
- `sql-source-inventory-report/v1`;
- `sql-change-analysis-report/v1`;
- `workspace-sql-catalog-report/v1`;
- `observed-storage-usage-report/v1`.

A profile is executable only when the selected published revision provides its declared model kind/capabilities. Missing knowledge fails explicitly; there is no silent fallback.

## Prepare deterministic report data

```bash
aisl-reporting prepare \
  --api-url http://127.0.0.1:8080 \
  --system-id ucp-data-model \
  --revision-id rev-... \
  --profile data-model-report/v1 \
  --output-dir ./prepared-report
```

The output contains `report-dataset.json`, `renderer-prompt.md`, `renderer-messages.json` and `report-run-manifest.json`.

## Build Markdown

With an OpenAI-compatible renderer:

```bash
aisl-reporting build \
  --api-url http://127.0.0.1:8080 \
  --system-id ucp-data-model \
  --revision-id rev-... \
  --profile data-model-report/v1 \
  --output-dir ./report \
  --endpoint https://llm.example \
  --model default
```

For an mTLS endpoint, pass the client certificate explicitly. `--insecure` is an opt-in equivalent of `curl -k`; prefer `--ca` when the server CA is available. `--http2` enables HTTP/2 when required by the endpoint:

```bash
aisl-reporting build \
  --api-url http://127.0.0.1:8080 \
  --system-id ucp-data-model \
  --revision-id rev-... \
  --profile system-description/v1 \
  --output-dir ./report \
  --endpoint https://llm.example/v1/chat/completions \
  --model model-name \
  --cert certs/cert.pem \
  --key certs/key.pem \
  --insecure \
  --http2
```

The same renderer settings can be supplied with `LLM_CERT_FILE`, `LLM_KEY_FILE`, `LLM_CA_FILE`, `LLM_TLS_VERIFY`, and `LLM_HTTP2`.

For deterministic/offline testing, use `--response-file` instead of a model endpoint.

## Evidence discipline

- report builders consume published typed knowledge and its provenance/gaps;
- renderer output does not become AISL knowledge;
- missing capability is an explicit error;
- deterministic dataset validation runs before rendering;
- Mermaid ER content is generated/corrected deterministically where supported;
- model wording cannot silently upgrade ambiguity/unresolved evidence into confirmed technical facts.

## Public AISL SDK boundary

`aisl-reporting` consumes published revisions through the public `aisl-sdk` package. Reporting does not own a second Knowledge API transport/revision implementation and does not access AISL artifact-store paths directly.

## Reporting service

`aisl-reporting 0.3.0` can run as an independent consumer service:

```bash
aisl-reporting serve \
  --api-url http://knowledge-api:8080 \
  --runs-root ./report-runs \
  --host 127.0.0.1 --port 18280 \
  --endpoint https://llm.example/v1 \
  --model model-name
```

The service requires a concrete `revision_id` for every ReportRun. It never resolves `latest` implicitly and never publishes back to AISL. Renderer configuration is server-side; clients cannot supply arbitrary LLM endpoints.


## 0.4.0

Adds `declared-data-model-report/v1` for published `code-declared-data-model` revisions, with optional storage context and no physical-JOIN inference.


## Corporate mTLS endpoint parity / diagnostics

For an endpoint that is known to work with `curl --cert ... --key ... -k -L`, use:

```bash
ais-reporting build \
  ... \
  --cert ./certs/cert.pem \
  --key ./certs/key.pem \
  --insecure \
  --http2
```

`LLM_CA_FILE` must not be combined with disabled TLS verification. If a trusted corporate CA bundle is available, use `--ca` and omit `--insecure`.

Prepared runs always keep `renderer-messages.json`. To replay the exact reporting messages through curl for gateway diagnostics:

```bash
jq -n --arg model "$LLM_MODEL" \
  --slurpfile messages ./outputs/reports/$AISL_SYSTEM_ID/renderer-messages.json \
  '{model:$model,messages:$messages[0]}' \
  > ./outputs/reports/$AISL_SYSTEM_ID/llm-request.json

curl -i -L --http2 \
  --cert ./certs/cert.pem --key ./certs/key.pem -k \
  -H 'Content-Type: application/json' -H 'Accept: application/json' \
  --data-binary @./outputs/reports/$AISL_SYSTEM_ID/llm-request.json \
  "$LLM_BASE_URL"
```

On non-2xx responses 0.4.3 reports the final URL, HTTP version, request byte size, request id (if returned), and response body excerpt.
