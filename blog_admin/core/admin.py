from django.contrib import admin
from django.utils.html import format_html
from .models import User, SubscriptionPlan, Post, BillingHistory

# Your FastAPI server's base URL — change this if you ever run it on a
# different host/port.
FASTAPI_BASE_URL = "http://127.0.0.1:8000"


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "email", "plan_id", "created_at")
    search_fields = ("username", "email")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "author_id", "created_at")
    search_fields = ("title",)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "price", "max_posts",
        "max_images_per_post", "max_likes", "max_comments", "is_unlimited",
    )


@admin.register(BillingHistory)
class BillingHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user_id", "plan_id", "price",
        "transaction_id", "start_date", "end_date", "invoice_link",
    )
    search_fields = ("transaction_id",)

    def invoice_link(self, obj):
        if not obj.invoice_path:
            return "—"
        url = f"{FASTAPI_BASE_URL}{obj.invoice_path}"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">📄 Download Invoice</a>',
            url,
        )

    invoice_link.short_description = "Invoice"