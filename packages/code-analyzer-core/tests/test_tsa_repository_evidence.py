import json

from code_analyzer_core import __version__ as CORE_VERSION
from pathlib import Path

from code_analyzer_core.models import AnalysisResult, EvidenceRef, Fact
from code_analyzer_core.prepared_artifacts.source_observation_fact_store import write_source_observation_fact_store
from code_analyzer_core.tsa_interpreter import interpret_tsa_facts


def _fact(fact_type: str, name: str, **properties):
    return Fact(
        fact_type=fact_type,
        name=name,
        properties=properties,
        evidence=[EvidenceRef(file_path="src/main/java/Sample.java", line_start=1, extractor="test")],
    )


def test_tsa_observations_are_persisted_in_uncapped_repository_store(tmp_path: Path):
    sources = [
        _fact("code_annotation", "MetaRootEntity", annotation="MetaRootEntity", owner_fqcn="a.Root", observation_id="ann-1"),
        _fact("java_method_call_observation", "referenceField", method="referenceField", owner_fqcn="a.Converter", observation_id="call-1"),
        _fact("call_argument_flow_observation", "arg", call_observation_id="call-1", argument_index=0, source_expression="source.getId()", input_symbols=["source.getId"]),
    ]
    tsa_facts, status = interpret_tsa_facts(sources)
    result = AnalysisResult(system_name="s", project_code="p", repo_path=".", stack=[], files_analyzed=1)
    manifest_status = write_source_observation_fact_store(result=result, facts_dir=tmp_path, additional_facts=[*sources, *tsa_facts])

    assert status["observations_emitted"] == 2
    assert manifest_status["fact_type_counts"]["tsa_annotation_observation"] == 1
    assert manifest_status["fact_type_counts"]["tsa_reference_operation_observation"] == 1
    manifest = json.loads((tmp_path / "full_fact_manifest.json").read_text())
    assert manifest["producer"]["version"] == CORE_VERSION
    assert manifest["semantic_policy"]["key_classification_performed"] is False


def test_tsa_reference_value_derivation_is_persisted_in_repository_store(tmp_path: Path):
    from code_analyzer_core.scanners.java_source_observations import build_java_source_observation_facts

    source_path = tmp_path / "src/main/java/example/Converter.java"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        '''package example;
        class Converter {
          Object convert(Address address, Builder ceb) {
            ceb.alias("example.Address");
            ceb.referenceField("country", convertCountry(address.getCountry()));
            return null;
          }
          String convertCountry(Country country) {
            return "Country_" + country.getCode();
          }
        }
        ''',
        encoding="utf-8",
    )
    generic_facts, _ = build_java_source_observation_facts([source_path])
    tsa_facts, _ = interpret_tsa_facts(generic_facts)
    result = AnalysisResult(system_name="s", project_code="p", repo_path=".", stack=[], files_analyzed=1)
    manifest_status = write_source_observation_fact_store(
        result=result,
        facts_dir=tmp_path / "facts",
        additional_facts=[*generic_facts, *tsa_facts],
    )

    assert manifest_status["fact_type_counts"]["tsa_reference_value_derivation_observation"] == 1
    rows = (tmp_path / "facts" / "full_by_type" / "tsa_reference_value_derivation_observation.jsonl").read_text().splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["properties"]["relationship_field"] == "country"
    assert payload["properties"]["composed_reference_value_expression"] == '"Country_" + address.getCountry().getCode()'


def test_generic_storage_record_and_reference_are_persisted(tmp_path: Path):
    from code_analyzer_core.scanners.java_source_observations import build_java_source_observation_facts

    source_path = tmp_path / "src/main/java/example/Converter.java"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        '''package example;
        class Converter {
          Object convert(Parent parent, Writer parentWriter) {
            String reference = makeChild(parent.child(), "child", "Parent_" + parent.id());
            parentWriter.referenceField("child", reference);
            return null;
          }
          String makeChild(Child child, String segment, String parentKey) {
            String recordKey = parentKey + "." + segment;
            Writer writer = createWriter();
            writer.alias("example.Child");
            writer.key(recordKey);
            return recordKey;
          }
          Writer createWriter() { return null; }
        }
        ''',
        encoding="utf-8",
    )
    generic_facts, _ = build_java_source_observation_facts([source_path])
    interpreted, _ = interpret_tsa_facts(generic_facts)
    result = AnalysisResult(system_name="s", project_code="p", repo_path=".", stack=[], files_analyzed=1)
    status = write_source_observation_fact_store(
        result=result,
        facts_dir=tmp_path / "facts",
        additional_facts=[*generic_facts, *interpreted],
    )

    assert status["fact_type_counts"]["storage_record_observation"] == 1
    assert status["fact_type_counts"]["storage_reference_observation"] == 1
    reference_row = json.loads(
        (tmp_path / "facts/full_by_type/storage_reference_observation.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert reference_row["properties"]["target_alias"] == "example.Child"
    assert reference_row["properties"]["target_storage_key_field"] == "key"
    assert reference_row["properties"]["physical_encoding"] == "downstream_interpretation_required"
