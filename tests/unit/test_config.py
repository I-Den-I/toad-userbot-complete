from __future__ import annotations

from pathlib import Path

import pytest

from toad_userbot.config import AppConfig, ConfigError, Paths, load_app_config


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    config = load_app_config(tmp_path / "config.yaml")
    assert config == AppConfig()
    assert config.chat_id is None
    assert config.bot_username == "toadbot"
    assert config.control.prefix == "."


def test_values_are_normalized(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "chat_id: -1001234567890\n"
        "bot_username: '@ToadBot'\n"
        "recorder:\n"
        "  command_words: ['Квак', '  ', 'ЖАБА ИНФО']\n",
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.chat_id == -1001234567890
    assert config.bot_username == "toadbot"
    assert config.recorder.command_words == ("квак", "жаба инфо")


def test_empty_file_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")
    assert load_app_config(path) == AppConfig()


@pytest.mark.parametrize(
    "content",
    [
        "chat_id: [unclosed",
        "- just\n- a list\n",
        "unknown_key: 1\n",
        "chat_id: not-a-number\n",
        "bot_username: '@'\n",
    ],
)
def test_invalid_files_raise_config_error(tmp_path: Path, content: str) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_app_config(path)


def test_paths_layout(tmp_path: Path) -> None:
    paths = Paths(tmp_path / "data")
    paths.ensure()

    assert paths.logs_dir.is_dir()
    assert paths.session.name == "userbot.session"
    assert paths.database.parent == paths.data_dir
    assert paths.log_file.parent == paths.logs_dir
