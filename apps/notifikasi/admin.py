"""Registrasi admin untuk app notifikasi."""
from django.contrib import admin

from apps.notifikasi.models import Notifikasi


@admin.register(Notifikasi)
class NotifikasiAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk Notifikasi."""
    list_display = ('judul', 'id_user', 'tipe', 'is_read', 'created_at')
    list_filter = ('tipe', 'is_read')
    search_fields = ('judul', 'pesan')
    ordering = ('-created_at',)
