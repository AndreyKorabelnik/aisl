# UI split acceptance

Date: 2026-08-14

## Knowledge Base Generator
- KCP split/OpenAPI/frontend boundary targeted tests: **21 passed**.
- selected production-stage tests from Block A: **2 passed**.
- runtime-store / one-shot lifecycle follow-up after Assistant removal: **4 passed**.
- compile/import with `knowledge-assistant` physically absent from framework source: **PASS**.
- active KCP has no `/assistant-contexts`, `/chat`, Assistant runtime services, chat DB tables, `assistant_ready` stage, or `knowledge-assistant` package dependency.
- production terminates at published revision (plus optional report).
- full framework regression intentionally **not run**; the change is boundary-local and the user explicitly requested targeted testing unless broader regression is necessary.

## Standalone Knowledge Chat
- backend boundary/store/service/API tests: **5 passed**.
- targeted Knowledge Assistant tests: **10 passed**.
- clean consumer smoke using only `knowledge-chat + knowledge-assistant + knowledge-integration + evidence-common`, a fake remote Knowledge API and fake model: **PASS**.
- the clean consumer smoke had no Knowledge Control Plane, Core, Runner, KLC, source repository or production workspace on its import path.
- frontend npm lock validation: **PASS**.
- frontend production build: **NOT PASS / not completed**. Offline `npm ci` lacked cached `vue-tsc`; a bounded normal npm attempt did not complete within the execution limit. No functional PASS is claimed for the frontend build.

## Not yet validated
- real Knowledge Chat against a corporate published Knowledge API revision and real LLM endpoint.
- frontend production build in a normal npm-connected environment.
- live corporate Bitbucket Project acceptance for bulk repository processing remains a separate task from this UI split.
