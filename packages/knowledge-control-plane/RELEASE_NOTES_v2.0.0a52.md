# Analysis UI 2.0.0a52

## Серверная аутентификация Bitbucket

Логин и пароль/token Bitbucket полностью удалены из пользовательского интерфейса.

Analysis UI использует только переменные окружения backend:

- `BITBUCKET_USERNAME`;
- `BITBUCKET_TOKEN`;
- либо `BITBUCKET_ACCESS_TOKEN`.

Поля аутентификации отсутствуют во всех формах, включая составной мастер подготовки контекста для добавления атрибута.

## API-контракт

Repository discovery больше не принимает объект `auth` в HTTP-запросе. Попытка передать `username`, `password` или `access_token` отклоняется валидацией контракта.

Это исключает передачу секретов через:

- браузер;
- frontend state;
- localStorage;
- payload задания;
- CLI preview;
- сохранённую конфигурацию UI.

URL со встроенными credentials по-прежнему запрещены.

## Checkout

Git checkout остаётся неинтерактивным:

- внешний `GIT_ASKPASS` от VS Code не наследуется;
- `GIT_TERMINAL_PROMPT=0`;
- при наличии серверного token создаётся защищённый runtime `GIT_ASKPASS`;
- при отсутствии server credentials checkout быстро завершается понятной ошибкой.

Сообщение об ошибке теперь указывает на `BITBUCKET_USERNAME` и `BITBUCKET_TOKEN`, а не предлагает ввод credentials в UI.

## Совместимость

Request-level Bitbucket auth удалён без compatibility adapter. Внешних потребителей этого внутреннего контракта нет. Существующие зарегистрированные репозитории и задания сохраняются.
