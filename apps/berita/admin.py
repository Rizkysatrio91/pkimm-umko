"""Registrasi admin untuk app berita."""
from django.contrib import admin

from apps.berita.models import Berita, KataSambutan, Sejarah, VisiMisi


@admin.register(Berita)
class BeritaAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk Berita."""
    list_display = ('judul', 'id_penulis', 'kategori', 'status', 'jumlah_views', 'tgl_dibuat', 'tgl_terbit')
    list_filter = ('kategori', 'status')
    search_fields = ('judul', 'konten_draft')
    prepopulated_fields = {'slug': ('judul',)}
    ordering = ('-tgl_dibuat',)


@admin.register(KataSambutan)
class KataSambutanAdmin(admin.ModelAdmin):
    list_display = ('nama', 'jabatan', 'is_active', 'updated_at')
    list_filter = ('is_active',)


@admin.register(VisiMisi)
class VisiMisiAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_active', 'updated_at')
    list_filter = ('is_active',)


@admin.register(Sejarah)
class SejarahAdmin(admin.ModelAdmin):
    list_display = ('judul', 'is_active', 'updated_at')
    list_filter = ('is_active',)
