from importlib.resources import files

from aisl_reporting.profiles.reference_data.v1 import builder as reference_builder
from aisl_reporting.profiles.system_description.v1 import builder as system_builder
from aisl_reporting.profiles.workspace_interaction.v1 import builder as interaction_builder


def _relationship(index: int) -> dict:
    return {
        "left_table": f"schema.left_{index:03d}",
        "right_table": f"schema.right_{index:03d}",
        "join_type": "foreign_key",
        "column_pairs": [
            {
                "left_column": "id",
                "operator": "=",
                "right_column": "parent_id",
            }
        ],
    }


def _prompt(package: str) -> str:
    return files(package).joinpath("renderer-prompt.md").read_text(encoding="utf-8")


def test_system_description_keeps_every_explicit_relationship_when_catalog_has_at_most_30():
    explicit = [_relationship(index) for index in range(27)]
    observed = [{**_relationship(index), "join_type": "observed_join"} for index in range(50)]

    selected_explicit, selected_observed, metadata = system_builder._select_report_relationships(
        explicit,
        observed,
        "standard",
    )

    assert selected_explicit == explicit
    assert selected_observed == observed[:20]
    assert metadata == {
        "explicit_relationship_selection_limit": 27,
        "observed_join_selection_limit": 20,
        "all_explicit_relationships_selected": True,
        "explicit_relationship_selection_policy": "all_explicit_relationships_when_count_at_most_30/v1",
    }


def test_system_description_uses_deterministic_detail_budget_for_large_relationship_catalog():
    explicit = [_relationship(index) for index in range(45)]

    selected_explicit, selected_observed, metadata = system_builder._select_report_relationships(
        explicit,
        [],
        "standard",
    )

    assert selected_explicit == explicit[:30]
    assert selected_observed == []
    assert metadata["all_explicit_relationships_selected"] is False
    assert metadata["explicit_relationship_selection_limit"] == 30
    assert metadata["explicit_relationship_selection_policy"] == (
        "ranked_explicit_relationships_with_detail_level_budget/v1"
    )


def test_interaction_and_reference_data_profiles_have_richer_detail_budgets():
    assert interaction_builder._DETAIL_LIMITS == {
        "executive": {"fields": 12, "interactions": 20},
        "standard": {"fields": 40, "interactions": 60},
        "detailed": {"fields": 120, "interactions": 200},
    }
    assert reference_builder._DETAIL_LIMITS == {
        "executive": 12,
        "standard": 40,
        "detailed": 100,
    }
    assert reference_builder._USAGE_SAMPLE_LIMITS == {
        "executive": 4,
        "standard": 12,
        "detailed": 30,
    }


def test_rich_report_prompts_require_named_evidence_before_appendix_limitations():
    system_prompt = _prompt("aisl_reporting.profiles.system_description.v1")
    interaction_prompt = _prompt("aisl_reporting.profiles.workspace_interaction.v1")
    persistence_prompt = _prompt("aisl_reporting.profiles.foreign_data_persistence.v1")
    reference_prompt = _prompt("aisl_reporting.profiles.reference_data.v1")

    assert "all_explicit_relationships_selected=true" in system_prompt
    assert "не менее 15 объектов" in system_prompt
    assert "не менее 8 конкретных interactions" in interaction_prompt
    assert "не менее 15 конкретных wire paths" in interaction_prompt
    assert "не менее 10 storage objects/fields" in persistence_prompt
    assert "все cases" in persistence_prompt
    assert "не менее 20 кандидатов" in reference_prompt
    assert "complete_candidate_catalog" in reference_prompt

    for prompt in (system_prompt, interaction_prompt, persistence_prompt, reference_prompt):
        assert "Приложение A. Полнота анализа и ограничения доказательности" in prompt
        assert "Приложение B. Неоднозначности и вопросы для уточнения" in prompt
        assert "Приложение C. Технические доказательства и provenance" in prompt


def test_reference_data_candidate_representation_basis_is_factual() -> None:
    literal = reference_builder._candidate({
        "representation_kind": "literal_populated_storage_target",
        "name": "placeholder.terbank",
        "source_set": "unknown",
    })
    assert literal["observed_maintenance_signals"] == ["literal_population_observed"]
    assert "Literal INSERT" in literal["candidate_basis"]
    assert literal["official_nsi_status"] == "not_established"
    assert literal["human_validation_required"] is True

    declared = reference_builder._candidate({
        "representation_kind": "declared_value_set",
        "name": "CardStatus",
        "source_set": "production",
    })
    assert declared["observed_maintenance_signals"] == ["embedded_in_code_or_config"]
    assert declared["official_nsi_status"] == "not_established"


def test_reference_data_report_budget_policy_preserves_prompt_minima():
    # The rich limits are upper bounds. Real datasets may deterministically trim
    # duplicated detail while preserving the full compact catalog and prompt minima.
    assert reference_builder._DETAIL_LIMITS["detailed"] >= 20
    assert reference_builder._USAGE_SAMPLE_LIMITS["detailed"] >= 10
