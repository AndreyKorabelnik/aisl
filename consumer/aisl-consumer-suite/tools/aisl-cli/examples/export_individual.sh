#!/usr/bin/env bash
set -euo pipefail
: "${KNOWLEDGE_API_URL:?set KNOWLEDGE_API_URL}"
: "${AISL_SYSTEM_ID:?set AISL_SYSTEM_ID}"
aisl project data-model-object \
  --api-url "$KNOWLEDGE_API_URL" \
  --system-id "$AISL_SYSTEM_ID" \
  --profile data-model/v1 \
  --object com.sbt.bm.ucp.retail.model.individual.Individual \
  --output individual.json
