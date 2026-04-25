"""Chatbot models: DatasetChatbot, RiwayatChat (Skripsi Tabel 3.8-3.9)."""
from django.conf import settings
from django.db import models

from core.constants import JenisChatbot, KategoriDataset


class ActiveManager(models.Manager):
    """Manager yang hanya mengembalikan dataset yang aktif."""

    def get_queryset(self) -> models.QuerySet:
        """Filter hanya dataset yang aktif."""
        return super().get_queryset().filter(is_active=True)


class DatasetChatbot(models.Model):
    """Dataset knowledge base untuk chatbot AI (Skripsi Tabel 3.8)."""

    id_dataset = models.AutoField(primary_key=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='created_by',
        related_name='dataset_chatbot_list',
    )
    intent_keyword = models.CharField(max_length=100)
    respon_jawaban = models.TextField()
    instruksi_ai = models.TextField()
    kategori = models.CharField(max_length=20, choices=KategoriDataset.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    jenis_chatbot = models.CharField(max_length=15, choices=JenisChatbot.choices)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        db_table = 'dataset_chatbot'
        verbose_name = 'Dataset Chatbot'
        verbose_name_plural = 'Dataset Chatbot'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"[{self.get_jenis_chatbot_display()}] {self.intent_keyword}"


class RiwayatChat(models.Model):
    """Riwayat percakapan chatbot (Skripsi Tabel 3.9)."""

    id_chat = models.AutoField(primary_key=True)
    id_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_user',
        related_name='riwayat_chat_list',
    )
    id_dataset = models.ForeignKey(
        DatasetChatbot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_dataset',
        related_name='riwayat_chat_list',
    )
    sesi_id = models.CharField(max_length=50)
    pesan_user = models.TextField()
    respon_bot = models.TextField()
    is_found = models.BooleanField()
    waktu_chat = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'riwayat_chat'
        verbose_name = 'Riwayat Chat'
        verbose_name_plural = 'Riwayat Chat'
        ordering = ['-waktu_chat']

    def __str__(self) -> str:
        return f"Chat {self.sesi_id} - {self.waktu_chat}"
