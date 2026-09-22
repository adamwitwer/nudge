import pytest

from nudge.config import ConfigError, load


def write(tmp_path, text):
    p = tmp_path / "config.toml"
    p.write_text(text)
    return p


def test_example_config_parses():
    cfg = load(__import__("pathlib").Path("config.example.toml"))
    assert len(cfg.calendars) == 2 and cfg.poll.total_seconds() == 300


def test_requires_calendars(tmp_path):
    with pytest.raises(ConfigError):
        load(write(tmp_path, "poll_minutes = 5\n"))


def test_rejects_placeholder_webhook(tmp_path):
    with pytest.raises(ConfigError):
        load(write(tmp_path, 'calendars = ["a"]\n[discord]\nwebhook_url = "PASTE_WEBHOOK_URL_HERE"\n'))
