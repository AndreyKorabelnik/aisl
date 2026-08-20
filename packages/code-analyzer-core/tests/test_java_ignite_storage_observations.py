from pathlib import Path

from code_analyzer_core.scanners.java_call_observations import _build_method_index, _build_storage_facts


def test_ignite_cache_calls_publish_read_write_and_cache_name_facts(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main" / "java" / "demo" / "IgniteAccess.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        '''
        class IgniteClient { Cache cache(String name) { return null; } }
        class Cache {
          Object get(Object key) { return null; }
          void put(Object key, Object value) {}
        }
        class CloudIgniteWriterAdapter { void writeRecord(WalRecord record, Object metadata) {} }
        class WalRecord {}
        class IgniteAccess {
          IgniteClient iClient;
          CloudIgniteWriterAdapter writerAdapter;
          Object load(String cacheName, String key) {
            return iClient.cache(cacheName).get(key);
          }
          void save(String cacheName, String key, Object data) {
            iClient.cache(cacheName).put(key, data);
          }
          void forward(WalRecord record) {
            writerAdapter.writeRecord(record, null);
          }
        }
        ''',
        encoding="utf-8",
    )

    methods, _class_fields, _class_infos, warnings = _build_method_index([src])
    assert warnings == []
    accesses = _build_storage_facts(methods)
    ignite = [a for a in accesses if a.get("storage_kind") == "ignite_cache"]

    read = next(a for a in ignite if a["operation"] == "IgniteAccess.load" and a["storage_method"] == "get")
    assert read["access_kind"] == "read"
    assert read["cache_name_expression"] == "cacheName"
    assert read["cache_name_basis"] == "nested_ignite_cache_call_argument"
    assert read["receiver_declared_type"] == "IgniteClient"
    assert read["payload_expression"] == "key"

    write = next(a for a in ignite if a["operation"] == "IgniteAccess.save" and a["storage_method"] == "put")
    assert write["access_kind"] == "write"
    assert write["cache_name_expression"] == "cacheName"
    assert write["payload_expression"] == "data"

    adapter = next(a for a in ignite if a["operation"] == "IgniteAccess.forward")
    assert adapter["operation_kind"] == "ignite_cache_write"
    assert adapter["receiver_declared_type"] == "CloudIgniteWriterAdapter"
    assert adapter["payload_expression"] == "record"
