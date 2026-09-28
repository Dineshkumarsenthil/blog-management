from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, EmailStr, Field, ConfigDict

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    created_at: datetime


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    user_id: int
    text: str
    created_at: datetime
    username: Optional[str] = None

class LikeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    user_id: int


class LikeStatus(BaseModel):
    liked: bool
    like_count: int

class PostImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    image_url: str
    created_at: datetime

class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    author_id: int
    created_at: datetime
    like_count: int = 0
    comment_count: int = 0
    image_url: Optional[str] = None


class PostDetailOut(PostOut):
    comments: List[CommentOut] = []
    images: List[PostImageOut] = []


class PaginatedPosts(BaseModel):
    """Response wrapper for GET /posts with pagination + search."""

    total: int
    page: int
    limit: int
    total_pages: int
    items: List[PostOut]

class SubscriptionPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: float
    max_posts: int
    max_images_per_post: int
    max_likes: int
    max_comments: int
    is_unlimited: bool


class SubscribeRequest(BaseModel):
    plan_name: str = Field(..., description="One of: Basic, Premium, Pro")


class BillingHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    plan_id: int
    plan_name: Optional[str] = None
    price: float
    transaction_id: str
    start_date: datetime
    end_date: datetime
    invoice_url: Optional[str] = None
    created_at: datetime


class UsageOut(BaseModel):
    """Current usage vs. plan limits, for GET /subscriptions/me."""

    plan: SubscriptionPlanOut
    posts_used: int
    likes_used: int
    comments_used: int

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message: str
    type: str
    is_read: bool
    created_at: datetime


class NotificationSummary(BaseModel):
    """Response wrapper for GET /notifications — list + unread count."""

    unread_count: int
    items: List[NotificationOut]

class ChatMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    response: str
    created_at: datetime

PublishOption = Literal["draft", "publish", "schedule"]


class BlogCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    scheduled_at: Optional[datetime] = None
    publish_option: Optional[PublishOption] = Field(
        None,
        description="draft | publish | schedule. If omitted: publishes now when "
        "scheduled_at is null, schedules when scheduled_at is set.",
    )


class BlogUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    scheduled_at: Optional[datetime] = None
    publish_option: Optional[PublishOption] = None


class BlogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    author_id: int
    status: str
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime