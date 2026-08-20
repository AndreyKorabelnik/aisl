# knowledge-integration 0.1.8

- Added generic `get_knowledge_item` binding for the universal AISL exact-item read endpoint.
- The tool is revision-pinned and available as a base AISL read operation rather than a domain capability.
- Added consumer policy rules: universal read is verification, not semantic discovery; `unsupported`/`not_available` never prove absence; vector candidates require exact AISL verification before factual use.
- Bumped canonical tool catalog version to 2.
