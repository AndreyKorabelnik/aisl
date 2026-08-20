# Analysis UI 2.0.0a61 — explicit Mermaid parsing and rendering

## Назначение

Версия устраняет непрозрачное исчезновение Mermaid-диаграмм в отчётах. Frontend больше не передаёт DOM-узлы в массовый `mermaid.run()`. Каждый diagram source явно валидируется и затем отдельно преобразуется в SVG.

## Что изменено

- перед рендерингом вызывается `mermaid.parse(source, { suppressErrors: false })`;
- SVG создаётся через `mermaid.render(uniqueId, source)`;
- `bindFunctions` применяется к готовому контейнеру, если Mermaid его вернул;
- каждый блок получает состояние `rendering`, `rendered` или `failed`;
- введён уникальный render ID для каждого блока и каждого цикла отображения;
- устаревший async-result не может перезаписать более новый отчёт;
- при ошибке показываются:
  - понятный заголовок;
  - ограниченное 500 символами сообщение parser/renderer;
  - исходный Mermaid-код;
- сообщение ошибки и source вставляются DOM API через `textContent`, без HTML-шаблона;
- modal/zoom для успешно построенных SVG сохранены;
- application-specific special cases не добавлялись.

## Совместимость

- API и backend contracts не изменены;
- `package.json` и `package-lock.json` не изменены;
- frontend source изменён, поэтому после обновления обязателен `npm run build`;
- `npm ci` не нужен, если существующий `frontend/node_modules` соответствует lock-файлу;
- старый frontend bundle не поддерживается как актуальный runtime: после установки исходников его необходимо пересобрать.

## Тесты

- `python -m compileall -q src tests`: passed;
- Mermaid/frontend/OpenAPI targeted suite: 37 passed;
- source manifest validation: passed;
- clean ZIP targeted suite: passed.

## Ограничение проверки

В текущем контейнере отсутствует `frontend/node_modules`, поэтому production `npm run build` здесь не выполнялся. Он обязателен в пользовательском окружении, где зависимости уже сохранены.
