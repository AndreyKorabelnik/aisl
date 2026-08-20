# static-analysis-runner 0.9.32

## HTTP Islands end-to-end

- завершён пользовательский сценарий `portfolio-topology` от последовательного анализа репозиториев до итогового `portfolio-interaction-islands.json`;
- Runner проверяет и публикует результат `portfolio_interaction_islands/v1` от Knowledge Layer Core;
- в итоговый JSON добавлены фактические статусы загрузки/анализа каждого репозитория, общий run status и run fingerprint;
- поддержан канонический статус KLC `complete`;
- persistent repository shard сокращён до compact interface catalog и минимального repository manifest;
- из persistent shard удалены временные пути clone, analysis output и локальной установки Runner/Core;
- сохранены partial failures: ошибка одного репозитория не блокирует topology assembly.

## Реальный E2E

На четырёх реальных приложениях получены 3 HTTP-зависимости и 8 matched/probable boundary interactions. Strict topology содержит 4 отдельных компонента, extended topology — один остров из 4 репозиториев.
