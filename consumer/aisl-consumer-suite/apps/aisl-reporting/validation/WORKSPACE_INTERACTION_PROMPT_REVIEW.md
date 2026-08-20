# Workspace interaction business report — prompt review

## Compared inputs

- Former canonical prompt: `llm-prompts 0.31.0 / workspace-system-interaction-business-report`.
- Previous reporting profile: `aisl-reporting 0.11.0 / workspace-interaction/v1`.
- Replacement profile: `aisl-reporting 0.12.0 / workspace-interaction/v1`.

## Finding

The former canonical prompt was materially stronger than the 0.11.0 renderer in business composition. It required an executive conclusion, contour description, system roles, operation cards, exchanged data, architecture observations, attribute examples, agent questions, owner questions, evidence quality and a technical appendix.

The 0.11.0 dataset also used generic cross-repository correspondences and data-model relationships as the main interaction substrate. Those records are not sufficient proof of runtime system interaction and do not use the canonical boundary/transport model introduced in current KLC.

## Replacement

Version 0.12.0 keeps the former business-first composition but grounds it in the current evidence model:

- source outbound → target inbound boundary interactions;
- protocol, HTTP method and endpoint;
- source/target operations and payload types;
- field contracts and data groups;
- transport value-flow edges;
- bounded attribute-path resolver results;
- execution context as optional local context;
- confirmed/probable confidence preservation;
- coverage and diagnostics;
- repository-relative evidence.

Generic type/configuration correspondence is explicitly excluded from the definition of runtime interaction.

## Required report sections

1. Краткий вывод
2. Бизнесовая картина контура
3. Роли систем
4. Основные бизнес-взаимодействия
5. Какие данные проходят через контур
6. Архитектурные выводы
7. Истории движения атрибутов
8. Что можно спросить у агента
9. Открытые вопросы
10. Качество доказательств и ограничения
11. Техническое приложение

## Real-workspace validation

Two-repository lightweight workspace:

- repositories: 2;
- boundary interactions: 1 probable;
- field contracts: 7;
- transport edges: 7;
- selected attribute journeys: 5, all `probable_complete`;
- portable evidence entries: 12.

Four-repository workspace:

- repositories: 4;
- boundary interactions: 8;
- field contracts: 231;
- transport edges: 231;
- selected attribute journeys: 5, all `probable_complete`;
- portable evidence entries: 21;
- deterministic dataset preparation: 11.61 seconds.

An initial implementation resolved every candidate field contract and exceeded a five-minute external timeout on the four-repository workspace. Version 0.12.0 ranks candidates first and invokes the resolver only for a deterministic bounded shortlist. The visible report still contains at most five representative journeys.

## Scope of validation

The deterministic dataset, renderer prompt and report contract were validated. No external LLM endpoint was invoked during the release validation, so prose quality of a specific model response remains a separate runtime check.
