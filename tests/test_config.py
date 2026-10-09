"""Config persistence tests."""

from file_organizer.config import AppSettings, load_settings, save_settings


def test_roundtrip(tmp_path):
    cfg = tmp_path / "settings.json"
    s = AppSettings(include_other=True, conflict="skip", recent_dirs=["/tmp/a"])
    s.categories["Custom"] = [".xyz"]
    save_settings(s, cfg)
    loaded = load_settings(cfg)
    assert loaded.include_other is True
    assert loaded.conflict == "skip"
    assert loaded.categories["Custom"] == [".xyz"]
    assert loaded.recent_dirs == ["/tmp/a"]


def test_unsafe_hand_edited_config_is_dropped(tmp_path):
    cfg = tmp_path / "settings.json"
    cfg.write_text('{"categories": {"../evil": [".x"], "Good": [".y"]}, "conflict": "bogus"}')
    loaded = load_settings(cfg)
    assert "../evil" not in loaded.categories
    assert loaded.categories["Good"] == [".y"]
    assert loaded.conflict == "rename"


def test_missing_config_gives_defaults(tmp_path):
    loaded = load_settings(tmp_path / "nope.json")
    assert "Images" in loaded.categories
