from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------- User ----------
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


# ---------- Comment ----------
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


# ---------- Like ----------
class LikeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    user_id: int


class LikeStatus(BaseModel):
    liked: bool
    like_count: int


# ---------- Post ----------
# NOTE: PostCreate/PostUpdate are no longer used to parse the request body directly.
# Because the create/update endpoints now accept multipart/form-data (to support an
# optional image file), title/content are read as individual Form(...) fields in
# main.py. These two classes are kept for reference/documentation of the expected
# fields and are still used internally for validation.
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


class PaginatedPosts(BaseModel):
    """Response wrapper for GET /posts with pagination + search."""

    total: int
    page: int
    limit: int
    total_pages: int
    items: List[PostOut]