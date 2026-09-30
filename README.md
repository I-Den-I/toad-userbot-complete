# Toad Userbot

Юзербот для гри [@toadbot](https://t.me/toadbot) в одному чаті Telegram.

**Статус: етап 0 — Recorder.** Юзербот лише слухає і записує відповіді бота, поки ти граєш руками. **У чат він нічого не пише.** Зібрані відповіді стануть основою для парсерів і автоматизації на наступних етапах.

Документація:
- [Архітектура](docs/ARCHITECTURE.md): план, модулі, roadmap;
- [Каталог відповідей бота](docs/BOT_REPLIES.md);
- [Архітектурні рішення (ADR)](docs/adr/).

## Що вміє етап 0

- Записує в SQLite кожне повідомлення @toadbot у робочому чаті та кожну команду, адресовану боту (свою чи чужу). Запис відбувається одразу при отриманні, бо бот видаляє все приблизно через 5 хв.
- Фіксує редагування і видалення цих повідомлень.
- Звичайні розмови в чаті не зберігає.
- Керується командами в **Saved Messages** (див. нижче).
- **Не читає чат:** не позначає прочитаним, не опитує історію, не вмикає «онлайн». Це перевіряє тест `tests/test_architecture.py` (див. [§5 архітектури](docs/ARCHITECTURE.md#5-непомітність)).

## Команди керування

Пиши їх у **Saved Messages** («Избранное») з акаунта, на якому працює юзербот. Відповідь з'являється замість команди. Довгі відповіді приходять файлом.

| Команда | Що робить |
|---|---|
| `.help` | список команд |
| `.ping` | затримка до Telegram API |
| `.status` | стан: акаунт, чат, бот, скільки записано, коли було останнє повідомлення бота |
| `.uptime` | час роботи процесу і сервера |
| `.version` | версія і коміт |
| `.cpu` | навантаження CPU (процес і сервер) |
| `.mem` | пам'ять процесу, контейнера і сервера |
| `.disk` | місце на диску, розмір БД, логів і сесії |
| `.sys` | хост, ОС, версії Python і Telethon |
| `.logs [N] [debug\|info\|warning\|error]` | останні N рядків логу, опційно від рівня: `.logs 50 error` |
| `.chats [фільтр]` | знайти групи та їхні id: `.chats болото` |
| `.chat` / `.chat set <id>` / `.chat reset` | показати або змінити робочий чат (зберігається в БД) |
| `.export [годин]` | вивантажити записане за N годин у файл JSONL (типово 24) |
| `.restart` | перезапустити процес |

## Розгортання на VPS

Потрібні Docker з плагіном `compose` і git.

```bash
git clone https://github.com/I-Den-I/toad-userbot-complete.git
```

```bash
cd toad-userbot-complete && cp .env.example .env && cp config.example.yaml config.yaml
```

1. **API-ключі.** Відкрий https://my.telegram.org → *API development tools* → створи застосунок. Впиши `api_id` і `api_hash` у `.env` (`TG_API_ID`, `TG_API_HASH`).
2. **Збірка образу:**
   ```bash
   GIT_COMMIT=$(git rev-parse --short HEAD) docker compose build
   ```
3. **Вхід в акаунт — робиш тільки ти.** Введи номер телефону, код із Telegram і пароль 2FA. Сесія збережеться в Docker-томі.
   ```bash
   docker compose run --rm userbot login
   ```
4. **Запуск:**
   ```bash
   docker compose up -d
   ```
5. **Налаштування чату в Saved Messages:** `.ping` → `.chats <частина назви>` → `.chat set <id>` → `.status`.
6. Грай руками як завжди. `.status` показує, що запис іде; `.export` вивантажує зібране.

Оновлення:

```bash
git pull && GIT_COMMIT=$(git rev-parse --short HEAD) docker compose up -d --build
```

Логи контейнера:

```bash
docker compose logs -f --tail=100
```

## Розробка

Потрібні Python 3.12+ і [uv](https://docs.astral.sh/uv/).

```bash
make install
```

```bash
make check
```

`make check` запускає те саме, що CI: `ruff`, `mypy --strict`, `pytest` з покриттям (поріг 85%). Локальний запуск без Docker: заповни `.env` і `config.yaml`, потім `make login` і `make run`.

Структура коду і правила залежностей між шарами описані в [§11–12 архітектури](docs/ARCHITECTURE.md#11-структура-проєкту).

## Безпека

- `.env`, `config.yaml`, `data/` і `*.session` не потрапляють у git (`.gitignore` і pre-commit).
- Файл сесії дає **повний доступ до акаунта**. Тримай VPS закритим: вхід лише за SSH-ключами, без зайвих користувачів.
- Активну сесію видно в Telegram → *Налаштування → Пристрої* як **Toad Userbot**. Звідти її можна завершити будь-коли.
