from aisl_reporting.mermaid import normalize_mermaid_markdown, normalize_mermaid_source


def test_normalizes_system_boundary_flowchart_from_real_report():
    source = '''flowchart LR
    rest_clients[«REST-клиенты»] --> |REST Request: 35| scope[«Client Profile»]
    scope --> |HTTP Outbound: 7| http_out[«Внешние HTTP-сервисы»]'''
    normalized = normalize_mermaid_source(source)
    assert 'rest_clients["«REST-клиенты»"] -->|REST Request: 35| scope["«Client Profile»"]' in normalized
    assert 'scope -->|HTTP Outbound: 7| http_out["«Внешние HTTP-сервисы»"]' in normalized


def test_normalizes_dotted_er_entity_names_from_real_report():
    source = '''erDiagram
    mbk_cache.card ||--o{ mbk_cache.link : "cardid = paymentcardid (jooq_join)"
    mbk_cache.link ||--o{ mbk_cache.phone : "phoneid = phoneid (jooq_join)"'''
    normalized = normalize_mermaid_source(source)
    assert '"mbk_cache.card" ||--o{ "mbk_cache.link"' in normalized
    assert '"mbk_cache.link" ||--o{ "mbk_cache.phone"' in normalized


def test_preserves_valid_mermaid_and_reports_changed_count():
    markdown = '''Before
```mermaid
flowchart LR
    A["Already quoted"] -->|ok| B["Done"]
```
After'''
    normalized, result = normalize_mermaid_markdown(markdown)
    assert normalized == markdown
    assert result.block_count == 1
    assert result.changed_block_count == 0


def test_normalizes_multiple_blocks_in_markdown():
    markdown = '''```mermaid
flowchart LR
    A[Начало] --> |go| B[Конец]
```
```mermaid
erDiagram
    s.table ||--o{ s.other : "joins"
```'''
    normalized, result = normalize_mermaid_markdown(markdown)
    assert result.block_count == 2
    assert result.changed_block_count == 2
    assert 'A["Начало"] -->|go| B["Конец"]' in normalized
    assert '"s.table" ||--o{ "s.other"' in normalized
