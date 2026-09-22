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


def test_telegram_optional_and_parsed(tmp_path):
    cfg = load(write(tmp_path, 'calendars = ["a"]\n[telegram]\nbot_token = "123:abc"\nchat_id = 42\n'))
    assert (cfg.telegram_bot_token, cfg.telegram_chat_id) == ("123:abc", 42)
    assert load(write(tmp_path, 'calendars = ["a"]\n')).telegram_bot_token is None


def test_rejects_placeholder_bot_token(tmp_path):
    with pytest.raises(ConfigError):
        load(write(tmp_path, 'calendars = ["a"]\n[telegram]\nbot_token = "PASTE_BOT_TOKEN_HERE"\n'))


def test_emoji_config_overrides_and_extends_builtins(tmp_path):
    cfg = load(write(tmp_path, 'calendars = ["a"]\n[emoji]\ndefault = "🔔"\n[emoji.keywords]\nTrash = "🚮"\nsoccer = "⚽"\n'))
    assert cfg.emoji.pick("Trash Night") == "🚮"   # user entry beats the built-in
    assert cfg.emoji.pick("Soccer practice") == "⚽"
    assert cfg.emoji.pick("Birthday") == "🎂"      # built-ins still apply
    assert cfg.emoji.pick("Something else") == "🔔"


def test_emoji_builtins_can_be_disabled(tmp_path):
    cfg = load(write(tmp_path, 'calendars = ["a"]\n[emoji]\nbuiltin = false\n'))
    assert cfg.emoji.pick("Birthday") == "⏰"
