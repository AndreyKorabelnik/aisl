import json
from pathlib import Path

from code_analyzer_core.models import AnalysisResult
from code_analyzer_core.navigation import build_navigation
from code_analyzer_core.scanners.java_field_flow_builder import build_java_field_flow_facts
from code_evidence.commands import field_flow_edge, field_flow_neighborhood, field_flow_occurrence


def test_materialized_neighborhood_returns_catalog_details(tmp_path: Path):
    repo = tmp_path / "repo"
    src = repo / "src/main/java/Mapper.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        """
        class Mapper {
            void map(Request request, TargetBuilder builder) {
                String value = request.getValue();
                if (value != null) {
                    builder.value(value);
                }
            }
        }
        """,
        encoding="utf-8",
    )
    facts, _ = build_java_field_flow_facts([src], repository_id="repo", repository_root=repo)
    result = AnalysisResult(system_name="system", project_code="P", repo_path=str(repo), facts=facts)
    out = tmp_path / "analysis-output"
    build_navigation(result, out)

    index = json.loads((out / "compact" / "field_flow_index.json").read_text(encoding="utf-8"))
    start = next(x["occurrence_id"] for x in index if x.get("field_path") == "request.value")
    neighborhood = field_flow_neighborhood(out, start, direction="out", max_depth=3, max_nodes=20)

    assert neighborhood["node_count"] >= 3
    assert any(x.get("field_path") == "builder.value" for x in neighborhood["occurrences"])
    builder_edge = next(x for x in neighborhood["edges"] if x.get("edge_kind") == "builder_argument")
    assert "value != null" in builder_edge["guards"][0]["expression_text"]
    assert (out / "catalog" / "field_occurrences.json").exists()
    assert (out / "catalog" / "field_flow_edges.json").exists()
    assert field_flow_occurrence(out, "request.value")["hit_count"] >= 1
    assert field_flow_edge(out, builder_edge["edge_id"])["hit_count"] == 1
