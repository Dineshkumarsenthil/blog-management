from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from models import Notification, User
from schemas import NotificationOut, NotificationSummary

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/", response_model=NotificationSummary)
def list_notifications(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    notifs = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    unread = sum(1 for n in notifs if not n.is_read)
    return {"unread_count": unread, "items": notifs}


@router.put("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if notif:
        notif.is_read = True
        db.commit()
        db.refresh(notif)
    return notif


@router.put("/read-all")
def mark_all_read(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    db.query(Notification).filter(
        Notification.user_id == current_user.id, Notification.is_read == False  # noqa: E712
    ).update({"is_read": True})
    db.commit()
    return {"success": True}