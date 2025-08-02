from uuid import uuid4

from django.db import models

# Create your models here.

class BaseAbstractModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Polls(BaseAbstractModel):
    POLL_TYPES = (
        ('single','Single Choice'),
        ('multiple','Multiple Choice'),
    )

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('expired', 'Expired'),
        ('archived', 'Archived'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    title = models.CharField(max_length=512)
    description = models.TextField(blank=True, null=True)
    poll_type = models.CharField(max_length=10, choices=POLL_TYPES, default='single')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
