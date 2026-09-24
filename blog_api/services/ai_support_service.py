import re

from sqlalchemy.orm import Session

from models import ChatLog

STOPWORDS = {
    "a", "an", "the", "is", "are", "how", "do", "does", "can", "i", "to",
    "for", "of", "on", "in", "my", "me", "what", "when", "where", "you",
    "your", "it", "and", "or", "with", "this", "that", "please", "pls",
}

FAQ_RULES = [
    (
        "POST /auth/register",
        ["register", "sign up", "signup", "create account", "create an account",
         "new account", "new user"],
        "To register, send a POST request to /auth/register with a username, "
        "email, and password. You'll be placed on the Basic plan automatically.",
    ),
    (
        "POST /auth/login",
        ["login", "log in", "sign in", "get token", "get my token", "auth token"],
        "To log in, send a POST request to /auth/login with your username and "
        "password. You'll receive a JWT access token to use in the "
        "Authorization header for every other request.",
    ),
    (
        "POST /posts",
        ["create post", "create a post", "new post", "add post", "add a post",
         "write post", "write a post", "make a post", "publish post",
         "how to post", "how do i post"],
        "To create a post, send a POST request to /posts with a title, "
        "content, and an optional cover image. Your subscription plan's post "
        "limit applies.",
    ),
    (
        "GET /posts",
        ["list posts", "all posts", "browse posts", "search post",
         "search posts", "find post", "find posts"],
        "To browse or search all posts, use GET /posts — it supports "
        "pagination and searching by title or content.",
    ),
    (
        "GET /posts/mine",
        ["my posts", "posts i made", "posts i created", "my own posts"],
        "To see only the posts you've created, use GET /posts/mine.",
    ),
    (
        "GET /posts/{post_id}",
        ["view post", "see post", "get post", "read post", "single post",
         "open post", "view a post"],
        "To view one specific post along with its comments, use GET "
        "/posts/{post_id}.",
    ),
    (
        "PUT /posts/{post_id}",
        ["update post", "update a post", "edit post", "edit a post",
         "change post", "change a post", "modify post", "modify a post"],
        "To edit a post, send a PUT request to /posts/{post_id} with the "
        "fields you want to change. Only the post's original author can "
        "update it.",
    ),
    (
        "DELETE /posts/{post_id}",
        ["delete post", "delete a post", "remove post", "remove a post"],
        "To delete a post, send a DELETE request to /posts/{post_id}. Only "
        "the post's original author can delete it.",
    ),
    (
        "POST /posts/{post_id}/images",
        ["add image", "upload image", "extra image", "another image",
         "more images", "post image", "add post image", "attach image"],
        "To attach an extra image to an existing post, send a POST request "
        "to /posts/{post_id}/images. Your subscription plan limits how many "
        "images each post can have.",
    ),
    (
        "POST /posts/{post_id}/comments",
        ["add comment", "post comment", "leave comment", "write comment",
         "comment on", "make a comment", "how to comment"],
        "To comment on a post, send a POST request to /posts/{post_id}/comments "
        "with your comment text. The post's author gets notified.",
    ),
    (
        "GET /posts/{post_id}/comments",
        ["view comment", "see comment", "list comment", "list comments",
         "read comment", "all comments"],
        "To see all comments on a post, use GET /posts/{post_id}/comments.",
    ),
    (
        "POST /posts/{post_id}/like",
        ["like a post", "like post", "how to like", "give a like",
         "like this"],
        "To like a post, send a POST request to /posts/{post_id}/like. Each "
        "user can only like a post once, and the author gets notified.",
    ),
    (
        "DELETE /posts/{post_id}/like",
        ["unlike", "remove like", "undo like", "take back like"],
        "To remove a like, send a DELETE request to /posts/{post_id}/like.",
    ),
    (
        "GET /subscriptions/plans",
        ["subscription plan", "list plans", "available plans", "which plan",
         "compare plan", "what plans"],
        "To see all available subscription plans and their limits, use GET "
        "/subscriptions/plans.",
    ),
    (
        "POST /subscriptions/subscribe",
        ["subscribe", "upgrade", "change plan", "buy plan", "get premium",
         "get pro", "how to subscribe"],
        "To subscribe or upgrade, send a POST request to "
        "/subscriptions/subscribe with the plan name (Basic, Premium, or "
        "Pro).",
    ),
    (
        "GET /subscriptions/me",
        ["my subscription", "current plan", "usage", "how many posts",
         "post limit", "like limit", "comment limit", "my plan", "my usage"],
        "To check your current plan and usage against its limits, use GET "
        "/subscriptions/me.",
    ),
    (
        "GET /billing/me",
        ["my billing", "my invoice", "billing history", "past payment",
         "my transaction", "my payments"],
        "Your own billing and invoice history is available at GET "
        "/billing/me.",
    ),
    (
        "GET /billing",
        ["all billing", "everyone's billing", "billing records",
         "all invoices", "all transactions"],
        "To see billing history across all users (admin view), use GET "
        "/billing.",
    ),
    (
        "GET /user/dashboard",
        ["dashboard", "analytics", "stats", "statistics", "chart",
         "activity summary", "my activity"],
        "Your Activity Dashboard (GET /user/dashboard) shows total posts, "
        "comments made, and likes received, with charts breaking it down "
        "per post.",
    ),
    (
        "GET /notifications/",
        ["list notification", "list notifications", "see notification",
         "my notifications", "view notification", "check notification"],
        "To see your notifications and unread count, use GET /notifications/.",
    ),
    (
        "PUT /notifications/{id}/read",
        ["mark read", "mark as read", "read notification",
         "mark one as read"],
        "To mark a single notification as read, send a PUT request to "
        "/notifications/{notification_id}/read.",
    ),
    (
        "PUT /notifications/read-all",
        ["mark all read", "clear notification", "clear all notifications",
         "read all"],
        "To mark every notification as read at once, send a PUT request to "
        "/notifications/read-all.",
    ),
    (
        "general/notifications",
        ["notification", "bell", "alert"],
        "The bell icon shows notifications for likes, comments, and "
        "subscription updates — you can list them and mark them read.",
    ),
    (
        "general/profile",
        ["profile", "account", "my email", "my username", "my password"],
        "Your account details are set at registration via POST "
        "/auth/register. There isn't a separate profile-edit endpoint yet.",
    ),
    (
        "general/greeting",
        ["hello", "hi", "hey"],
        "Hi there! I'm your support assistant. Ask me how to create, edit, "
        "or delete a post, use likes and comments, manage your subscription "
        "and billing, or check your dashboard and notifications.",
    ),
    (
        "general/help",
        ["help", "what can you do", "what do you do"],
        "I can help with every part of this platform: posts (create, edit, "
        "delete, view), comments, likes, subscriptions, billing, your "
        "dashboard, and notifications. Just ask in plain language.",
    ),
]

DEFAULT_RESPONSE = (
    "I'm not fully sure about that yet. I can help with posts (create, "
    "edit, delete, view), comments, likes, subscriptions, billing, your "
    "dashboard, or notifications — try rephrasing around one of those."
)


def _tokenize(text: str):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS]


def get_ai_response(message: str) -> str:
    lowered = message.lower()

    for _label, keywords, response in FAQ_RULES:
        if any(keyword in lowered for keyword in keywords):
            return response

   
    message_words = set(_tokenize(message))
    if not message_words:
        return DEFAULT_RESPONSE

    best_response = None
    best_score = 0
    for _label, keywords, response in FAQ_RULES:
        rule_words = set()
        for phrase in keywords:
            rule_words.update(_tokenize(phrase))
        score = len(message_words & rule_words)
        if score > best_score:
            best_score = score
            best_response = response

    if best_score >= 1:
        return best_response
    return DEFAULT_RESPONSE


def log_chat(db: Session, user_id: int, question: str, response: str) -> ChatLog:
    entry = ChatLog(user_id=user_id, question=question, response=response)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry