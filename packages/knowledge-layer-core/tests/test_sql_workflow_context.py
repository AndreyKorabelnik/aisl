from knowledge_layer_core.sql_workflow_context import (
    _literal_suffix,
    _match_known_files,
    _narrow_candidates_by_source_directory,
)


def test_bare_placeholder_after_underscore_keeps_only_stable_literal_suffix() -> None:
    template = "$datamart_dir/wf/dml_$load_type/epk_client/interim_epk_client_individual_stg.sql"
    known_files = {
        "hdfs/app/wf/dml_inc/epk_client/interim_epk_client_individual_stg.sql",
        "hdfs/app/wf/dml_arc/epk_client/interim_epk_client_individual_stg.sql",
        "hdfs/app/wf/dml_inc/other/interim_epk_client_individual_stg.sql",
    }

    assert _literal_suffix(template) == "epk_client/interim_epk_client_individual_stg.sql"
    candidates, basis = _match_known_files(template, known_files)

    assert candidates == [
        "hdfs/app/wf/dml_arc/epk_client/interim_epk_client_individual_stg.sql",
        "hdfs/app/wf/dml_inc/epk_client/interim_epk_client_individual_stg.sql",
    ]
    assert basis == "exact_literal_suffix_after_placeholder"


def test_source_directory_context_prevents_crossing_inc_and_arc_branches() -> None:
    candidates = [
        "hdfs/app/wf/dml_arc/epk_client/main.sql",
        "hdfs/app/wf/dml_inc/epk_client/main.sql",
    ]

    narrowed, applied = _narrow_candidates_by_source_directory(
        "hdfs/app/wf/dml_inc/epk_client/pipeline.json", candidates
    )

    assert narrowed == ["hdfs/app/wf/dml_inc/epk_client/main.sql"]
    assert applied is True


def test_source_without_shared_directory_keeps_all_branches() -> None:
    candidates = [
        "hdfs/app/wf/dml_arc/epk_client/pipeline.json",
        "hdfs/app/wf/dml_inc/epk_client/pipeline.json",
    ]

    narrowed, applied = _narrow_candidates_by_source_directory(
        "workflow/project/epk_client.yaml", candidates
    )

    assert narrowed == candidates
    assert applied is False


def test_context_binding_narrows_generic_prep_src_reference() -> None:
    from knowledge_layer_core.sql_workflow_context import _contextual_edge_targets

    candidates = [
        "hdfs/app/wf/dml/epk_client/prep_src.sql",
        "hdfs/app/wf/dml/epk_client_email/prep_src.sql",
    ]
    selected, status = _contextual_edge_targets(
        "$datamart_dir/wf/dml/$main_table_name/prep_src.sql",
        candidates,
        {"main_table_name": ["epk_client"]},
    )

    assert selected == ["hdfs/app/wf/dml/epk_client/prep_src.sql"]
    assert status == "resolved"


def test_context_binding_keeps_candidates_when_required_value_is_missing() -> None:
    from knowledge_layer_core.sql_workflow_context import _contextual_edge_targets

    candidates = [
        "hdfs/app/wf/dml/epk_client/prep_src.sql",
        "hdfs/app/wf/dml/epk_client_email/prep_src.sql",
    ]
    selected, status = _contextual_edge_targets(
        "$datamart_dir/wf/dml/$main_table_name/prep_src.sql",
        candidates,
        {},
    )

    assert selected == candidates
    assert status == "ambiguous"


def test_known_placeholder_after_unknown_placeholder_is_still_resolved() -> None:
    from knowledge_layer_core.sql_workflow_context import _resolve_template_value

    variants, unresolved = _resolve_template_value(
        "$datamart_dir/wf/dml/$main_table_name/prep_src.sql",
        {"main_table_name": ["epk_client"]},
    )

    assert variants == ["$datamart_dir/wf/dml/epk_client/prep_src.sql"]
    assert unresolved == ["datamart_dir"]


def test_context_binding_discovers_file_when_static_candidates_are_empty() -> None:
    from knowledge_layer_core.sql_workflow_context import _contextual_edge_targets

    selected, status = _contextual_edge_targets(
        "$datamart_dir/wf/dml/${$main_table_name}/${$main_table_name}.sql",
        [],
        {"main_table_name": ["epk_client"]},
        known_files={
            "hdfs/app/wf/dml/epk_client/epk_client.sql",
            "hdfs/app/wf/dml/epk_client_email/epk_client_email.sql",
        },
        source_file="hdfs/app/wf/dml/common/calc_stg.sql",
    )

    assert selected == ["hdfs/app/wf/dml/epk_client/epk_client.sql"]
    assert status == "resolved"


def test_unrelated_context_binding_does_not_resolve_empty_candidate_set() -> None:
    from knowledge_layer_core.sql_workflow_context import _contextual_edge_targets

    selected, status = _contextual_edge_targets(
        "$datamart_dir/wf/dml/${$main_table_name}/${$main_table_name}.sql",
        [],
        {"some_other_name": ["epk_client"]},
        known_files={"hdfs/app/wf/dml/epk_client/epk_client.sql"},
    )

    assert selected == []
    assert status == "unresolved"


def test_unknown_placeholder_inside_filename_preserves_exact_candidate_ambiguity() -> None:
    template = "$datamart_dir/wf/dml/t_link/pipeline_${load_type}.json"
    known_files = {
        "hdfs/app/wf/dml/t_link/pipeline_inc.json",
        "hdfs/app/wf/dml/t_link/pipeline_arc.json",
        "hdfs/app/wf/dml/other/pipeline_inc.json",
        "hdfs/app/wf/dml/t_link/other_inc.json",
    }

    candidates, basis = _match_known_files(template, known_files)

    assert candidates == [
        "hdfs/app/wf/dml/t_link/pipeline_arc.json",
        "hdfs/app/wf/dml/t_link/pipeline_inc.json",
    ]
    assert basis == "exact_template_structure:wf"


def test_whole_dynamic_directory_is_not_expanded_as_repository_wildcard() -> None:
    from knowledge_layer_core.sql_workflow_context import _match_known_files

    known = [
        "wf/dml/client/a.sql",
        "wf/dml/client/b.sql",
        "wf/dml/order/a.sql",
    ]
    matches, basis = _match_known_files("$root/wf/dml/${main_table}/${query}.sql", known)
    assert matches == []
    assert basis == "no_repository_local_exact_suffix"


def test_jinja_root_placeholder_preserves_literal_suffix_for_repository_file() -> None:
    template = "{{repo_root}}/path/to/conf/file.json"
    known_files = {"path/to/conf/file.json"}

    assert _literal_suffix(template) == "path/to/conf/file.json"
    candidates, basis = _match_known_files(template, known_files)

    assert candidates == ["path/to/conf/file.json"]
    assert basis == "exact_literal_suffix_after_placeholder"


def test_jinja_datamart_root_resolves_real_style_config_path_without_binding_value() -> None:
    template = "{{datamart_dir}}/etl/workflows/pa/conf/b2c_sql_config.json"
    known_files = {"etl/workflows/pa/conf/b2c_sql_config.json"}

    candidates, basis = _match_known_files(template, known_files)

    assert candidates == ["etl/workflows/pa/conf/b2c_sql_config.json"]
    assert basis == "exact_literal_suffix_after_placeholder"
