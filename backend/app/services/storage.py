import shutil
from pathlib import Path

from app.config import get_settings


settings = get_settings()


def storage_root() -> Path:
    root = Path(settings.rag_storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def document_upload_dir(document_id: str) -> Path:
    path = storage_root() / "uploads" / document_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def document_artifact_dir(document_id: str) -> Path:
    path = storage_root() / "artifacts" / document_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def original_file_path(document_id: str) -> Path:
    return document_upload_dir(document_id) / "original"


def remove_document_files(document_id: str) -> None:
    for base in [storage_root() / "uploads" / document_id, storage_root() / "artifacts" / document_id]:
        if base.exists():
            shutil.rmtree(base)
