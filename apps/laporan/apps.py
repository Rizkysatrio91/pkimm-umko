"""Konfigurasi app laporan."""
from django.apps import AppConfig


class LaporanConfig(AppConfig):
    """Konfigurasi untuk app laporan."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.laporan'
    verbose_name = 'Laporan'
