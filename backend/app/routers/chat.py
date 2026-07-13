from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import ChatRequest, ChatResponse
from app.services.chat import answer_question
from app.services.embeddings import OpenAIUnavailable


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    try:
        answer, conversation, citations = answer_question(
            db,
            current_user,
            message,
            payload.conversation_id,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
        )
    except OpenAIUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChatResponse(answer=answer, conversation_id=conversation.id, citations=citations)
