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
from sqladmin import Admin, ModelView 

import auth
import models
import schemas
import subscriptions
from database import Base, SessionLocal, engine, get_db
from services.notification_service import notify_comment, notify_like, create_notification
from services.dashboard_service import get_user_dashboard  # NEW
from uploads import MEDIA_ROOT, delete_post_image, save_post_image
from routers import notifications, ai_support

Base.metadata.create_all(bind=engine)

with SessionLocal() as _db:
    subscriptions.seed_plans(_db)

app = FastAPI(
    title="Blog Management API",
    description="A mini blogging system with posts, comments, likes, JWT auth, "
    "and subscription-based feature limits.",
    version="1.2.0",
)


app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")

app.mount("/static", StaticFiles(directory="static"), name="static")


admin = Admin(app, engine)


class UserAdmin(ModelView, model=models.User):
    name = "User"
    name_plural = "Users"
    column_list = [models.User.id, models.User.username, models.User.email, models.User.plan_id, models.User.created_at]
    column_searchable_list = [models.User.username, models.User.email]


class PostAdmin(ModelView, model=models.Post):
    name = "Post"
    name_plural = "Posts"
    column_list = [models.Post.id, models.Post.title, models.Post.author_id, models.Post.created_at]
    column_searchable_list = [models.Post.title]


class SubscriptionPlanAdmin(ModelView, model=models.SubscriptionPlan):
    name = "Subscription Plan"
    name_plural = "Subscription Plans"
    column_list = [
        models.SubscriptionPlan.id,
        models.SubscriptionPlan.name,
        models.SubscriptionPlan.price,
        models.SubscriptionPlan.max_posts,
        models.SubscriptionPlan.max_images_per_post,
        models.SubscriptionPlan.max_likes,
        models.SubscriptionPlan.max_comments,
        models.SubscriptionPlan.is_unlimited,
    ]


class BillingHistoryAdmin(ModelView, model=models.BillingHistory):
    name = "Billing Record"
    name_plural = "Billing History"
    column_list = [
        models.BillingHistory.id,
        models.BillingHistory.user_id,
        models.BillingHistory.plan_id,
        models.BillingHistory.price,
        models.BillingHistory.transaction_id,
        models.BillingHistory.start_date,
        models.BillingHistory.end_date,
        models.BillingHistory.invoice_path,
        models.BillingHistory.created_at,
    ]
    column_searchable_list = [models.BillingHistory.transaction_id]


admin.add_view(UserAdmin)
admin.add_view(PostAdmin)
admin.add_view(SubscriptionPlanAdmin)
admin.add_view(BillingHistoryAdmin)


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

    basic_plan = db.query(models.SubscriptionPlan).filter_by(name="Basic").first()
    if basic_plan:
        new_user.plan_id = basic_plan.id
        db.commit()
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

@app.post("/posts", response_model=schemas.PostOut, tags=["Posts"], status_code=201)
def create_post(
    title: str = Form(..., min_length=1, max_length=200),
    content: str = Form(..., min_length=1),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):

    subscriptions.check_post_limit(db, current_user)

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

    extra_images = (
        db.query(models.PostImage)
        .filter(models.PostImage.post_id == post_id)
        .order_by(models.PostImage.created_at.asc())
        .all()
    )
    image_list = [
        schemas.PostImageOut(
            id=img.id, post_id=img.post_id, image_url=img.image, created_at=img.created_at
        )
        for img in extra_images
    ]

    return schemas.PostDetailOut(**base.model_dump(), comments=comment_list, images=image_list)


@app.put("/posts/{post_id}", response_model=schemas.PostOut, tags=["Posts"])
def update_post(
    post_id: int,
    title: Optional[str] = Form(None, min_length=1, max_length=200),
    content: Optional[str] = Form(None, min_length=1),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):

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
    for img in post.extra_images:
        delete_post_image(img.image)
    db.delete(post)
    db.commit()
    return None


@app.post(
    "/posts/{post_id}/images",
    response_model=schemas.PostImageOut,
    tags=["Posts"],
    status_code=201,
)
def add_post_image(
    post_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    post = get_post_or_404(db, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this post",
        )

    subscriptions.check_image_limit(db, current_user, post, adding=1)

    image_url = save_post_image(image)
    new_image = models.PostImage(post_id=post.id, image=image_url)
    db.add(new_image)
    db.commit()
    db.refresh(new_image)

    return schemas.PostImageOut(
        id=new_image.id,
        post_id=new_image.post_id,
        image_url=new_image.image,
        created_at=new_image.created_at,
    )

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
    subscriptions.check_comment_limit(db, current_user)

    new_comment = models.Comment(
        post_id=post_id, user_id=current_user.id, text=comment.text
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)


    if post.author_id != current_user.id:
        owner = db.query(models.User).filter(models.User.id == post.author_id).first()
        if owner:
            background_tasks.add_task(
                notify_comment, owner.email, post.title, current_user.username
            )
            create_notification(
                db, post.author_id,
                f'{current_user.username} commented on your post "{post.title}"',
                "comment"
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

    subscriptions.check_like_limit(db, current_user)

    new_like = models.Like(post_id=post_id, user_id=current_user.id)
    db.add(new_like)
    db.commit()

    if post.author_id != current_user.id:
        owner = db.query(models.User).filter(models.User.id == post.author_id).first()
        if owner:
            background_tasks.add_task(
                notify_like, owner.email, post.title, current_user.username
            )
            create_notification(
                db, post.author_id,
                f'{current_user.username} liked your post "{post.title}"',
                "like"
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


def _billing_out(b: models.BillingHistory) -> schemas.BillingHistoryOut:
    return schemas.BillingHistoryOut(
        id=b.id,
        user_id=b.user_id,
        plan_id=b.plan_id,
        plan_name=b.plan.name if b.plan else None,
        price=b.price,
        transaction_id=b.transaction_id,
        start_date=b.start_date,
        end_date=b.end_date,
        invoice_url=b.invoice_path,
        created_at=b.created_at,
    )


@app.get("/subscriptions/plans", response_model=List[schemas.SubscriptionPlanOut], tags=["Subscriptions"])
def list_plans(db: Session = Depends(get_db)):
    
    return db.query(models.SubscriptionPlan).order_by(models.SubscriptionPlan.price.asc()).all()


@app.post("/subscriptions/subscribe", response_model=schemas.BillingHistoryOut, tags=["Subscriptions"])
def subscribe(
    body: schemas.SubscribeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
 
    billing = subscriptions.subscribe_user(db, current_user, body.plan_name)

    create_notification(
        db, current_user.id,
        f'Your subscription to the "{body.plan_name}" plan is now active',
        "subscription"
    )

    return _billing_out(billing)


@app.get("/subscriptions/me", response_model=schemas.UsageOut, tags=["Subscriptions"])
def my_subscription(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    
    plan = subscriptions.get_user_plan(db, current_user)
    posts_used = db.query(func.count(models.Post.id)).filter(
        models.Post.author_id == current_user.id
    ).scalar() or 0
    likes_used = db.query(func.count(models.Like.id)).filter(
        models.Like.user_id == current_user.id
    ).scalar() or 0
    comments_used = db.query(func.count(models.Comment.id)).filter(
        models.Comment.user_id == current_user.id
    ).scalar() or 0

    return schemas.UsageOut(
        plan=plan, posts_used=posts_used, likes_used=likes_used, comments_used=comments_used
    )


@app.get("/billing/me", response_model=List[schemas.BillingHistoryOut], tags=["Billing"])
def my_billing_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    
    rows = (
        db.query(models.BillingHistory)
        .filter(models.BillingHistory.user_id == current_user.id)
        .order_by(models.BillingHistory.created_at.desc())
        .all()
    )
    return [_billing_out(b) for b in rows]


@app.get("/billing", response_model=List[schemas.BillingHistoryOut], tags=["Billing"])
def all_billing_history(db: Session = Depends(get_db)):
    rows = db.query(models.BillingHistory).order_by(models.BillingHistory.created_at.desc()).all()
    return [_billing_out(b) for b in rows]


@app.get("/user/dashboard", tags=["Dashboard"])
def user_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return get_user_dashboard(db, current_user)


app.include_router(notifications.router)
app.include_router(ai_support.router)


@app.get("/", tags=["Root"])
def root():
    return {"message": "Blog Management API is running. Visit /docs for Swagger UI."}