"""Konfigurasi app accounts."""
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Konfigurasi untuk app accounts."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = 'Akun & Autentikasi'
