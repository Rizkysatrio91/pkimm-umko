"""Abstract base model untuk proyek ini."""
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base model dengan created_at dan updated_at."""

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
