import errno
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


MASK_VALUE = "********"


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    group: str
    value_type: str = "string"
    restart: str = "api worker"
    secret: bool = False
    options: Optional[List[str]] = None
    help: str = ""


SETTING_SPECS: List[SettingSpec] = [
    SettingSpec("API_PROVIDER", "API provider", "LLM", options=["openai", "gemini", "openrouter", "together", "custom", "ollama"]),
    SettingSpec("OPENAI_BASE_URL", "OpenAI-compatible base URL", "LLM", help="Leave blank for official OpenAI."),
    SettingSpec("OPENAI_CHAT_MODEL", "Chat model", "LLM"),
    SettingSpec("OPENAI_TEMPERATURE", "Temperature", "LLM", value_type="float"),
    SettingSpec("OPENAI_API_KEY", "API key", "LLM", secret=True),
    SettingSpec("USE_FAKE_OPENAI", "Fake demo mode", "LLM", value_type="bool", options=["true", "false"]),
    SettingSpec("EMBEDDING_PROVIDER", "Embedding provider", "Embedding", options=["openai", "local_bge_m3"]),
    SettingSpec("OPENAI_EMBEDDING_MODEL", "OpenAI embedding model", "Embedding"),
    SettingSpec("OPENAI_EMBEDDING_DIMENSIONS", "OpenAI embedding dimensions", "Embedding", value_type="int"),
    SettingSpec("LOCAL_EMBEDDING_MODEL", "Local embedding model", "Embedding"),
    SettingSpec("LOCAL_EMBEDDING_DEVICE", "Local embedding device", "Embedding", options=["cpu", "cuda"]),
    SettingSpec("LOCAL_EMBEDDING_BATCH_SIZE", "Local embedding batch size", "Embedding", value_type="int"),
    SettingSpec("RERANKER_PROVIDER", "Reranker provider", "Reranker", options=["none", "local_bge_m3"]),
    SettingSpec("LOCAL_RERANKER_MODEL", "Local reranker model", "Reranker"),
    SettingSpec("LOCAL_RERANKER_DEVICE", "Local reranker device", "Reranker", options=["cpu", "cuda"]),
    SettingSpec("RERANKER_TOP_K", "Reranker top K", "Reranker", value_type="int"),
    SettingSpec("RERANKER_WEIGHT", "Reranker weight", "Reranker", value_type="float"),
    SettingSpec("ENABLE_RAG_ANYTHING", "Enable RAG-Anything", "Parsing", value_type="bool", options=["true", "false"]),
    SettingSpec("RAG_ANYTHING_PARSER", "RAG-Anything parser", "Parsing"),
    SettingSpec("PDF_OCR_ENABLED", "Enable PDF OCR", "OCR", value_type="bool", options=["true", "false"]),
    SettingSpec("PDF_OCR_ENGINE", "PDF OCR engine", "OCR", options=["auto", "paddle", "vietocr", "tesseract"]),
    SettingSpec("PDF_OCR_LANG", "Tesseract OCR languages", "OCR"),
    SettingSpec("PADDLE_OCR_LANG", "PaddleOCR languages", "OCR"),
    SettingSpec("PDF_OCR_SCALE", "PDF OCR scale", "OCR", value_type="float"),
    SettingSpec("PDF_OCR_MAX_PAGES", "PDF OCR max pages", "OCR", value_type="int"),
    SettingSpec("OCR_MIN_LINE_CONFIDENCE", "OCR min line confidence", "OCR", value_type="float"),
    SettingSpec("PAGEINDEX_MIN_PAGES", "PageIndex min pages", "PageIndex", value_type="int"),
    SettingSpec("PAGEINDEX_COMMAND", "PageIndex command", "PageIndex"),
    SettingSpec("CHAT_CONTEXT_LIMIT", "Chat context chunks", "Chat/RAG", value_type="int"),
    SettingSpec("CHAT_CONTEXT_MAX_CHARS", "Chat context max chars", "Chat/RAG", value_type="int"),
    SettingSpec("CHAT_CHUNK_MAX_CHARS", "Chat chunk max chars", "Chat/RAG", value_type="int"),
    SettingSpec("CHAT_MIN_RELEVANCE_SCORE", "Chat min relevance score", "Chat/RAG", value_type="float"),
    SettingSpec("CHAT_MIN_LEXICAL_SCORE", "Chat min lexical score", "Chat/RAG", value_type="float"),
    SettingSpec("MAX_UPLOAD_MB", "Max upload MB", "Limits", value_type="int"),
]

SPECS_BY_KEY = {spec.key: spec for spec in SETTING_SPECS}


class SettingsFileError(RuntimeError):
    pass


def env_file_path() -> Path:
    return Path(os.getenv("ADMIN_SETTINGS_ENV_PATH", ".env")).resolve()


def read_admin_settings() -> Dict[str, Any]:
    env_values = _read_env_file(env_file_path())
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for spec in SETTING_SPECS:
        raw_value = env_values.get(spec.key, os.getenv(spec.key, ""))
        value = MASK_VALUE if spec.secret and raw_value else raw_value
        groups.setdefault(spec.group, []).append(
            {
                "key": spec.key,
                "label": spec.label,
                "value": value,
                "type": spec.value_type,
                "secret": spec.secret,
                "options": spec.options or [],
                "restart": spec.restart,
                "help": spec.help,
            }
        )
    return {
        "env_path": str(env_file_path()),
        "groups": [{"name": name, "settings": settings} for name, settings in groups.items()],
        "restart_command": restart_command(),
    }


def update_admin_settings(values: Dict[str, str]) -> Dict[str, Any]:
    unknown = sorted(set(values) - set(SPECS_BY_KEY))
    if unknown:
        raise SettingsFileError(f"Unsupported settings: {', '.join(unknown)}")

    path = env_file_path()
    current = _read_env_file(path)
    updates: Dict[str, str] = {}
    for key, value in values.items():
        spec = SPECS_BY_KEY[key]
        text_value = "" if value is None else str(value).strip()
        if spec.secret and text_value in {"", MASK_VALUE}:
            continue
        updates[key] = _validate_setting_value(spec, text_value)

    if updates:
        _write_env_file(path, updates, current)

    return {
        "ok": True,
        "updated_keys": sorted(updates),
        "restart_required": bool(updates),
        "restart_command": restart_command(),
    }


def restart_command() -> str:
    return "sudo docker compose up -d --force-recreate api worker frontend"


def _validate_setting_value(spec: SettingSpec, value: str) -> str:
    if spec.options and value not in spec.options:
        raise SettingsFileError(f"{spec.key} must be one of: {', '.join(spec.options)}")
    if spec.value_type == "bool":
        normalized = value.lower()
        if normalized not in {"true", "false"}:
            raise SettingsFileError(f"{spec.key} must be true or false")
        return normalized
    if spec.value_type == "int":
        try:
            int(value)
        except ValueError as exc:
            raise SettingsFileError(f"{spec.key} must be an integer") from exc
    if spec.value_type == "float":
        try:
            float(value)
        except ValueError as exc:
            raise SettingsFileError(f"{spec.key} must be a number") from exc
    return value


def _read_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    if path.is_dir():
        raise SettingsFileError(
            f"Settings env path is a directory, not a file: {path}. "
            "Remove that directory and create a real .env file before using Admin Settings."
        )
    values: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SettingsFileError(f"Cannot read settings env file {path}: {exc}") from exc
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _write_env_file(path: Path, updates: Dict[str, str], current: Dict[str, str]) -> None:
    if path.exists() and path.is_dir():
        raise SettingsFileError(
            f"Settings env path is a directory, not a file: {path}. "
            "Remove that directory and create a real .env file before using Admin Settings."
        )
    try:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        original_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SettingsFileError(f"Cannot prepare settings env file {path}: {exc}") from exc
    written = set()
    output_lines = []
    for line in original_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output_lines.append(line)
            continue
        key, _value = stripped.split("=", 1)
        key = key.strip()
        if key in updates:
            output_lines.append(f"{key}={_quote_env_value(updates[key])}")
            written.add(key)
        else:
            output_lines.append(line)

    for key in updates:
        if key not in written and key not in current:
            output_lines.append(f"{key}={_quote_env_value(updates[key])}")

    content = "\n".join(output_lines).rstrip() + "\n"
    try:
        _write_env_content(path, content)
    except OSError as exc:
        raise SettingsFileError(f"Cannot write settings env file {path}: {exc}") from exc


def _write_env_content(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), newline="\n") as handle:
            handle.write(content)
            temp_name = handle.name
        Path(temp_name).replace(path)
    except OSError as exc:
        if exc.errno != errno.EBUSY:
            raise
        path.write_text(content, encoding="utf-8")
    finally:
        if temp_name:
            temp_path = Path(temp_name)
            if temp_path.exists():
                temp_path.unlink()


def _quote_env_value(value: str) -> str:
    if value == "":
        return ""
    if any(char.isspace() for char in value) or "#" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value
