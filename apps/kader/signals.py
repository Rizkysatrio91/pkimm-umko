"""Signals untuk app kader."""
import os

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from apps.kader.models import BiodataKader


@receiver(pre_delete, sender=BiodataKader)
def delete_foto_profil(sender, instance, **kwargs) -> None:
    """Hapus file foto profil dari disk saat BiodataKader dihapus."""
    if instance.foto_profil:
        try:
            if os.path.isfile(instance.foto_profil.path):
                os.remove(instance.foto_profil.path)
        except Exception:
            pass


@receiver(post_save, sender=BiodataKader)
def auto_check_completeness(sender, instance: BiodataKader, **kwargs) -> None:
    """Jalankan otomatis check_completeness setelah setiap save."""
    if not kwargs.get('update_fields') or 'is_biodata_complete' not in kwargs.get('update_fields', []):
        instance.check_completeness()
