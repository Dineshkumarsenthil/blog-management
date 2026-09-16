import math
from typing import List, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import Base, SessionLocal, engine, get_db
from notifications import notify_new_comment, notify_new_like
from uploads import MEDIA_ROOT, delete_post_image, save_post_image

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Blog Management API",
    description="A mini blogging system with posts, comments, likes and JWT auth.",
    version="1.1.0",
)

# Serve uploaded post images at /media/posts/<filename>
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
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
        image_url=post.image,
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
    title: str = Form(..., min_length=1, max_length=200),
    content: str = Form(..., min_length=1),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Create a post. Accepts multipart/form-data so an optional cover image can
    be attached alongside title/content. In Swagger, this shows up as regular
    form fields (title, content) plus a file picker (image) — not a JSON body.
    """
    image_url = save_post_image(image)

    new_post = models.Post(
        title=title, content=content, author_id=current_user.id, image=image_url
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return serialize_post(db, new_post)


@app.get("/posts", response_model=schemas.PaginatedPosts, tags=["Posts"])
def list_posts(
    page: int = Query(1, ge=1, description="Page number, starting at 1"),
    limit: int = Query(10, ge=1, le=100, description="Posts per page (max 100)"),
    search: Optional[str] = Query(
        None, min_length=1, description="Search posts by title or content"
    ),
    db: Session = Depends(get_db),
):
    """
    List posts with pagination and optional search.
    Example: GET /posts?page=2&limit=10&search=fastapi
    Search and pagination compose together — search first narrows the result
    set, then pagination slices that narrowed set.
    """
    query = db.query(models.Post)

    if search:
        like_pattern = f"%{search}%"
        query = query.filter(
            or_(models.Post.title.ilike(like_pattern), models.Post.content.ilike(like_pattern))
        )

    total = query.count()
    total_pages = max(1, math.ceil(total / limit)) if total else 0

    posts = (
        query.order_by(models.Post.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return schemas.PaginatedPosts(
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        items=[serialize_post(db, p) for p in posts],
    )


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
    title: Optional[str] = Form(None, min_length=1, max_length=200),
    content: Optional[str] = Form(None, min_length=1),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Update a post. Also multipart/form-data, so an owner can replace the
    cover image the same way they set it on create. All fields are optional —
    send only what you want to change. Uploading a new image replaces (and
    deletes) the old one; title/content are left untouched if omitted.
    """
    post = get_post_or_404(db, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this post",
        )
    if title is not None:
        post.title = title
    if content is not None:
        post.content = content
    if image is not None and image.filename:
        new_image_url = save_post_image(image)
        old_image_url = post.image
        post.image = new_image_url
        delete_post_image(old_image_url)

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
    delete_post_image(post.image)
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