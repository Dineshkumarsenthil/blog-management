from typing import List

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import Base, SessionLocal, engine, get_db
from notifications import notify_new_comment, notify_new_like

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Blog Management API",
    description="A mini blogging system with posts, comments, likes and JWT auth.",
    version="1.0.0",
)

def get_post_or_404(db: Session, post_id: int) -> models.Post:
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


def serialize_post(db: Session, post: models.Post) -> schemas.PostOut:
    like_count = db.query(func.count(models.Like.id)).filter(
        models.Like.post_id == post.id
    ).scalar()
    comment_count = db.query(func.count(models.Comment.id)).filter(
        models.Comment.post_id == post.id
    ).scalar()
    return schemas.PostOut(
        id=post.id,
        title=post.title,
        content=post.content,
        author_id=post.author_id,
        created_at=post.created_at,
        like_count=like_count or 0,
        comment_count=comment_count or 0,
    )


# --------------------------------------------------------------------------
# Auth routes
# --------------------------------------------------------------------------
@app.post("/auth/register", response_model=schemas.UserOut, tags=["Auth"], status_code=201)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(models.User)
        .filter(
            (models.User.username == user.username) | (models.User.email == user.email)
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered",
        )

    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=auth.get_password_hash(user.password),
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered",
        )
    db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=schemas.Token, tags=["Auth"])
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == credentials.username).first()
    if not user or not auth.verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": str(user.id)})
    return schemas.Token(access_token=access_token)


# --------------------------------------------------------------------------
# Post routes
# --------------------------------------------------------------------------
@app.post("/posts", response_model=schemas.PostOut, tags=["Posts"], status_code=201)
def create_post(
    post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    new_post = models.Post(
        title=post.title, content=post.content, author_id=current_user.id
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return serialize_post(db, new_post)


@app.get("/posts", response_model=List[schemas.PostOut], tags=["Posts"])
def list_posts(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    posts = (
        db.query(models.Post)
        .order_by(models.Post.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [serialize_post(db, p) for p in posts]


@app.get("/posts/mine", response_model=List[schemas.PostOut], tags=["Posts"])
def my_posts(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    posts = (
        db.query(models.Post)
        .filter(models.Post.author_id == current_user.id)
        .order_by(models.Post.created_at.desc())
        .all()
    )
    return [serialize_post(db, p) for p in posts]


@app.get("/posts/{post_id}", response_model=schemas.PostDetailOut, tags=["Posts"])
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = get_post_or_404(db, post_id)
    base = serialize_post(db, post)
    comments = (
        db.query(models.Comment, models.User.username)
        .join(models.User, models.Comment.user_id == models.User.id)
        .filter(models.Comment.post_id == post_id)
        .order_by(models.Comment.created_at.asc())
        .all()
    )
    comment_list = []
    for comment, username in comments:
        c = schemas.CommentOut.model_validate(comment)
        c.username = username
        comment_list.append(c)

    return schemas.PostDetailOut(**base.model_dump(), comments=comment_list)


@app.put("/posts/{post_id}", response_model=schemas.PostOut, tags=["Posts"])
def update_post(
    post_id: int,
    post_update: schemas.PostUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    post = get_post_or_404(db, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this post",
        )
    if post_update.title is not None:
        post.title = post_update.title
    if post_update.content is not None:
        post.content = post_update.content
    db.commit()
    db.refresh(post)
    return serialize_post(db, post)


@app.delete("/posts/{post_id}", tags=["Posts"], status_code=204)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    post = get_post_or_404(db, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this post",
        )
    db.delete(post)
    db.commit()
    return None


# --------------------------------------------------------------------------
# Comment routes
# --------------------------------------------------------------------------
@app.post(
    "/posts/{post_id}/comments",
    response_model=schemas.CommentOut,
    tags=["Comments"],
    status_code=201,
)
def add_comment(
    post_id: int,
    comment: schemas.CommentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    post = get_post_or_404(db, post_id)

    new_comment = models.Comment(
        post_id=post_id, user_id=current_user.id, text=comment.text
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    # Notify the post owner (skip if commenting on your own post)
    if post.author_id != current_user.id:
        owner = db.query(models.User).filter(models.User.id == post.author_id).first()
        if owner:
            background_tasks.add_task(
                notify_new_comment, owner.email, post.title, current_user.username
            )

    out = schemas.CommentOut.model_validate(new_comment)
    out.username = current_user.username
    return out


@app.get(
    "/posts/{post_id}/comments", response_model=List[schemas.CommentOut], tags=["Comments"]
)
def list_comments(post_id: int, db: Session = Depends(get_db)):
    get_post_or_404(db, post_id)
    comments = (
        db.query(models.Comment, models.User.username)
        .join(models.User, models.Comment.user_id == models.User.id)
        .filter(models.Comment.post_id == post_id)
        .order_by(models.Comment.created_at.asc())
        .all()
    )
    result = []
    for comment, username in comments:
        c = schemas.CommentOut.model_validate(comment)
        c.username = username
        result.append(c)
    return result


# --------------------------------------------------------------------------
# Like routes
# --------------------------------------------------------------------------
@app.post("/posts/{post_id}/like", response_model=schemas.LikeStatus, tags=["Likes"])
def like_post(
    post_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    post = get_post_or_404(db, post_id)

    existing = (
        db.query(models.Like)
        .filter(models.Like.post_id == post_id, models.Like.user_id == current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You already liked this post"
        )

    new_like = models.Like(post_id=post_id, user_id=current_user.id)
    db.add(new_like)
    db.commit()

    if post.author_id != current_user.id:
        owner = db.query(models.User).filter(models.User.id == post.author_id).first()
        if owner:
            background_tasks.add_task(
                notify_new_like, owner.email, post.title, current_user.username
            )

    like_count = db.query(func.count(models.Like.id)).filter(
        models.Like.post_id == post_id
    ).scalar()
    return schemas.LikeStatus(liked=True, like_count=like_count or 0)


@app.delete("/posts/{post_id}/like", response_model=schemas.LikeStatus, tags=["Likes"])
def unlike_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    get_post_or_404(db, post_id)

    like = (
        db.query(models.Like)
        .filter(models.Like.post_id == post_id, models.Like.user_id == current_user.id)
        .first()
    )
    if not like:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You have not liked this post"
        )
    db.delete(like)
    db.commit()

    like_count = db.query(func.count(models.Like.id)).filter(
        models.Like.post_id == post_id
    ).scalar()
    return schemas.LikeStatus(liked=False, like_count=like_count or 0)


@app.get("/", tags=["Root"])
def root():
    return {"message": "Blog Management API is running. Visit /docs for Swagger UI."}
