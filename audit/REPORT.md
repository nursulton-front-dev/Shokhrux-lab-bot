# 1. 🔴 CRITICAL / SHOWSTOPPERS (Срочно исправить)

**Вердикт по исходному состоянию: запуск под реальным трафиком преждевременен.** Подтверждены ошибки списания кешбэка, гонки подтверждения платежей, потеря выдачи доступа и исключение оплативших клиентов. Исправления внесены в рабочие файлы. Это аудит кода и локальная проверка, а не подтверждение доступности production Neon или прав бота в Telegram.

Дата: 8 сентября 2026. Ссылки ведут на исправленные файлы; номера строк «до исправления» зафиксированы при первичном чтении рабочего дерева. Это дерево уже содержало пользовательские изменения относительно Git.

**C1. Бесплатная подписка через старую кнопку кешбэка.**

- **Trace:** пользователь получает кнопку `pay_cashback_full_1` при балансе 500 000 → тратит кешбэк → снова нажимает старую кнопку. Хэндлер создаёт `amount=0, cashback_applied=0`; сервис всё равно активирует подписку. Для эксплуатации не требуется вручную подделывать callback. Повторение старой кнопки воспроизводит выдачу новых периодов.
- **Причина до исправления:** `user.py:874–899`: `cashback_used = min(orig_price, user.balance or 0)` без требования полного покрытия. `rahmat.py:43–54` повторяет `min(balance, cashback_applied)` вместо отказа при нехватке. Проверки `amount + cashback == price` нет.
- **Патч:** [создание платёжного намерения](../bot/services/rahmat.py), [проверка тарифов](../bot/services/payment_policy.py), [cashback callback](../bot/handlers/user.py). Сервер проверяет тариф, полную сумму и достаточность баланса. `request_key` привязан к пользователю, сообщению и способу оплаты; повтор той же кнопки возвращает прежний платёж.
- **Доказательство исправления:** реальные PostgreSQL-тесты `test_zero_balance_cannot_activate_cashback_tariff`, `test_legacy_underfunded_pending_payment_is_rejected`, `test_replayed_ui_action_deduplicates_intents`.

**C2. Двойное подтверждение, потерянные обновления баланса и гонка confirm/reject.**

- **Trace A:** администраторы A и B читают один `pending` → оба меняют ORM-объект на `completed` → оба создают `Subscription` и списания → оба commit. Проверка статуса обычным SELECT не исключает это расписание. Итог зависит от порядка видимости: два периода или две одновременно активные записи, два лога списания при одном перезаписанном балансе.
- **Trace B:** два разных приглашённых одновременно оплачивают → оба читают баланс пригласившего 0 → оба присваивают 30 000 → два лога бонуса, итоговый баланс только 30 000. Две первые покупки одного приглашённого также гоняются по `count(completed)`.
- **Trace C:** reject читает `pending` → confirm фиксирует подписку → reject безусловно записывает `failed`. Деньги/подписка и статус оплаты расходятся.
- **Причина до исправления:** `rahmat.py:30–61,125–129`, `user.py:986–1012`; `admin.py:997–1009`: нет row locks, CAS и обновления уже загруженных ORM-объектов после ожидания конкурента. Ручное админское продление тоже читало срок до несериализованной записи.
- **Патч:** [rahmat.py](../bot/services/rahmat.py): блокировки всех затронутых `User` в порядке ID, затем `Payment`, `populate_existing=True`, повторная проверка статуса/баланса. В этой же транзакции — подписка, списание, реферальное начисление и задача доставки. Reject использует тот же порядок блокировок. [admin.py](../bot/handlers/admin.py) сериализует ручное продление по `User`.
- **Проверка:** 20 одновременных подтверждений на PostgreSQL дают ровно одну подписку, одно списание и одну задачу доставки. Отдельно проверены два платежа на один баланс, confirm/reject, два продления, два разных реферала и две первые оплаты одного реферала. Ошибка commit и отмена coroutine откатывают весь денежный блок.

**C3. Платёж завершён, доступа нет; внешние уведомления до commit.**

- **Trace A:** Telegram `create_chat_invite_link` возвращает timeout/ошибку прав → exception поглощён → платёж и подписка commit с `invite_link=None` → повтор подтверждения уже не проходит по `status`. Устойчивой задачи повторной выдачи нет.
- **Trace B:** `flush()` создаёт ещё незафиксированный ID → администратор получает кнопку → его сессия не видит платёж. Ошибка редактирования пользовательского сообщения до `commit()` может вообще откатить заявку после её рассылки администраторам. Реферальное уведомление также отправлялось до финансового commit.
- **Причина до исправления:** `rahmat.py:73–112,125–154`, `user.py:820–870,950–983`. Несколько систем ошибочно объединены одним Python-флоу; PostgreSQL rollback не умеет отменить уже выполненный Telegram API.
- **Патч:** [PaymentDelivery](../bot/database/models.py), [payment_delivery.py](../bot/services/payment_delivery.py), [создание заявки](../bot/services/rahmat.py). Заявка фиксируется до передачи ID администратору. Денежный commit атомарно создаёт durable outbox. Отдельный воркер выдаёт ссылки и уведомляет; ошибки сохраняют задачу и повторяются с backoff. URL фиксируется до отправки пользователю.
- **Проверка:** `test_api_timeout_keeps_money_and_retries_delivery` инъецирует timeout, проверяет неизменность денег, сохранение очереди и успешную повторную выдачу через новую сессию. Отдельная сессия наблюдает ссылку в БД до отправки сообщения.
- **Граница гарантии:** деньги обрабатываются идемпотентно. Telegram-сообщение может дублироваться, если API принял его, но ответ потерялся; Bot API не предоставляет ключ идемпотентности для `sendMessage`. Откатывать подтверждённую денежную операцию из-за недоступности Telegram неправильно: исправление делает повторяемым именно предоставление доступа.

**C4. Планировщик исключает оплативших клиентов; неудачный кик теряется.**

- **Trace A:** есть оплаченная подписка на 180 дней и отдельная неоплаченная заявка → заявка старше 24 часов → scheduler кикает пользователя и ставит его действующей подписке `expired`.
- **Trace B:** старый период закончился, новый уже оплачен → обработка старой строки кикает пользователя без проверки нового права доступа. При сетевой ошибке старый код всё равно мог фиксировать `expired`, исключая запись из следующих проходов.
- **Trace C:** админ записывает `expired` → `ban_chat_member` успешен → `unban_chat_member` не выполнен. Остаётся постоянный бан или, при ошибке первого вызова, членство сохраняется без повторной задачи.
- **Причина до исправления:** `scheduler.py:30–68,127–155`, `admin.py:1134–1154`: событие истечения заявки смешано с правом доступа; нет повторной проверки всех подписок под общей блокировкой; статус и внешнее исключение не имеют повторяемого состояния.
- **Патч:** [scheduler.py](../bot/services/scheduler.py), [admin.py](../bot/handlers/admin.py), [kick_member](../bot/services/telegram_rate_limit.py). Неоплаченная заявка меняет только свой статус через `UPDATE ... WHERE pending`. Перед удалением участника блокируется `User`, заново проверяются все действующие периоды отдельно для основного/VIP чата. Ошибка cleanup оставляет запись для следующего прохода; админская аннуляция использует `revocation_pending`. Одно `unbanChatMember(only_if_banned=False)` удаляет текущее членство и разрешает последующий вход, устраняя окно между ban/unban. Такое поведение прямо описано в [Telegram Bot API](https://core.telegram.org/bots/api#unbanchatmember).
- **Проверка:** PostgreSQL-регрессии для неоплаченной заявки и старого оплаченного периода; offline-тесты смены права доступа во время ожидания блокировки, ошибки revoke, повторного cleanup и сбоя одного пользователя в пачке.

**C5. «Одноразовые» ссылки не привязаны к оплатившему пользователю.**

- **Trace:** оплативший передаёт URL знакомому → знакомый входит первым. `member_limit=1` ограничивает количество одновременно вступивших по ссылке, а не проверяет Telegram ID покупателя. Старый `adm_user_link` создаёт неограниченную по сроку, не сохранённую в БД ссылку даже без действующей подписки; scheduler её не знает и не отзывает.
- **Причина до исправления:** `rahmat.py:90–95,105–110`, `user.py:519–524`, `admin.py:1163–1170`: нет проверки владельца при вступлении, `expire_date` и полной регистрации выданных URL.
- **Патч:** [authorize_paid_join](../bot/handlers/user.py), [payment_delivery.py](../bot/services/payment_delivery.py), [adm_user_link](../bot/handlers/admin.py). Все новые ссылки создаются с `creates_join_request=True` и сроком подписки; вступление разрешено только при совпадении URL, ID покупателя и действующего права на конкретный чат. Созданная при неоднозначном timeout, но не сохранённая ссылка никого не допускает. Параметры ссылок описаны в [Bot API](https://core.telegram.org/bots/api#createchatinvitelink).
- **Проверка:** реальный PostgreSQL: один URL допускает владельца 42 и отклоняет пользователя 43. Проверены сохранение, срок и join-request режим админских ссылок.
- **Обновление существующей установки:** [rotate_invites.py](../rotate_invites.py) отзывает сохранённые старые ссылки, выдаёт активным клиентам новые и очищает исторические ссылки истёкших подписок. Ранее созданные **несохранённые** админские ссылки нельзя восстановить из БД: их нужно отозвать через управление приглашениями в Telegram. Скрипт подготовлен и проверен на doubles, к реальным чатам в аудите не запускался.

**C6. Секундные блокировки event loop: XLSX, matplotlib, файловые логи.**

- **Trace:** администратор запускает отчёт → основной поток выполняет openpyxl/XML/ZIP → остальные callbacks, getUpdates, таймеры и завершения HTTP-запросов ждут окончания синхронного участка. Аналогично работает график. При заполнении диска синхронный `RotatingFileHandler` блокирует loop на записи/переименовании файла.
- **Причина до исправления:** `admin.py:247–294,330–749` — синхронные Workbook/style/save внутри async-функций; `fitness_tools.py:601` — прямой вызов `generate_weight_chart`; `run_polling.py:28–44` — файловый handler на основном логгере. `user.py:705` также выполнял `os.path.exists` на главном потоке.
- **Патч:** [admin.py](../bot/handlers/admin.py): неизменяемые снимки ORM-данных, освобождение read-транзакции, ограничение одновременных экспортов, `to_thread` с ожиданием завершения worker при отмене. [fitness_tools.py](../bot/handlers/fitness_tools.py), [charts.py](../bot/services/charts.py): рендер в потоке, сериализация глобального состояния matplotlib, `finally: plt.close(fig)`. [run_polling.py](../run_polling.py): ограниченная очередь логов и QueueListener; файловое открытие/закрытие также вне loop. Проверка существования баннера вынесена в поток.
- **Измерение:** одинаковый renderer, локальный Python 3.13, 1000 пользователей + 1000 платежей; heartbeat каждые 5 мс. Полный XLSX занимает 2,929 с при прямом вызове, heartbeat не исполняется до 2,934 с. С `to_thread` максимальный интервал — 0,114 с. Для графика из 1000 точек — 0,396 с и 0,024 с соответственно. [Данные](event-loop-benchmark.json), [воспроизводимый скрипт](benchmark_event_loop.py).
- **Ограничение:** поток убирает длинный синхронный вызов с loop, но GIL/планировщик всё ещё влияют на задержку. Эти цифры не являются production p95 или доказательством SLO ниже 100 мс. Экспорт всего набора данных остаётся пропорционален размеру набора; не проверялась вместимость workbook на миллионах строк.

**C7. Gemini HTTP-клиенты не закрываются.**

- **Trace:** каждый запрос к ИИ создаёт `genai.Client` → использует `client.aio` → возвращает результат или попадает в exception → явного закрытия нет. При повторных запросах/остановке судьба транспорта зависит от GC; нет детерминированного освобождения соединений. Конструктор клиента также синхронно загружает TLS-материалы.
- **Причина до исправления:** `gemini_service.py:29,91,178` и `get_gemini_client`: запросы не используют контекстный менеджер или `finally` с `aclose`.
- **Патч:** [_gemini_client](../bot/services/gemini_service.py): создание в потоке, запрос в async-контексте, обязательные `client.aio.aclose()` и `client.close()`; cleanup дожидается конца даже при отмене запроса. Runtime сначала завершает/отменяет хэндлеры, потом закрывает общий HTTP и engine. Владение транспортами соответствует [официальному SDK](https://googleapis.github.io/python-genai/#close-a-client).
- **Проверка:** успех/ошибка всех трёх Gemini-флоу, отмена во время создания/запроса, ошибка async close, проверка вызова обоих close и выполнения синхронных операций вне главного потока. Число leaked sockets в реальном Google-трафике не измерялось.

# 2. 🟡 HIGH / SCALABILITY WARNINGS (Узкие места)

**H1. Пул удерживается во время Gemini; SSL-режим незаметно ослабляется.**

- **Trace:** несколько AI-хэндлеров делают SELECT → ждут Google с открытой read-транзакцией → занимают все подключения → обычное сообщение ждёт pool checkout. Отдельно URL с `sslmode=verify-full` превращается в `ssl='require'`, теряя проверку сертификата/имени сервера.
- **Причина:** `fitness_tools.py:405–419,480–493,693–708` до исправления; `db.py:28–44`: уже есть `pool_pre_ping=True`, но нет заданных recycle/timeout/budget; SSL-режимы сведены к require. Без настроек SQLAlchemy обычно допускает 5 + 10 соединений, а не «по соединению на каждого из 50 пользователей».
- **Патч:** снимки данных и `rollback()` перед внешним ожиданием; [db.py](../bot/database/db.py), [config.py](../bot/config.py): 5 соединений, overflow 0, recycle 600 с, ожидание пула 10 с, подключение 15 с, command timeout 30 с. SSL mode сохраняется; обязательный неподдерживаемый channel binding/GSS режим приводит к явной ошибке, а не скрытому ослаблению. Добавлены индексы частых запросов.
- **Проверка/граница:** освобождение read-транзакций проверено в offline-тестах; локальные PostgreSQL-конкурентные проверки используют ограниченный пул. Квота конкретного Neon-проекта неизвестна. Нельзя утверждать неизбежный `FATAL` при 50 запросах или неизбежное утреннее падение: pre-ping уже был. Pre-ping заменяет мёртвые соединения при checkout, но не повторяет прерванную транзакцию — [SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/pooling.html). SSL-различия подтверждены [asyncpg](https://magicstack.github.io/asyncpg/current/api/index.html).

**H2. FSM: NaN проходит диапазоны; неверная личность callback.**

- **Trace:** `float('NaN')` успешно создаёт NaN, сравнения `< / >` ложны → анкета/журнал сохраняет NaN. При открытии инструмента через callback `callback.message.from_user` — отправитель сообщения-бот, а не клиент → запрос fitness-профиля выполняется по ID бота.
- **Причина:** до исправления numeric validators в `fitness_tools.py`, `ensure_fitness_profile` и его вызовы передавали только `event.message`; callback-параметры оплаты также разбирались через `int/split` без допустимой схемы.
- **Патч:** [fitness_tools.py](../bot/handlers/fitness_tools.py): `math.isfinite`, диапазоны, исходный `Message | CallbackQuery`, набор разрешённых целей, fallback для неверного типа сообщения. [user.py](../bot/handlers/user.py): точные regex-фильтры callback; bounded имя/номер, проверка `contact.user_id`; [run_polling.py](../run_polling.py): `SimpleEventIsolation` для последовательности FSM одного пользователя.
- **Проверка:** три numeric-хэндлера × `None`, `NaN`, `-50`, `1e9`, `inf`, мусор; изменений БД/FSM нет. Стикер, документ и геопозиция дают `text=None`. Отрицательные числа и `1e9` уже частично отсекались исходными диапазонами: основной скрытый обход — NaN. Отдельно проверен ID пользователя callback.

**H3. HTML-инъекция, Excel-формулы и недоставляемые AI-ответы.**

- **Trace:** имя `=HYPERLINK(...)` попадает в XLSX как формула; `<...>` или незаконный XML-символ ломает профиль/экспорт. ИИ возвращает длинную строку без переносов или повреждённый HTML → прежний splitter оставляет oversized chunk, Telegram отвергает сообщение после уже выполненного платного AI-запроса.
- **Причина:** `admin.py:273,624,678,731`, `user.py` — поля имени/телефона и тексты поддержки без escaping; прежний `split_text_into_chunks` в `fitness_tools.py` делил только по строкам.
- **Патч:** [admin.py](../bot/handlers/admin.py): текстовые значения Excel, префикс для формульных маркеров, удаление недопустимых XML-символов; HTML escaping при выводе. [user.py](../bot/handlers/user.py): escaping профиля/поддержки. [fitness_tools.py](../bot/handlers/fitness_tools.py): ограничение каждого куска и plain-text fallback при `TelegramBadRequest` из-за разметки; ошибки доступа не маскируются как HTML-проблемы.
- **Проверка:** открытие сформированного workbook и проверка `cell.data_type == 's'`, отсутствие формул/нулевого символа; длинный неразрывный текст, некорректный HTML, TelegramForbidden и escaping имени. Это injection в представление/документ, а не SQL injection или доказанное исполнение команд ОС.

**H4. Startup/retry размножает scheduler и удаляет накопленные updates.**

- **Trace:** scheduler запущен через `create_task` → polling падает → внешний while повторяет запуск и создаёт второй scheduler. `delete_webhook(drop_pending_updates=True)` уничтожает ожидающие команды при старте. При SIGTERM HTTP закрывается, пока незарегистрированные фоновые задачи ещё работают; engine не dispose.
- **Причина:** `run_polling.py:78–98` до исправления, создание scheduler внутри retry-loop без сохранённого Task; detached broadcast в `admin.py:892`.
- **Патч:** [run_polling.py](../run_polling.py), [background_tasks.py](../bot/services/background_tasks.py): один tracked scheduler и outbox-worker, сохранение pending updates, ограничение 50 update tasks, обработка сигналов во время startup и polling, drain/cancel хэндлеров/рассылок, затем HTTP close и engine.dispose.
- **Проверка:** тесты SIGTERM в startup, завершения tracked broadcast, drain update tasks и запуска воркеров один раз. Исходный exec-form Docker CMD и aiogram уже позволяли доставить/обработать сигналы; проблема была в неполном lifecycle ресурсов, не в доказанном отсутствии SIGTERM у Python.

**H5. Лимит рассылки локален; ошибки и выбор аудитории не масштабируются.**

- **Trace:** два администратора запускают рассылки по 20 сообщений/с → суммарный поток пересекает обычный бюджет бота. При 429 старая рассылка просто теряет получателя. Неудачные отправки обходили sleep. Для аудитории expired множество `set(s.user_id for s in subs)` заново строилось внутри проверки каждого пользователя: O(users × subscriptions) в основном потоке.
- **Причина:** `admin.py:849–892` до исправления; scheduler не имел общего бюджета с рассылкой/хэндлерами.
- **Патч:** [telegram_rate_limit.py](../bot/services/telegram_rate_limit.py): общий middleware Bot.session — 25 запросов/с, отдельные интервалы для чатов, учёт альбомов, ограниченный retry по `retry_after`; неоднозначные сетевые отправки автоматически не повторяются. [admin.py](../bot/handlers/admin.py): выбор аудитории через SQL EXISTS, устранение повторных получателей, обработка ошибки на каждого адресата, зарегистрированная background task. [scheduler.py](../bot/services/scheduler.py): страницы по 100 ID и отдельная транзакция на элемент.
- **Проверка:** параллельные отправители делят один лимит; 429 повторяется, timeout не повторяется слепо; один неудачный пользователь не останавливает пачку. Упомянутые 30 сообщений/с — обычный bulk messaging ориентир, а не документированный универсальный лимит на все административные методы; серверный `retry_after` остаётся обязательным. [Telegram FAQ](https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this).

**H6. Docker запускается от root; отсутствуют явные production-параметры контейнера.**

- **Trace:** компрометация процесса даёт root внутри контейнера; постоянный stdout без ротации растит Docker json log; naive локальные даты зависят от TZ образа.
- **Причина до исправления:** Dockerfile без `USER` и `TZ`; в compose нет полного набора rotation/grace/security параметров. Это увеличение последствий компрометации, а не найденный отдельный RCE.
- **Патч:** [Dockerfile](../Dockerfile), [docker-compose.yml](../docker-compose.yml), [fitness_bot.service](../fitness_bot.service): UID/GID 10001, `TZ=Asia/Tashkent`, exec CMD, SIGTERM, `init: true`, 60 с остановки, no-new-privileges, json-file 10m × 3. Named volumes и владение каталогами позволяют non-root процессу писать логи.
- **Проверка:** просмотр конфигураций и runtime-тесты сигналов. Docker CLI/daemon в среде отсутствуют; сборка и контейнерный SIGTERM на целевом хосте не проверены. Изменение mount-путей описано в [DEPLOY.md](../DEPLOY.md): старый host `./logs` не удаляется, приложение теперь пишет в named volume.

**H7. Резервная Gemini-модель отключена.**

- **Trace:** основной `gemini-2.5-flash` возвращает ошибку → fallback вызывает `gemini-2.0-flash`, для которого объявлено отключение 1 июня 2026 → резервный путь не восстанавливает ответ.
- **Причина:** исходный `gemini_service.py:26`, hardcoded retired fallback.
- **Патч:** `FALLBACK_MODELS = ['gemini-2.5-flash-lite']` в [gemini_service.py](../bot/services/gemini_service.py). На дату аудита для основной 2.5-flash и выбранной 2.5-flash-lite дата отключения не объявлена. [Официальный график Google](https://ai.google.dev/gemini-api/docs/deprecations).
- **Проверка:** документация и offline-флоу fallback/close. Доступность модели для конкретного Google-проекта и квота не проверялись реальным запросом.

**H8. Rahmat Pay представлен рабочим способом оплаты, но интеграции нет.**

- **Trace:** пользователь нажимает оплату → бот конструирует URL из `amount/uid/pid` и случайного UUID → не создаёт подтверждённый provider invoice; в проекте нет механизма проверки получения средств от провайдера.
- **Причина:** `rahmat.py:14–19` до исправления — локальный f-string. Автоматическое подтверждение настоящего платежа из такого URL не следует.
- **Патч:** [rahmat.py](../bot/services/rahmat.py) явно отклоняет генерацию неподключённого счёта; [user.py](../bot/handlers/user.py) не показывает этот способ и объясняет недоступность старой кнопки. Ручное подтверждение и полный кешбэк продолжают работать.
- **Граница:** готовый безопасный патч закрывает ложный путь оплаты. Настоящая Rahmat-интеграция потребует документации/учётных данных провайдера и отдельной реализации; они не выдумывались.

**H9. Миграция может напечатать успех после ошибки.**

- **Trace:** одна ALTER TABLE падает → общий transaction уже aborted → broad except печатает ошибку и продолжает → `init_db/create_all` не обновляет существующие таблицы → процесс может закончиться без понятного сигнала провала миграции.
- **Причина:** `run_migration.py:6–22` до исправления; ошибки поглощаются внутри транзакции.
- **Патч:** [run_migration.py](../run_migration.py): исключения выходят наружу, `engine.dispose` в finally, additive columns, новый outbox, уникальность request_key, индексы CONCURRENTLY с обработкой INVALID индекса после прерванного создания.
- **Проверка:** PostgreSQL-тест удаляет новый столбец и таблицу из временной схемы, запускает upgrade и повторяет его. Таблица/столбец доступны, индекс валиден; повтор успешен.

# 3. 🟢 HARDENED & VERIFIED

**Уже было корректно в исходном коде:**

- Admin Router защищает и `message`, и `callback_query` через `IsAdmin`. Подделка `adm_user_*` пользователем вне списка не даёт доступ к профилям. Добавлена только устойчивость фильтра к `from_user=None`.
- `SUPPORT_ID` намеренно входит в admin IDs; это явно указано в исходном `.env.example`. При отсутствии другого требования к ролям это не объявляется скрытым RBAC-обходом.
- DB middleware использует `async with AsyncSessionLocal()`: исключение хэндлера закрывает сессию и откатывает незавершённую транзакцию. Отдельного доказанного leak сессий middleware нет.
- `pool_pre_ping=True` уже включён; финансовые суммы хранятся целыми UZS; SQLAlchemy-запросы параметризованы.
- Docker CMD задан JSON exec-form. Временный Excel/PNG формируется через BytesIO; это оперативная память, а не синхронная запись временного файла на диск. Проблемой был CPU-рендер. Файл баннера передаётся через FSInputFile; прямых runtime-вызовов `shutil`/`requests` в подключённых модулях не найдено.
- `user_backup.py`, `reset_db.py`, `clear_db.py` не подключены к рабочим routers/polling; они не выполнялись при проверках.

**После исправления проверено:**

- **101 pytest-тест пройден**, включая **18 тестов на настоящем временном PostgreSQL 17.9**; Python 3.13.15. [Лог](pytest-results.txt), [денежные тесты](../tests/test_payments_audit.py).
- **25/25 исходных self-test проверок пройдено**. [Лог](self-test-results.txt). Эти проверки сами по себе проверяют wiring/импорты, а не конкурентную корректность.
- `compileall` проходит для bot, runtime, миграции, rotation utility и тестов.
- [Патч проверен](patch-verification.txt) применением к изолированной копии документированного Git-базиса и сравнением SHA-256 всех 41 файла с проверенным деревом.
- Тесты игнорируют `.env`. Рабочая БД, реальные отправки Telegram, Google-запросы и настоящая ротация ссылок не использовались.

Границы: нет нагрузочного прогона на конкретном Neon-тарифе, проверки Python 3.12 внутри Docker, прав реального бота и реальной сетевой аварии. В тестах остаются четыре `DeprecationWarning` о `utcnow` из существующей аналитики/админки; это не ошибки выполнения. Рассылки/FSM/rate limiter рассчитаны на один polling-процесс; денежные блокировки и outbox находятся в БД. Админская рассылка остаётся best-effort и не обещает продолжение с точного получателя после рестарта. Длительная недоступность Telegram задерживает cleanup/выдачу; повторяемые задачи сохраняются, права API автоматически не восстанавливаются.

# 4. 🔧 COMPILATION OF FIXES

Исправления **уже применены в рабочем проекте**, в том числе код, миграция и regression tests.

- [Полный применимый diff](fixes.patch).
- [Комплект исправленных исходников](fixed-source.tar.gz), [SHA-256 манифест](fixed-files.json).
- [Инструкции обновления](../DEPLOY.md), [миграция БД](../run_migration.py), [ротация исторических ссылок](../rotate_invites.py).

**Базис diff — Git commit `4edd46d`.** Начальное рабочее дерево содержало незакоммиченные функциональные доработки, а временный снимок начала аудита не сохранился после перезапуска среды. Поэтому diff включает эти доработки в проверенных модулях, а не только изменения аудита; он не выдаётся за чистый diff «до/после аудита». Его применение к `4edd46d` проверено. В уже исправленном рабочем дереве повторно применять его не нужно. `.env`, пользовательские assets и Git index в комплект/правки не включены.

В отдельной копии указанного базиса:

```sh
git apply --check /path/to/audit/fixes.patch
git apply /path/to/audit/fixes.patch
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
```

Ключевые фрагменты из полного патча — зависимости и окружающая обработка ошибок включены в linked source/diff.

**C1/C2: блокировка и строгая стоимость вместо `min()` при списании.**

```python
payment = await session.scalar(
    select(Payment).where(Payment.id == payment_id)
    .with_for_update().execution_options(populate_existing=True)
)
# User/referrer уже заблокированы в порядке ID.
price = TARIFF_PRICES.get(payment.tariff_months)
cashback = payment.cashback_applied or 0
if (price is None or payment.amount < 0 or cashback < 0
        or payment.amount + cashback != price):
    raise PaymentValidationError("Payment amount does not match its tariff")
if (user.balance or 0) < cashback:
    raise PaymentValidationError("Insufficient cashback; reconcile the pending payment")
```

**C3: денежные изменения и повторяемая выдача фиксируются вместе.**

```python
await session.flush()
session.add(PaymentDelivery(
    payment_id=payment.id,
    subscription_id=sub.id,
    referrer_id=reward_recipient,
))
await session.commit()
# Внешние Telegram-вызовы выполняет payment_delivery.py после этого commit.
```

Владеющий финансовой транзакцией сервис обрабатывает и обычные исключения, и отмену:

```python
except BaseException:
    await session.rollback()
    raise
```

**C4/C5: удаление без постоянного бана и проверяемое приглашение.**

```python
await bot.unban_chat_member(
    chat_id=chat_id, user_id=user_id,
    only_if_banned=False, request_timeout=15,
)
link = await bot.create_chat_invite_link(
    chat_id=config.channel_id,
    creates_join_request=True,
    expire_date=sub.expires_at,
    name=f"Payment {payment_id}",
    request_timeout=10,
)
```

Сам по себе `creates_join_request=True` недостаточен: обработчик `authorize_paid_join` в полном патче сверяет владельца, URL, срок и нужный чат под той же блокировкой User, что и cleanup/продление.

**C6/C7: вынос рендера и явное владение HTTP-транспортами.**

```python
record_tuples = [(r.recorded_at, r.weight) for r in records]
await session.rollback()
async with _chart_render_semaphore:
    buf, summary_text = await asyncio.to_thread(
        generate_weight_chart, record_tuples, language=lang,
    )
```

```python
async def _close_gemini_client(client: genai.Client) -> None:
    try:
        await client.aio.aclose()
    finally:
        await asyncio.to_thread(client.close)
```

Полный async context manager также защищает cleanup при отмене; одна строка `aclose()` только на успешном пути эту проблему не решает.

**H1: ограниченный пул с проверкой/обновлением соединений.**

```python
engine = create_async_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=config.db_pool_recycle,  # 600
    pool_size=config.db_pool_size,        # 5
    max_overflow=config.db_max_overflow,  # 0
    pool_timeout=config.db_pool_timeout,  # 10
    pool_use_lifo=True,
    connect_args={**connect_args, "timeout": 15, "command_timeout": 30},
)
```

**H2/H3: нечисловые/нефинитные значения и безопасные поля Excel.**

```python
weight_val = float((message.text or "").strip().replace(",", "."))
if not math.isfinite(weight_val) or weight_val <= 0 or weight_val > 300:
    raise ValueError("Invalid weight range")
```

```python
def _excel_text(value: str | None) -> str:
    value = ILLEGAL_CHARACTERS_RE.sub("", value or "-")[:32766]
    if value.lstrip().startswith(("=", "+", "-", "@")):
        value = "'" + value
    return value
```

**H4/H5: общий бюджет API и контролируемый polling.**

```python
bot.session.middleware(TelegramRateLimitMiddleware())
dp = Dispatcher(events_isolation=SimpleEventIsolation())
await dp.start_polling(
    bot, handle_signals=False, close_bot_session=False,
    tasks_concurrency_limit=50,
)
```

Обработчики сигналов, singleton workers, drain и закрытие транспорта/engine приведены полностью в `run_polling.py`. Лимитер обрабатывает общий cooldown после 429, а не независимый `sleep` каждого отправителя.

**H6: параметры контейнера.**

```dockerfile
USER fitnessbot:fitnessbot
STOPSIGNAL SIGTERM
CMD ["python", "main.py"]
```

```yaml
init: true
stop_grace_period: 60s
environment:
  TZ: Asia/Tashkent
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

**Порядок production-обновления:** остановить прежний бот; применить `run_migration.py`; для существующей установки выполнить `rotate_invites.py` и отдельно отозвать несохранённые старые ссылки в Telegram; запустить новую версию; проверить доступ владельца, отказ чужому ID, права обоих чатов и очередь недоставленных PaymentDelivery. Эти действия с production в рамках аудита не выполнялись.
