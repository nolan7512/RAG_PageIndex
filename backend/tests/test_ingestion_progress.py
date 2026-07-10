from app.services import ingestion_progress


def test_ingestion_progress_records_ordered_steps(monkeypatch, tmp_path):
    def artifact_dir(document_id):
        path = tmp_path / document_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(ingestion_progress, "document_artifact_dir", artifact_dir)

    ingestion_progress.init_progress("doc-1", "sample.pdf")
    ingestion_progress.mark_step("doc-1", "embedding", "processing", "Embedding chunks.")
    ingestion_progress.mark_step("doc-1", "parsing", "done", "Parsed.")

    progress = ingestion_progress.load_progress("doc-1")

    assert [step["name"] for step in progress["steps"]][:5] == ["uploaded", "parsing", "ocr", "chunking", "embedding"]
    assert progress["steps"][1]["status"] == "done"
    assert progress["steps"][4]["status"] == "processing"
