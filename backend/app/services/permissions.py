from app.models import Document, User


def can_access_document(user: User, document: Document) -> bool:
    return user.role == "admin" or document.uploaded_by == user.id
