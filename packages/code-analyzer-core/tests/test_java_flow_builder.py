from pathlib import Path

from code_analyzer_core.scanners.java_flow_builder import build_java_data_flow_facts


def test_method_parameter_to_kafka_payload_via_serialization(tmp_path: Path):
    src = tmp_path / "Publisher.java"
    src.write_text(
        """
        public class Publisher {
          public <T> void sendMessages(T object) {
            kafkaTemplate.send(topic, dtoToString(object));
          }
        }
        """,
        encoding="utf-8",
    )

    facts, status = build_java_data_flow_facts([src])

    assert status["flows_extracted"] == 1
    flow = facts[0]
    assert flow.fact_type == "source_to_sink_flow"
    assert flow.properties["flow_id"] == "flow_000001"
    assert flow.properties["source_parameter"] == "object"
    assert flow.properties["sink_kind"] == "kafka"
    assert flow.properties["serialization_kind"] == "dtoToString"
    assert flow.properties["payload_expression"] == "dtoToString(object)"


def test_unrelated_send_without_parameter_is_ignored(tmp_path: Path):
    src = tmp_path / "Publisher.java"
    src.write_text(
        """
        public class Publisher {
          public void sendMessages(Object object) {
            kafkaTemplate.send(topic, staticPayload);
          }
        }
        """,
        encoding="utf-8",
    )

    facts, status = build_java_data_flow_facts([src])

    assert facts == []
    assert status["flows_extracted"] == 0
