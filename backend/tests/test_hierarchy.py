import pytest

from app.models import Collection, Document
from app.services.hierarchy import (
    InvalidRelativePath,
    build_embedding_text,
    folder_path_for_relative_path,
    normalize_relative_path,
)


def test_normalize_relative_path_accepts_nested_folder_path():
    assert normalize_relative_path("HR\\Thuong Tet\\policy.pdf") == "HR/Thuong Tet/policy.pdf"


@pytest.mark.parametrize("value", ["../secret.pdf", "/abs/path.pdf", "C:/secret.pdf", "HR//file.pdf", "HR/./file.pdf"])
def test_normalize_relative_path_rejects_unsafe_paths(value):
    with pytest.raises(InvalidRelativePath):
        normalize_relative_path(value)


def test_folder_path_strips_collection_root():
    collection = Collection(id="col-1", name="HR", root_path="HR", created_by="user-1")

    assert folder_path_for_relative_path(collection, "HR/Thuong Tet/policy.pdf") == "Thuong Tet"


def test_build_embedding_text_adds_hierarchy_without_changing_content():
    document = Document(
        id="doc-1",
        filename="policy.pdf",
        storage_path="/tmp/policy.pdf",
        uploaded_by="user-1",
        relative_path="HR/Thuong Tet/policy.pdf",
    )
    content = "Điều kiện nhận thưởng Tết là làm đủ thời gian quy định."

    value = build_embedding_text(document, content, {"section_title": "II. Điều kiện"})

    assert "HR/Thuong Tet/policy.pdf" in value
    assert "II. Điều kiện" in value
    assert content in value
