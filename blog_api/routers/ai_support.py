from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from models import User
from schemas import ChatMessageCreate, ChatMessageOut
from services.ai_support_service import get_ai_response, log_chat

router = APIRouter(prefix="/api/ai-support", tags=["AI Support"])


@router.post("/", response_model=ChatMessageOut)
def ai_support_chat(
    body: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reply = get_ai_response(body.message)
    entry = log_chat(db, current_user.id, body.message, reply)
    return entry