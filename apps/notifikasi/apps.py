"""Konfigurasi app notifikasi."""
from django.apps import AppConfig


class NotifikasiConfig(AppConfig):
    """Konfigurasi untuk app notifikasi."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notifikasi'
    verbose_name = 'Notifikasi'
