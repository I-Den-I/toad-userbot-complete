# ADR 0003: systemd замість Docker на спільному VPS

- Статус: прийнято
- Дата: 2026-09-30

## Контекст

Спочатку планувався Docker Compose. Реальний сервер (Hetzner, Debian 12) виявився таким:
- на ньому вже працює інший бот (wg-sniper) як systemd-сервіс з окремим користувачем, директорією `/opt/wg-sniper`, власним venv і `ProtectSystem=strict`;
- Docker не встановлений;
- системний Python — 3.11, а проєкту потрібен 3.12+.

Вимога власника: новий бот не має нічого зачепити в існуючому.

## Рішення

Розгортати як окремий systemd-сервіс за тим самим шаблоном, що й сусідній бот:
- системний користувач `toad-userbot` без shell;
- код у `/opt/toad-userbot` (власник root, сервіс лише читає), секрети в `/etc/toad-userbot`, дані в `/var/lib/toad-userbot` (`StateDirectory`, права `700`);
- Python 3.12 ставить `uv` у `/opt/toad-userbot/.python`, а сам `uv` живе в окремому venv `/opt/toad-userbot/.tools`. У `/usr/local`, системний Python і чужі venv нічого не ставиться;
- пісочниця systemd: `ProtectSystem=strict`, `NoNewPrivileges`, порожній набір capabilities, `SystemCallFilter=@system-service`, `MemoryMax=512M`;
- скрипти `deploy/install.sh`, `update.sh`, `login.sh` роблять розгортання відтворюваним та ідемпотентним.

Dockerfile і `docker-compose.yml` лишаються: CI збирає образ, і він підходить для хостів, де Docker уже є.

## Наслідки

- Docker-демон не з'являється на сервері й не змінює правила iptables.
- Оновлення: `deploy/update.sh` (git → `uv sync --locked` → рестарт сервісу).
- Логи йдуть і в journald (`journalctl -u toad-userbot`), і у файл, який читає `.logs`.
- Heartbeat-файл і `healthcheck` потрібні лише Docker. У systemd живучість забезпечують `Restart=on-failure` і `.restart` (код 75); коди 2 (немає входу) і 78 (помилка конфігу) не перезапускаються.
