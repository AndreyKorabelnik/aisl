from importlib.resources import files


def _prompt() -> str:
    return files("aisl_reporting.profiles.workspace_interaction.v1").joinpath("renderer-prompt.md").read_text(encoding="utf-8")


def _contract() -> str:
    return files("aisl_reporting.profiles.workspace_interaction.v1").joinpath("report-contract.yaml").read_text(encoding="utf-8")


def test_workspace_prompt_is_boundary_interaction_centric_and_excludes_parked_value_flow():
    prompt = _prompt()
    assert "source outbound → target inbound" in prompt
    assert "Generic build dependency" in prompt
    assert "Не используй их вместо `business_interactions`" in prompt
    assert "execution context — дополнительный локальный контекст" in prompt
    assert "Direct value-flow graph и attribute-path resolution не входят" in prompt
    for forbidden in ("required_card_count", "required_wire_paths", "probable_complete", "target_local_continuation", "source_local_variant_count"):
        assert forbidden not in prompt


def test_workspace_prompt_requires_active_interaction_report_composition():
    prompt = _prompt()
    contract = _contract()
    headings = [
        "Краткий вывод",
        "Бизнесовая картина контура",
        "Роли систем",
        "Основные бизнес-взаимодействия",
        "Какие данные проходят через контур",
        "Архитектурные выводы",
        "Приложение A. Полнота анализа и ограничения доказательности",
        "Приложение B. Неоднозначности и вопросы для уточнения",
        "Приложение C. Технические доказательства и provenance",
    ]
    for heading in headings:
        assert heading in prompt
        assert heading in contract
    assert "Истории движения атрибутов" not in contract


def test_workspace_prompt_preserves_evidence_and_confidence_discipline():
    prompt = _prompt()
    assert "Сохраняй `confirmed`, `probable`, `ambiguous`, `unresolved`" in prompt
    assert "Не выдумывай evidence ID" in prompt
    assert "Не утверждай отсутствие хранения" in prompt
    assert "Counts — диагностические технические записи" in prompt


def test_workspace_prompt_and_plan_exclude_parked_topology_and_value_flow():
    prompt = _prompt()
    plan = files("aisl_reporting.profiles.workspace_interaction.v1").joinpath("dataset-plan.yaml").read_text(encoding="utf-8")
    assert "strict_island" not in prompt.casefold()
    assert "extended_island" not in prompt.casefold()
    assert "repository_interaction_islands" not in plan
    assert "repository_value_flow" not in plan
    assert "resolve_attribute_paths" not in plan
