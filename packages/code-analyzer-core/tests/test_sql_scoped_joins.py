import json
from pathlib import Path

from tests.sql_evidence_test_support import run_sql_evidence


from tests.sql_evidence_test_support import read_sql_output


def _read(path: Path):
    return read_sql_output(path)


def _analyze(tmp_path: Path, sql: str):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "model.sql").write_text(sql, encoding="utf-8")
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="scoped_joins",
    )
    return _read(out / "compact/sql_join_edge.json")


def test_left_join_extracts_key_and_additional_predicate(tmp_path: Path) -> None:
    joins = _analyze(
        tmp_path,
        """
        SELECT a.id
        FROM src.a a
        LEFT JOIN src.b b
          ON a.id = b.a_id
         AND b.valid_to > current_date();
        """,
    )

    assert len(joins) == 1
    join = joins[0]
    assert join["join_type"] == "left"
    assert join["condition_kind"] == "on"
    assert join["left_relation_names"] == ["src.a"]
    assert join["right_relation_name"] == "src.b"
    assert join["resolution_status"] == "confirmed"
    assert join["physical_join_confirmed"] is True
    assert [
        (item["left_relation_name"], item["left_column"], item["right_relation_name"], item["right_column"], item["operator"])
        for item in join["column_pairs"]
    ] == [("src.a", "id", "src.b", "a_id", "=")]
    assert join["additional_predicates"] == ["b.valid_to > CURRENT_DATE"]
    assert join["temporal_or_range_predicates"] == ["b.valid_to > CURRENT_DATE"]


def test_range_join_preserves_every_column_pair(tmp_path: Path) -> None:
    joins = _analyze(
        tmp_path,
        """
        SELECT a.id
        FROM src.events a
        JOIN src.periods b
          ON a.event_dt >= b.start_dt
         AND a.event_dt < b.end_dt;
        """,
    )

    join = joins[0]
    assert {
        (item["left_column"], item["right_column"], item["operator"], item["predicate_role"])
        for item in join["column_pairs"]
    } == {
        ("event_dt", "start_dt", ">=", "range_or_temporal"),
        ("event_dt", "end_dt", "<", "range_or_temporal"),
    }
    assert set(join["temporal_or_range_predicates"]) == {
        "a.event_dt >= b.start_dt",
        "a.event_dt < b.end_dt",
    }
    assert join["resolution_status"] == "confirmed"


def test_using_join_builds_canonical_column_pair(tmp_path: Path) -> None:
    join = _analyze(
        tmp_path,
        "SELECT a.value FROM src.a a JOIN src.b b USING (id);",
    )[0]

    assert join["join_type"] == "inner"
    assert join["condition_kind"] == "using"
    assert join["using_columns"] == ["id"]
    assert join["column_pairs"] == [
        {
            "left_column_usage_id": None,
            "left_relation_id": join["left_relation_id"],
            "left_relation_candidate_ids": [],
            "left_relation_name": "src.a",
            "left_relation_candidate_names": [],
            "left_column": "id",
            "right_column_usage_id": None,
            "right_relation_id": join["right_relation_id"],
            "right_relation_name": "src.b",
            "right_column": "id",
            "operator": "=",
            "predicate": "USING (id)",
            "predicate_role": "equality_key",
            "resolution_status": "confirmed",
        }
    ]
    assert join["resolution_status"] == "confirmed"
    assert join["physical_join_confirmed"] is True


def test_cross_join_is_confirmed_without_predicate(tmp_path: Path) -> None:
    join = _analyze(
        tmp_path,
        "SELECT a.id, b.code FROM src.a a CROSS JOIN src.b b;",
    )[0]

    assert join["join_type"] == "cross"
    assert join["condition_kind"] == "cross"
    assert join["predicate"] is None
    assert join["column_pairs"] == []
    assert join["resolution_status"] == "confirmed"
    assert join["physical_join_confirmed"] is True


def test_second_join_uses_relations_from_its_own_predicate(tmp_path: Path) -> None:
    joins = _analyze(
        tmp_path,
        """
        SELECT a.id
        FROM src.a a
        JOIN src.b b ON a.id = b.a_id
        JOIN src.c c ON b.id = c.b_id;
        """,
    )

    assert len(joins) == 2
    second = joins[1]
    assert second["left_relation_names"] == ["src.b"]
    assert second["right_relation_name"] == "src.c"
    assert {
        (item["left_relation_name"], item["right_relation_name"])
        for item in second["column_pairs"]
    } == {("src.b", "src.c")}


def test_cte_join_is_logically_confirmed_but_not_physical(tmp_path: Path) -> None:
    joins = _analyze(
        tmp_path,
        """
        WITH prepared AS (
            SELECT id FROM src.a
        )
        SELECT p.id
        FROM prepared p
        JOIN src.b b ON p.id = b.id;
        """,
    )

    join = joins[0]
    assert join["left_relation_names"] == ["prepared"]
    assert join["right_relation_name"] == "src.b"
    assert join["resolution_status"] == "confirmed"
    assert join["physical_join_confirmed"] is False


def test_unqualified_ambiguous_join_predicate_stays_partial(tmp_path: Path) -> None:
    join = _analyze(
        tmp_path,
        "SELECT * FROM src.a a JOIN src.b b ON id = b.id;",
    )[0]

    assert join["right_relation_name"] == "src.b"
    assert join["column_pairs"][0]["resolution_status"] == "partial"
    assert join["resolution_status"] == "partial"
    assert join["resolution_reasons"] == ["predicate_column_unresolved_or_ambiguous"]
    assert join["physical_join_confirmed"] is False


def test_using_after_multiple_left_relations_does_not_invent_base_pair(tmp_path: Path) -> None:
    joins = _analyze(
        tmp_path,
        "SELECT * FROM src.a a JOIN src.b b ON a.id = b.a_id JOIN src.c c USING (id);",
    )

    second = joins[1]
    assert second["left_relation_id"] is None
    assert second["left_relation_names"] == ["src.a", "src.b"]
    assert len(second["column_pairs"]) == 1
    pair = second["column_pairs"][0]
    assert pair["left_relation_id"] is None
    assert set(pair["left_relation_candidate_names"]) == {"src.a", "src.b"}
    assert pair["resolution_status"] == "partial"
    assert second["resolution_status"] == "partial"
    assert second["resolution_reasons"] == ["using_left_relation_ambiguous"]
    assert second["physical_join_confirmed"] is False


def test_reversed_predicate_is_canonicalized_to_join_sides(tmp_path: Path) -> None:
    join = _analyze(
        tmp_path,
        "SELECT a.id FROM src.a a JOIN src.b b ON b.a_id = a.id;",
    )[0]

    pair = join["column_pairs"][0]
    assert pair["left_relation_name"] == "src.a"
    assert pair["left_column"] == "id"
    assert pair["right_relation_name"] == "src.b"
    assert pair["right_column"] == "a_id"


def test_same_relation_comparison_is_additional_predicate_not_join_key(tmp_path: Path) -> None:
    join = _analyze(
        tmp_path,
        "SELECT a.id FROM src.a a JOIN src.b b ON a.id = b.a_id AND b.start_dt < b.end_dt;",
    )[0]

    assert len(join["column_pairs"]) == 1
    assert join["column_pairs"][0]["predicate"] == "a.id = b.a_id"
    assert join["additional_predicates"] == ["b.start_dt < b.end_dt"]
    assert join["temporal_or_range_predicates"] == ["b.start_dt < b.end_dt"]
    assert join["resolution_status"] == "confirmed"


def test_expression_join_links_relations_without_inventing_single_column_pair(tmp_path: Path) -> None:
    join = _analyze(
        tmp_path,
        """
        SELECT em.id
        FROM prepared em
        LEFT JOIN src.subtype st
          ON substring(coalesce(em.subtype, em.fallback_subtype), 2) = st.key;
        """,
    )[0]

    assert join["column_pairs"] == []
    assert len(join["expression_links"]) == 1
    link = join["expression_links"][0]
    assert link["left_relation_names"] == ["prepared"]
    assert link["right_relation_names"] == ["src.subtype"]
    assert {item["column"] for item in link["left_columns"]} == {"subtype", "fallback_subtype"}
    assert {item["column"] for item in link["right_columns"]} == {"key"}
    assert link["predicate_role"] == "equality_expression"
    assert link["resolution_status"] == "confirmed"
    assert join["resolution_status"] == "confirmed"
