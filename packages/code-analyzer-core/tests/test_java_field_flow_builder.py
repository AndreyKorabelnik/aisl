from pathlib import Path
from code_analyzer_core.scanners.java_flow_builder import build_java_data_flow_facts


def _write(tmp_path: Path, rel: str, text: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_field_flow_for_whole_object_http_payload(tmp_path: Path):
    p = _write(tmp_path, "CardService.java", """
        class CardInfoByPanRq {
            private String cardNumber;
            private String rqUid;
            private String stateCode;
        }
        class CardService {
            public void send(CardInfoByPanRq request) {
                restTemplate.postForObject(CARD_LIFE_CYCLE_URL, request, String.class);
            }
        }
    """)
    facts, status = build_java_data_flow_facts([p])
    field_facts = [f for f in facts if f.fact_type == "field_identifier_flow"]
    fields = {f.properties["source_field"] for f in field_facts}
    assert "cardNumber" in fields
    assert "rqUid" in fields
    assert all(f.properties["related_flow_id"].startswith("flow_") for f in field_facts)
    assert status["field_flows_extracted"] >= 2


def test_field_flow_for_getter_payload(tmp_path: Path):
    p = _write(tmp_path, "Publisher.java", """
        class PhoneBlockResyncEvent {
            private String phoneNumber;
            public String getPhoneNumber() { return phoneNumber; }
        }
        class Publisher {
            public void sendMessages(PhoneBlockResyncEvent event) {
                kafkaTemplate.send(topic, event.getPhoneNumber());
            }
        }
    """)
    facts, status = build_java_data_flow_facts([p])
    field_facts = [f for f in facts if f.fact_type == "field_identifier_flow"]
    assert field_facts
    ff = field_facts[0]
    assert ff.properties["source_field"] == "phoneNumber"
    assert ff.properties["trace_status"] == "confirmed"
