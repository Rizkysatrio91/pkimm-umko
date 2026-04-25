"""Konfigurasi app pendaftaran."""
from django.apps import AppConfig


class PendaftaranConfig(AppConfig):
    """Konfigurasi untuk app pendaftaran."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.pendaftaran'
    verbose_name = 'Pendaftaran DAD'

    def ready(self) -> None:
        """Daftarkan signals."""
        import apps.pendaftaran.signals  # noqa: F401
