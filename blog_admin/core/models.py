from django.db import models


class User(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    email = models.CharField(max_length=120, unique=True)
    hashed_password = models.CharField(max_length=255)
    created_at = models.DateTimeField(blank=True, null=True)
    plan_id = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "users"

    def __str__(self):
        return self.username


class SubscriptionPlan(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    price = models.FloatField()
    max_posts = models.IntegerField()
    max_images_per_post = models.IntegerField()
    max_likes = models.IntegerField()
    max_comments = models.IntegerField()
    is_unlimited = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = "subscription_plans"

    def __str__(self):
        return self.name


class Post(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200)
    content = models.TextField()
    author_id = models.IntegerField()
    created_at = models.DateTimeField(blank=True, null=True)
    image = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "posts"

    def __str__(self):
        return self.title


class BillingHistory(models.Model):
    id = models.AutoField(primary_key=True)
    user_id = models.IntegerField()
    plan_id = models.IntegerField()
    price = models.FloatField()
    transaction_id = models.CharField(max_length=64, unique=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    invoice_path = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "billing_history"

    def __str__(self):
        return self.transaction_id