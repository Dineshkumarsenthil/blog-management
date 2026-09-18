from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, status
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy import func
from sqlalchemy.orm import Session

import models

LIMIT_MESSAGE = "You've reached your plan limit. Kindly upgrade your plan to continue."

PLAN_DEFINITIONS = [
    # name,      price,  max_posts, max_images_per_post, max_likes, max_comments
    ("Basic",    0.0,    1,         1,                    3,         3),
    ("Premium",  9.99,   2,         2,                    10,        10),
    ("Pro",      29.99,  -1,        -1,                   -1,        -1),
]

INVOICES_DIR = Path("media") / "invoices"
INVOICES_DIR.mkdir(parents=True, exist_ok=True)


def seed_plans(db: Session) -> None:
    """Create the three plans if they don't already exist. Safe to call every startup."""
    for name, price, max_posts, max_images, max_likes, max_comments in PLAN_DEFINITIONS:
        existing = db.query(models.SubscriptionPlan).filter_by(name=name).first()
        if existing:
            continue
        db.add(
            models.SubscriptionPlan(
                name=name,
                price=price,
                max_posts=max_posts,
                max_images_per_post=max_images,
                max_likes=max_likes,
                max_comments=max_comments,
                is_unlimited=(name == "Pro"),
            )
        )
    db.commit()


def get_user_plan(db: Session, user: models.User) -> models.SubscriptionPlan:
    """A user should always have a plan (set at registration), but fall back to Basic
    defensively in case of older data."""
    if user.plan_id:
        plan = db.query(models.SubscriptionPlan).filter_by(id=user.plan_id).first()
        if plan:
            return plan
    return db.query(models.SubscriptionPlan).filter_by(name="Basic").first()


def _enforce(current: int, limit: int) -> None:
    if limit != -1 and current >= limit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=LIMIT_MESSAGE)


def check_post_limit(db: Session, user: models.User) -> None:
    plan = get_user_plan(db, user)
    current = db.query(func.count(models.Post.id)).filter(
        models.Post.author_id == user.id
    ).scalar() or 0
    _enforce(current, plan.max_posts)


def check_image_limit(db: Session, user: models.User, post: models.Post, adding: int = 1) -> None:
    """post must belong to user (ownership already checked by the caller)."""
    plan = get_user_plan(db, user)
    if plan.max_images_per_post == -1:
        return
    current = (1 if post.image else 0) + (
        db.query(func.count(models.PostImage.id)).filter(
            models.PostImage.post_id == post.id
        ).scalar()
        or 0
    )
    if current + adding > plan.max_images_per_post:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=LIMIT_MESSAGE)


def check_like_limit(db: Session, user: models.User) -> None:
    plan = get_user_plan(db, user)
    current = db.query(func.count(models.Like.id)).filter(
        models.Like.user_id == user.id
    ).scalar() or 0
    _enforce(current, plan.max_likes)


def check_comment_limit(db: Session, user: models.User) -> None:
    plan = get_user_plan(db, user)
    current = db.query(func.count(models.Comment.id)).filter(
        models.Comment.user_id == user.id
    ).scalar() or 0
    _enforce(current, plan.max_comments)


def generate_invoice_pdf(
    user: models.User, plan: models.SubscriptionPlan, transaction_id: str,
    start_date: datetime, end_date: datetime,
) -> str:
    """Renders a simple invoice PDF with ReportLab and saves it under media/invoices/.
    Returns the URL path to store on BillingHistory.invoice_path."""
    filename = f"{uuid4().hex}.pdf"
    file_path = INVOICES_DIR / filename

    c = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, y, "Blog Management API — Invoice")
    y -= 12 * mm

    c.setFont("Helvetica", 11)
    lines = [
        f"Transaction ID: {transaction_id}",
        f"User Name: {user.username}",
        f"Email: {user.email}",
        f"Plan: {plan.name}",
        f"Price: ${plan.price:.2f}",
        f"Start Date: {start_date.strftime('%Y-%m-%d')}",
        f"End Date: {end_date.strftime('%Y-%m-%d')}",
        f"Issued: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    ]
    for line in lines:
        c.drawString(20 * mm, y, line)
        y -= 8 * mm

    y -= 5 * mm
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(20 * mm, y, "This is a system-generated sample invoice for demo purposes.")

    c.showPage()
    c.save()

    return f"/media/invoices/{filename}"


def subscribe_user(db: Session, user: models.User, plan_name: str) -> models.BillingHistory:
    plan = db.query(models.SubscriptionPlan).filter_by(name=plan_name).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown plan '{plan_name}'. Choose one of: Basic, Premium, Pro.",
        )

    user.plan_id = plan.id

    transaction_id = f"TXN-{uuid4().hex[:12].upper()}"
    start_date = datetime.now(timezone.utc)
    end_date = start_date + timedelta(days=30)

    invoice_path = generate_invoice_pdf(user, plan, transaction_id, start_date, end_date)

    billing = models.BillingHistory(
        user_id=user.id,
        plan_id=plan.id,
        price=plan.price,
        transaction_id=transaction_id,
        start_date=start_date,
        end_date=end_date,
        invoice_path=invoice_path,
    )
    db.add(billing)
    db.commit()
    db.refresh(billing)
    return billing