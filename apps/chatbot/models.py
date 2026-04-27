"""Chatbot models: DatasetChatbot, RiwayatChat (Skripsi Tabel 3.19-3.20),
serta ekstensi RAG: DokumenPengetahuan & ChunkPengetahuan (Tabel 3.22-3.23).
"""
from django.conf import settings
from django.db import models
from pgvector.django import VectorField

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
    instruksi_ai = models.TextField(blank=True, default='')
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


# ─── RAG (Retrieval-Augmented Generation) ─────────────────────────────────
# Skripsi Tabel 3.22-3.23. Memungkinkan admin upload PDF (AD/ART, sejarah,
# dll) dan menjadikannya sumber pengetahuan chatbot tanpa perlu mengetik
# manual ke DatasetChatbot. Pencarian pakai embedding vektor (pgvector).


class StatusDokumen(models.TextChoices):
    """Status pemrosesan dokumen pengetahuan."""
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Sedang Diproses'
    READY = 'ready', 'Siap Digunakan'
    FAILED = 'failed', 'Gagal'


class DokumenPengetahuan(models.Model):
    """Dokumen sumber pengetahuan chatbot (PDF) — Skripsi Tabel 3.22."""

    id_dokumen = models.AutoField(primary_key=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='created_by',
        related_name='dokumen_pengetahuan_list',
    )
    judul = models.CharField(max_length=200)
    file_pdf = models.FileField(upload_to='dokumen_pengetahuan/', max_length=255)
    jenis_chatbot = models.CharField(max_length=15, choices=JenisChatbot.choices)
    jumlah_chunk = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=StatusDokumen.choices,
        default=StatusDokumen.PENDING,
    )
    error_message = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dokumen_pengetahuan'
        verbose_name = 'Dokumen Pengetahuan'
        verbose_name_plural = 'Dokumen Pengetahuan'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"[{self.get_jenis_chatbot_display()}] {self.judul}"


class ChunkPengetahuan(models.Model):
    """Potongan teks PDF + embedding vektor — Skripsi Tabel 3.23.

    Satu dokumen di-chunk per BAB/Pasal/seksi (atau per blok ~500 token).
    Embedding 1536 dimensi sesuai model OpenAI ``text-embedding-3-small``.
    """

    id_chunk = models.AutoField(primary_key=True)
    id_dokumen = models.ForeignKey(
        DokumenPengetahuan,
        on_delete=models.CASCADE,
        db_column='id_dokumen',
        related_name='chunk_list',
    )
    urutan = models.IntegerField()
    teks = models.TextField()
    metadata_seksi = models.CharField(max_length=200, blank=True, default='')
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chunk_pengetahuan'
        verbose_name = 'Chunk Pengetahuan'
        verbose_name_plural = 'Chunk Pengetahuan'
        ordering = ['id_dokumen', 'urutan']

    def __str__(self) -> str:
        return f"Chunk {self.urutan} — {self.metadata_seksi or 'no section'}"
