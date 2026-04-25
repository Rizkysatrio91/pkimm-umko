"""Registrasi admin untuk app chatbot."""
from django.contrib import admin

from apps.chatbot.models import DatasetChatbot, RiwayatChat


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
