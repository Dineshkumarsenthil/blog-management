"""
Email notification helper.

By default this runs in "console mode" — it prints the email that would be
sent instead of actually sending it, so the project runs out-of-the-box
without SMTP credentials.

To send real emails, set the environment variables below and set
SEND_REAL_EMAILS = True.

    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

SEND_REAL_EMAILS = os.getenv("SEND_REAL_EMAILS", "false").lower() == "true"

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)


def send_email(to_email: str, subject: str, body: str) -> None:
    if not SEND_REAL_EMAILS:
        print("----- EMAIL NOTIFICATION (console mode) -----")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(body)
        print("-----------------------------------------------")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:  # noqa: BLE001
        # Never let a notification failure break the main request flow.
        print(f"[notifications] Failed to send email to {to_email}: {e}")


def notify_new_comment(post_owner_email: str, post_title: str, commenter_username: str) -> None:
    subject = f"New comment on your post: {post_title}"
    body = (
        f"Hi,\n\n{commenter_username} commented on your post '{post_title}'.\n\n"
        "Log in to view the comment.\n\nBlog Management API"
    )
    send_email(post_owner_email, subject, body)


def notify_new_like(post_owner_email: str, post_title: str, liker_username: str) -> None:
    subject = f"New like on your post: {post_title}"
    body = (
        f"Hi,\n\n{liker_username} liked your post '{post_title}'.\n\n"
        "Log in to view it.\n\nBlog Management API"
    )
    send_email(post_owner_email, subject, body)
