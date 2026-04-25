"""Konfigurasi app penilaian."""
from django.apps import AppConfig


class PenilaianConfig(AppConfig):
    """Konfigurasi untuk app penilaian."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.penilaian'
    verbose_name = 'Penilaian DAD'

    def ready(self) -> None:
        """Daftarkan signals."""
        import apps.penilaian.signals  # noqa: F401
