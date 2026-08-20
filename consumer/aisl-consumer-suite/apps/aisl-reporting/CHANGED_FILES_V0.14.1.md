# Changed files — aisl-reporting 0.14.1

- `aisl_reporting/deterministic_er.py` — новый детерминированный генератор ER и observed-usage Mermaid.
- `aisl_reporting/pipeline.py` — замена LLM-authored ER section детерминированным фрагментом до normalization/validation.
- `aisl_reporting/version.py` — версия 0.14.1.
- `pyproject.toml` — версия 0.14.1.
- `tests/test_deterministic_er.py` — physical/logical/observed Mermaid, sanitization и сохранение остальных разделов.
- `tests/test_pipeline_soft_validation.py` — детерминированная ER как основной путь, correction pass как fallback.
- `RELEASE_NOTES_V0.14.1.md`.
- `TEST_STATUS_DETERMINISTIC_MERMAID_V0.14.1.md`.
- `SOURCE_TREE_MANIFEST.sha256`.
