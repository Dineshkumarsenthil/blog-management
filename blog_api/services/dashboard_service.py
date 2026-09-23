from sqlalchemy import func
from sqlalchemy.orm import Session

import models


def get_user_dashboard(db: Session, current_user: models.User) -> dict:
    total_posts = db.query(func.count(models.Post.id)).filter(
        models.Post.author_id == current_user.id
    ).scalar() or 0

    total_comments = db.query(func.count(models.Comment.id)).filter(
        models.Comment.user_id == current_user.id
    ).scalar() or 0

    total_likes_received = (
        db.query(func.count(models.Like.id))
        .join(models.Post, models.Like.post_id == models.Post.id)
        .filter(models.Post.author_id == current_user.id)
        .scalar()
        or 0
    )

    posts = (
        db.query(models.Post)
        .filter(models.Post.author_id == current_user.id)
        .order_by(models.Post.created_at.asc())
        .all()
    )

    post_breakdown = []
    for post in posts:
        like_count = db.query(func.count(models.Like.id)).filter(
            models.Like.post_id == post.id
        ).scalar() or 0
        comment_count = db.query(func.count(models.Comment.id)).filter(
            models.Comment.post_id == post.id
        ).scalar() or 0

        post_breakdown.append({
            "post_id": post.id,
            "title": post.title,
            "likes": like_count,
            "comments": comment_count,
            "created_at": post.created_at.isoformat(),
        })

    return {
        "total_posts": total_posts,
        "total_comments": total_comments,
        "total_likes_received": total_likes_received,
        "posts": post_breakdown,
    }