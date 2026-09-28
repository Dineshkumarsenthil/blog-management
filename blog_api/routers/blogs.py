from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import auth
import models
import schemas
import subscriptions
from database import get_db

router = APIRouter(prefix="/api/blogs", tags=["Scheduled Blogs"])


def _to_naive_local(dt: Optional[datetime]) -> Optional[datetime]:
    """Accept naive or timezone-aware input; store everything as naive server-local time."""
    if dt is not None and dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def resolve_publish_state(option: Optional[str], scheduled_at: Optional[datetime]):
    """Validate the author's publish choice.

    Returns (status, scheduled_at, published_at) ready to store on the post.
    """
    now = datetime.now()
    scheduled_at = _to_naive_local(scheduled_at)

    if option == "draft":
        if scheduled_at is not None:
            raise HTTPException(status_code=422, detail="Draft posts cannot have scheduled_at set.")
        return "draft", None, None

    if option == "publish":
        if scheduled_at is not None:
            raise HTTPException(
                status_code=422, detail="Publish Now cannot be combined with scheduled_at."
            )
        return "published", None, now

    if option == "schedule" and scheduled_at is None:
        raise HTTPException(
            status_code=422, detail="scheduled_at is required when scheduling a post."
        )

    if scheduled_at is None:
        return "published", None, now  # no date given -> publish immediately

    if scheduled_at <= now:
        raise HTTPException(
            status_code=422, detail="scheduled_at must be a future date and time."
        )
    return "scheduled", scheduled_at, None


def _get_own_blog(db: Session, blog_id: int, user: models.User) -> models.Post:
    post = db.query(models.Post).filter(models.Post.id == blog_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.author_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to access this post")
    return post


@router.post("", response_model=schemas.BlogOut, status_code=201)
def create_blog(
    body: schemas.BlogCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Create a post as a draft, publish it now, or schedule it for a future time."""
    subscriptions.check_post_limit(db, current_user)
    post_status, scheduled_at, published_at = resolve_publish_state(
        body.publish_option, body.scheduled_at
    )

    post = models.Post(
        title=body.title,
        content=body.content,
        author_id=current_user.id,
        status=post_status,
        scheduled_at=scheduled_at,
        published_at=published_at,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.get("/mine", response_model=List[schemas.BlogOut])
def my_blogs(
    status_filter: Optional[str] = Query(
        None, alias="status", pattern="^(draft|scheduled|published)$"
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """The current user's posts in every state, optionally filtered by status."""
    query = db.query(models.Post).filter(models.Post.author_id == current_user.id)
    if status_filter:
        query = query.filter(models.Post.status == status_filter)
    return query.order_by(models.Post.created_at.desc()).all()


@router.get("/{blog_id}", response_model=schemas.BlogOut)
def get_blog(
    blog_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return _get_own_blog(db, blog_id, current_user)


@router.put("/{blog_id}", response_model=schemas.BlogOut)
def update_blog(
    blog_id: int,
    body: schemas.BlogUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Edit a post and/or move it along Draft -> Scheduled -> Published."""
    post = _get_own_blog(db, blog_id, current_user)

    if body.publish_option is not None or body.scheduled_at is not None:
        if post.status == "published":
            raise HTTPException(
                status_code=400,
                detail="This post is already published; its publish status can no longer be changed.",
            )
        new_status, scheduled_at, published_at = resolve_publish_state(
            body.publish_option, body.scheduled_at
        )
        post.status = new_status
        post.scheduled_at = scheduled_at
        post.published_at = published_at

    if body.title is not None:
        post.title = body.title
    if body.content is not None:
        post.content = body.content

    db.commit()
    db.refresh(post)
    return post