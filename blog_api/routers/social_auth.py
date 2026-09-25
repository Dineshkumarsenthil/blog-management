from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import auth
import models
from database import SessionLocal
from auth0_config import oauth

router = APIRouter(prefix="/auth", tags=["Social Auth"])


@router.get("/login/{provider}")
async def social_login(request: Request, provider: str):
    if provider not in ("google", "facebook"):
        raise HTTPException(status_code=400, detail="Unsupported provider")

    connection = "google-oauth2" if provider == "google" else "facebook"
    redirect_uri = request.url_for("auth_callback")
    return await oauth.auth0.authorize_redirect(
        request, redirect_uri, connection=connection
    )


@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.auth0.authorize_access_token(request)
    except Exception:
        raise HTTPException(
            status_code=400, detail="Authentication failed or was cancelled."
        )

    userinfo = token.get("userinfo")
    if not userinfo or not userinfo.get("sub") or not userinfo.get("email"):
        raise HTTPException(
            status_code=400, detail="Missing user details from provider callback."
        )

    sub = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name") or email.split("@")[0]
    provider = "google" if sub.startswith("google") else "facebook"

    db: Session = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.auth0_sub == sub).first()

        if not user:
            existing = db.query(models.User).filter(models.User.email == email).first()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail="An account with this email already exists. "
                    "Please log in with your password instead.",
                )

            basic_plan = db.query(models.SubscriptionPlan).filter_by(name="Basic").first()
            user = models.User(
                username=name.replace(" ", "_").lower()[:50],
                email=email,
                hashed_password=None,
                auth_provider=provider,
                auth0_sub=sub,
                plan_id=basic_plan.id if basic_plan else None,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        access_token = auth.create_access_token(data={"sub": str(user.id)})

    finally:
        db.close()

    return RedirectResponse(
        url=f"/static/dashboard.html?token={access_token}"
    )