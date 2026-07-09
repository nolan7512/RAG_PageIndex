from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import SearchRequest, SearchResultOut
from app.services.embeddings import OpenAIUnavailable
from app.services.retrieval import result_to_dict, retrieve_chunks


router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=list[SearchResultOut])
def search(payload: SearchRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = payload.query.strip()
    if not query:
        return []
    try:
        results = retrieve_chunks(db, current_user, query, limit=max(1, min(payload.limit, 30)))
    except OpenAIUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [result_to_dict(result) for result in results]
