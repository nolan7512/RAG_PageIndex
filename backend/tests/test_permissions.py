from app.models import Document, User
from app.services.permissions import can_access_document


def test_owner_can_access_own_document():
    user = User(id="user-1", email="user@example.com", password_hash="x", role="user")
    document = Document(id="doc-1", filename="a.txt", storage_path="/tmp/a.txt", uploaded_by="user-1")

    assert can_access_document(user, document)


def test_regular_user_cannot_access_other_document():
    user = User(id="user-1", email="user@example.com", password_hash="x", role="user")
    document = Document(id="doc-1", filename="a.txt", storage_path="/tmp/a.txt", uploaded_by="user-2")

    assert not can_access_document(user, document)


def test_admin_can_access_any_document():
    user = User(id="admin-1", email="admin@example.com", password_hash="x", role="admin")
    document = Document(id="doc-1", filename="a.txt", storage_path="/tmp/a.txt", uploaded_by="user-2")

    assert can_access_document(user, document)
