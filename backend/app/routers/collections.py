from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Collection, Document, User
from app.schemas import CollectionCreate, CollectionOut, CollectionTreeOut
from app.services.hierarchy import can_access_collection, collection_tree, create_collection, visible_collections
from app.services.storage import remove_document_files


router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=CollectionOut)
def create_collection_endpoint(
    payload: CollectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return create_collection(db, current_user, payload.name, payload.root_path or payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[CollectionOut])
def list_collections(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return list(visible_collections(db, current_user))


@router.get("/{collection_id}/tree", response_model=CollectionTreeOut)
def get_collection_tree(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = db.query(Collection).filter(Collection.id == collection_id).one_or_none()
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    if not can_access_collection(current_user, collection):
        raise HTTPException(status_code=403, detail="Access denied")
    return collection_tree(db, collection)


@router.delete("/{collection_id}")
def delete_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = db.query(Collection).filter(Collection.id == collection_id).one_or_none()
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    if not can_access_collection(current_user, collection):
        raise HTTPException(status_code=403, detail="Access denied")

    document_ids = [row[0] for row in db.query(Document.id).filter(Document.collection_id == collection.id).all()]
    for document_id in document_ids:
        remove_document_files(document_id)
    db.query(Document).filter(Document.collection_id == collection.id).delete(synchronize_session=False)
    db.delete(collection)
    db.commit()
    return {"ok": True}
