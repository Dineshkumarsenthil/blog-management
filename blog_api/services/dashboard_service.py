from sqlalchemy import func
from sqlalchemy.orm import Session

import models


def get_user_dashboard(db: Session, user: models.User) -> dict:
    posts = (
        db.query(models.Post)
        .filter(models.Post.author_id == user.id)
        .order_by(models.Post.created_at.asc())
        .all()
    )

    total_posts = len(posts)

    total_comments = db.query(func.count(models.Comment.id)).filter(
        models.Comment.user_id == user.id
    ).scalar() or 0

    post_ids = [p.id for p in posts]
    total_likes_received = 0
    per_post = []

    if post_ids:
        total_likes_received = db.query(func.count(models.Like.id)).filter(
            models.Like.post_id.in_(post_ids)
        ).scalar() or 0

        for post in posts:
            like_count = db.query(func.count(models.Like.id)).filter(
                models.Like.post_id == post.id
            ).scalar() or 0
            comment_count = db.query(func.count(models.Comment.id)).filter(
                models.Comment.post_id == post.id
            ).scalar() or 0
            per_post.append({
                "post_id": post.id,
                "title": post.title,
                "likes": like_count,
                "comments": comment_count,
                "created_at": post.created_at.isoformat() if post.created_at else None,
            })

    return {
        "total_posts": total_posts,
        "total_comments": total_comments,
        "total_likes_received": total_likes_received,
        "posts": per_post,
    }