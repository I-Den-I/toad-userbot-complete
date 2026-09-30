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

## Розгортання на VPS (systemd)

Основний спосіб для сервера, де вже працюють інші сервіси. Юзербот отримує окремого системного користувача `toad-userbot`, окрему директорію і власний Python 3.12, який ставить `uv`. Системний Python, інші сервіси й мережеві правила не зачіпаються. Причини — в [ADR 0003](docs/adr/0003-systemd-on-shared-vps.md).

| Що | Де |
|---|---|
| Код, venv, Python | `/opt/toad-userbot` (власник root, сервіс лише читає) |
| Секрети і конфіг | `/etc/toad-userbot/env`, `/etc/toad-userbot/config.yaml` |
| БД, сесія, логи | `/var/lib/toad-userbot` (права `700`) |
| Сервіс | `toad-userbot.service` (пісочниця systemd, `MemoryMax=512M`) |

**Встановлення** (від root):

```bash
git clone https://github.com/I-Den-I/toad-userbot-complete.git /opt/toad-userbot && /opt/toad-userbot/deploy/install.sh
```

**Вхід в акаунт — робиш тільки ти.** Скрипт спитає `api_id`/`api_hash` з https://my.telegram.org (якщо їх ще немає) і покаже **QR-код**. Відскануй його з телефона: Telegram → Налаштування → Пристрої → «Підключити пристрій». Далі введи пароль 2FA, якщо він є. Наприкінці скрипт запустить сервіс.

```bash
ssh -t root@<сервер> /opt/toad-userbot/deploy/login.sh
```

Вхід за кодом замість QR: `login.sh --code`. Telegram часто не доставляє коди новим стороннім клієнтам з IP дата-центрів, тому типово використовується QR.

Далі в Saved Messages: `.ping` → `.chats <частина назви>` → `.chat set <id>` → `.status`.

**Оновлення** до свіжого `main` (або до гілки: `update.sh origin/<гілка>`):

```bash
/opt/toad-userbot/deploy/update.sh
```

**Стан і логи:**

```bash
systemctl status toad-userbot
```

```bash
journalctl -u toad-userbot -f
```

## Розгортання через Docker

Альтернатива для сервера, де Docker уже є.

```bash
cp .env.example .env && cp config.example.yaml config.yaml
```

1. Впиши `TG_API_ID` і `TG_API_HASH` у `.env`.
2. `GIT_COMMIT=$(git rev-parse --short HEAD) docker compose build`
3. `docker compose run --rm userbot login` — вхід робиш тільки ти.
4. `docker compose up -d`, потім у Saved Messages: `.chats` → `.chat set <id>` → `.status`.

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
- `/etc/toad-userbot/env` доступний лише root і групі сервісу (`640`), дані сервісу — лише йому (`700`).
