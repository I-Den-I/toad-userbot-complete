from __future__ import annotations

from pathlib import Path

import pytest

from toad_userbot.__main__ import EXIT_CONFIG, main


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings read ".env" from the working directory; never pick up a developer's real one.
    monkeypatch.chdir(tmp_path)
    for name in ("TG_API_ID", "TG_API_HASH", "DATA_DIR", "CONFIG_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))


def test_healthcheck_fails_without_heartbeat() -> None:
    assert main(["healthcheck"]) == 1


def test_healthcheck_passes_with_fresh_heartbeat(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "heartbeat").write_text("now", encoding="utf-8")
    assert main(["healthcheck"]) == 0


def test_missing_credentials_is_a_config_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run"]) == EXIT_CONFIG
    assert "tg_api_id" in capsys.readouterr().err.lower()


def test_invalid_config_file_is_a_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TG_API_ID", "12345")
    monkeypatch.setenv("TG_API_HASH", "0123456789abcdef")
    (tmp_path / "config.yaml").write_text("unknown_key: 1\n", encoding="utf-8")

    assert main(["run"]) == EXIT_CONFIG
    assert "config.yaml" in capsys.readouterr().err
