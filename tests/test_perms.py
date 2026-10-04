import logging
import stat

from nudge.config import load
from nudge.perms import keep_private
from nudge.store import Store


def mode(p):
    return stat.S_IMODE(p.stat().st_mode)


def test_world_readable_file_is_tightened_and_logged(tmp_path, caplog):
    p = tmp_path / "secret"
    p.write_text("x")
    p.chmod(0o644)
    with caplog.at_level(logging.WARNING, logger="nudge"):
        keep_private(p)
    assert mode(p) == 0o600
    assert "tightened to 600" in caplog.text


def test_private_file_is_left_alone_quietly(tmp_path, caplog):
    p = tmp_path / "secret"
    p.write_text("x")
    p.chmod(0o600)
    with caplog.at_level(logging.WARNING, logger="nudge"):
        keep_private(p)
    assert mode(p) == 0o600 and caplog.text == ""


def test_missing_path_and_memory_db_are_ignored(tmp_path):
    keep_private(tmp_path / "nope")
    keep_private(":memory:")


def test_loading_config_toml_tightens_it(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('calendars = ["a"]\n')
    p.chmod(0o644)
    load(p)
    assert mode(p) == 0o600


def test_loading_the_example_does_not_touch_it(tmp_path):
    p = tmp_path / "config.example.toml"
    p.write_text('calendars = ["a"]\n')
    p.chmod(0o644)
    load(p)
    assert mode(p) == 0o644


def test_opening_the_store_tightens_state_db(tmp_path):
    p = tmp_path / "state.db"
    p.touch()
    p.chmod(0o644)
    Store(p)
    assert mode(p) == 0o600
