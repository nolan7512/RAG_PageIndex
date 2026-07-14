from app.services import admin_settings
from app.services.admin_settings import MASK_VALUE, SettingsFileError, read_admin_settings, update_admin_settings


def test_admin_settings_masks_secret_values(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=secret-key\nOPENAI_CHAT_MODEL=gpt-4o-mini\n", encoding="utf-8")
    monkeypatch.setattr(admin_settings, "env_file_path", lambda: env_path)

    payload = read_admin_settings()
    values = {item["key"]: item["value"] for group in payload["groups"] for item in group["settings"]}

    assert values["OPENAI_API_KEY"] == MASK_VALUE
    assert values["OPENAI_CHAT_MODEL"] == "gpt-4o-mini"


def test_update_admin_settings_keeps_secret_when_mask_is_submitted(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=secret-key\nOPENAI_CHAT_MODEL=gpt-4o-mini\n", encoding="utf-8")
    monkeypatch.setattr(admin_settings, "env_file_path", lambda: env_path)

    result = update_admin_settings({"OPENAI_API_KEY": MASK_VALUE, "OPENAI_CHAT_MODEL": "gpt-4.1-mini"})

    content = env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=secret-key" in content
    assert "OPENAI_CHAT_MODEL=gpt-4.1-mini" in content
    assert result["updated_keys"] == ["OPENAI_CHAT_MODEL"]


def test_update_admin_settings_validates_allowlist_and_types(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(admin_settings, "env_file_path", lambda: env_path)

    try:
        update_admin_settings({"DATABASE_URL": "sqlite:///bad.db"})
    except SettingsFileError as exc:
        assert "Unsupported settings" in str(exc)
    else:
        raise AssertionError("DATABASE_URL should not be editable")

    try:
        update_admin_settings({"PAGEINDEX_MIN_PAGES": "not-a-number"})
    except SettingsFileError as exc:
        assert "must be an integer" in str(exc)
    else:
        raise AssertionError("PAGEINDEX_MIN_PAGES should require an integer")

    try:
        update_admin_settings({"API_PROVIDER": ""})
    except SettingsFileError as exc:
        assert "must be one of" in str(exc)
    else:
        raise AssertionError("API_PROVIDER should require a supported provider")


def test_admin_settings_reports_directory_env_path(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.mkdir()
    monkeypatch.setattr(admin_settings, "env_file_path", lambda: env_path)

    try:
        read_admin_settings()
    except SettingsFileError as exc:
        assert "is a directory" in str(exc)
    else:
        raise AssertionError("directory env path should be rejected")
