"""Konfigurasi app berita."""
from django.apps import AppConfig


class BeritaConfig(AppConfig):
    """Konfigurasi untuk app berita."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.berita'
    verbose_name = 'Berita'
