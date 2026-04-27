"""Registrasi admin untuk app chatbot."""
from django.contrib import admin

from apps.chatbot.models import (
    ChunkPengetahuan,
    DatasetChatbot,
    DokumenPengetahuan,
    RiwayatChat,
)


@admin.register(DatasetChatbot)
class DatasetChatbotAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk DatasetChatbot."""
    list_display = ('intent_keyword', 'jenis_chatbot', 'kategori', 'is_active', 'created_at')
    list_filter = ('jenis_chatbot', 'kategori', 'is_active')
    search_fields = ('intent_keyword', 'respon_jawaban')
    ordering = ('-created_at',)


@admin.register(RiwayatChat)
class RiwayatChatAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk RiwayatChat."""
    list_display = ('sesi_id', 'id_user', 'is_found', 'waktu_chat')
    list_filter = ('is_found',)
    search_fields = ('sesi_id', 'pesan_user')
    ordering = ('-waktu_chat',)


@admin.register(DokumenPengetahuan)
class DokumenPengetahuanAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk DokumenPengetahuan."""
    list_display = ('judul', 'jenis_chatbot', 'status', 'jumlah_chunk', 'is_active', 'created_at')
    list_filter = ('jenis_chatbot', 'status', 'is_active')
    search_fields = ('judul',)
    readonly_fields = ('jumlah_chunk', 'status', 'error_message', 'created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(ChunkPengetahuan)
class ChunkPengetahuanAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk ChunkPengetahuan (read-only via admin)."""
    list_display = ('id_dokumen', 'urutan', 'metadata_seksi')
    list_filter = ('id_dokumen',)
    search_fields = ('teks', 'metadata_seksi')
    readonly_fields = ('id_dokumen', 'urutan', 'teks', 'metadata_seksi', 'created_at')
