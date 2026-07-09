import json
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List

from app.config import get_settings
from app.models import DocumentChunk
from app.services.storage import document_artifact_dir


settings = get_settings()


def build_page_index(document_id: str, file_path: Path, chunks: List[DocumentChunk]) -> Dict:
    tree = _try_pageindex_command(document_id, file_path)
    if tree is None:
        tree = _build_heuristic_tree(chunks)

    artifact_path = document_artifact_dir(document_id) / "pageindex.json"
    artifact_path.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
    return tree


def _try_pageindex_command(document_id: str, file_path: Path):
    if not settings.pageindex_command:
        return None

    output_path = document_artifact_dir(document_id) / "pageindex-command.json"
    command = shlex.split(settings.pageindex_command) + [str(file_path), str(output_path)]
    try:
        subprocess.run(command, check=True, timeout=600, capture_output=True, text=True)
        if output_path.exists():
            return json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _build_heuristic_tree(chunks: List[DocumentChunk]) -> Dict:
    pages = {}
    for chunk in chunks:
        pages.setdefault(chunk.page_number, []).append(chunk.content)

    nodes = []
    for page_number in sorted(pages):
        merged = " ".join(" ".join(text.split()) for text in pages[page_number])
        summary = merged[:420].rstrip()
        nodes.append(
            {
                "title": f"Page {page_number}",
                "node_id": f"page-{page_number}",
                "start_index": page_number,
                "end_index": page_number,
                "summary": summary,
                "nodes": [],
            }
        )

    return {
        "title": "Document",
        "node_id": "root",
        "summary": "Heuristic page tree generated locally because PageIndex command is not configured.",
        "nodes": nodes,
    }


def page_boosts_from_tree(query: str, tree: Dict) -> Dict[int, float]:
    terms = [term.lower() for term in query.split() if len(term) >= 3]
    boosts: Dict[int, float] = {}
    if not terms or not tree:
        return boosts

    def visit(node: Dict):
        text = f"{node.get('title', '')} {node.get('summary', '')}".lower()
        score = sum(1 for term in terms if term in text)
        if score:
            start = int(node.get("start_index") or node.get("page_number") or 1)
            end = int(node.get("end_index") or start)
            for page in range(start, end + 1):
                boosts[page] = max(boosts.get(page, 0.0), min(0.2, score * 0.04))
        for child in node.get("nodes") or []:
            if isinstance(child, dict):
                visit(child)

    visit(tree)
    return boosts
