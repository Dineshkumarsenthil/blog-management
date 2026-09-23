from datetime import datetime

from sqlalchemy.orm import Session

from services.email_service import send_email
from models import Notification


def _build_message(post_title: str, actor_name: str, activity: str, timestamp: datetime) -> str:
    return (
        f"Post: \"{post_title}\"\n"
        f"User: {actor_name}\n"
        f"Activity: {activity}\n"
        f"Time: {timestamp.strftime('%Y-%m-%d %I:%M %p')}"
    )


def notify_comment(owner_email: str, post_title: str, commenter_name: str) -> None:
    timestamp = datetime.now()
    body = _build_message(post_title, commenter_name, "Commented on your post", timestamp)
    send_email(owner_email, f"New comment on '{post_title}'", body)


def notify_like(owner_email: str, post_title: str, liker_name: str) -> None:
    timestamp = datetime.now()
    body = _build_message(post_title, liker_name, "Liked your post", timestamp)
    send_email(owner_email, f"New like on '{post_title}'", body)


def create_notification(db: Session, user_id: int, message: str, type: str) -> Notification:
    notif = Notification(user_id=user_id, message=message, type=type)
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif