"""Konfigurasi app kader."""
from django.apps import AppConfig


class KaderConfig(AppConfig):
    """Konfigurasi untuk app kader."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.kader'
    verbose_name = 'Data Kader'

    def ready(self) -> None:
        """Daftarkan signals."""
        import apps.kader.signals  # noqa: F401
