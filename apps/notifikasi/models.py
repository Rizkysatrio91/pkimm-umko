"""Notifikasi model (Skripsi Tabel 3.10)."""
from django.conf import settings
from django.db import models

from core.constants import TipeNotifikasi


class UnreadManager(models.Manager):
    """Manager yang hanya mengembalikan notifikasi yang belum dibaca."""

    def get_queryset(self) -> models.QuerySet:
        """Filter hanya notifikasi yang belum dibaca."""
        return super().get_queryset().filter(is_read=False)


class Notifikasi(models.Model):
    """Notifikasi otomatis untuk user (Skripsi Tabel 3.10)."""

    id_notif = models.AutoField(primary_key=True)
    id_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='id_user',
        related_name='notifikasi_list',
    )
    judul = models.CharField(max_length=100)
    pesan = models.TextField()
    tipe = models.CharField(max_length=20, choices=TipeNotifikasi.choices)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    unread = UnreadManager()

    class Meta:
        db_table = 'notifikasi'
        verbose_name = 'Notifikasi'
        verbose_name_plural = 'Notifikasi'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"[{self.get_tipe_display()}] {self.judul}"

    def tandai_dibaca(self) -> None:
        """Tandai notifikasi sebagai sudah dibaca."""
        self.is_read = True
        self.save(update_fields=['is_read'])
