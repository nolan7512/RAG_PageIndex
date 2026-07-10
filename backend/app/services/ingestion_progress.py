import json
from datetime import datetime
from typing import Dict, List, Optional

from app.services.storage import document_artifact_dir


STEP_ORDER = ["uploaded", "parsing", "ocr", "chunking", "embedding", "pageindex", "ready"]
TERMINAL_STEPS = {"ready", "failed", "skipped"}


def init_progress(document_id: str, filename: str) -> None:
    progress = {
        "document_id": document_id,
        "filename": filename,
        "steps": [
            _step("uploaded", "done", "File uploaded to local storage."),
            _step("parsing", "pending"),
            _step("ocr", "pending"),
            _step("chunking", "pending"),
            _step("embedding", "pending"),
            _step("pageindex", "pending"),
            _step("ready", "pending"),
        ],
        "updated_at": _now(),
    }
    _write_progress(document_id, progress)


def mark_step(document_id: str, name: str, status: str, message: Optional[str] = None, metadata: Optional[Dict] = None) -> None:
    progress = load_progress(document_id)
    if not progress:
        progress = {"document_id": document_id, "steps": [], "updated_at": _now()}
    steps = progress.setdefault("steps", [])
    current = next((step for step in steps if step.get("name") == name), None)
    if current is None:
        current = _step(name, "pending")
        steps.append(current)

    current["status"] = status
    if message is not None:
        current["message"] = message
    if metadata is not None:
        current["metadata"] = metadata
    if status == "processing" and not current.get("started_at"):
        current["started_at"] = _now()
    if status in TERMINAL_STEPS:
        current["finished_at"] = _now()
    progress["updated_at"] = _now()
    _write_progress(document_id, progress)


def fail_progress(document_id: str, message: str) -> None:
    progress = load_progress(document_id)
    active_step = None
    if progress:
        active_step = next((step for step in progress.get("steps", []) if step.get("status") == "processing"), None)
    if active_step:
        mark_step(document_id, active_step["name"], "failed", message)
    mark_step(document_id, "ready", "failed", message)


def load_progress(document_id: str) -> Dict:
    path = _progress_path(document_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    steps = data.get("steps")
    if isinstance(steps, list):
        data["steps"] = _ordered_steps(steps)
    return data


def _ordered_steps(steps: List[Dict]) -> List[Dict]:
    order = {name: index for index, name in enumerate(STEP_ORDER)}
    return sorted(steps, key=lambda step: order.get(step.get("name"), len(order)))


def _step(name: str, status: str, message: str = "", metadata: Optional[Dict] = None) -> Dict:
    return {
        "name": name,
        "status": status,
        "message": message,
        "metadata": metadata or {},
        "started_at": _now() if status == "processing" else None,
        "finished_at": _now() if status in TERMINAL_STEPS else None,
    }


def _progress_path(document_id: str):
    return document_artifact_dir(document_id) / "ingestion.json"


def _write_progress(document_id: str, progress: Dict) -> None:
    progress["steps"] = _ordered_steps(progress.get("steps", []))
    _progress_path(document_id).write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.utcnow().isoformat()
