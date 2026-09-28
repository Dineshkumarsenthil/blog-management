import asyncio
from datetime import datetime

import models
from database import SessionLocal

CHECK_INTERVAL_SECONDS = 15


def publish_due_posts() -> int:
    """Publish every scheduled post whose scheduled_at time has been reached."""
    now = datetime.now()
    db = SessionLocal()
    try:
        due_posts = (
            db.query(models.Post)
            .filter(models.Post.status == "scheduled", models.Post.scheduled_at <= now)
            .all()
        )
        for post in due_posts:
            post.status = "published"
            post.published_at = now
        db.commit()
        return len(due_posts)
    finally:
        db.close()


async def scheduler_loop():
    """Background loop started with the app; runs until the server shuts down."""
    while True:
        try:
            published = await asyncio.to_thread(publish_due_posts)
            if published:
                print(f"[scheduler] auto-published {published} post(s)")
        except Exception as exc:
            print(f"[scheduler] error: {exc}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)