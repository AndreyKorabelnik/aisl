# Analysis UI 2.0.0a69 — Assistant 0.17.1 synchronization and revision-chat profile

- Updated the package dependency to `knowledge-assistant>=0.17.1,<0.18.0`.
- Revision-pinned chat continues to use `KnowledgeApiAssistantTools` over one immutable revision.
- The complete packaged `attribute-addition-plan/v1` profile is now loaded for revision chat as well as cross-system chat.
- Profile absence is an explicit 503 error; no shortened policy or fallback is used.
- Diagnostics publish the canonical profile ID/version/fingerprint separately from the UI context-instruction profile.
- Backend/frontend versions synchronized at 2.0.0a69 / 2.0.0-alpha.69.
