"""Registrasi admin untuk app kader."""
from django.contrib import admin

from apps.kader.models import BiodataKader, Fakultas, ProgramStudi


class ProgramStudiInline(admin.TabularInline):
    model = ProgramStudi
    extra = 1


@admin.register(Fakultas)
class FakultasAdmin(admin.ModelAdmin):
    list_display = ['nama_fakultas', 'kode_fakultas', 'is_active']
    inlines = [ProgramStudiInline]


@admin.register(ProgramStudi)
class ProgramStudiAdmin(admin.ModelAdmin):
    list_display = ['nama_prodi', 'kode_prodi', 'fakultas', 'is_active']
    list_filter = ['fakultas', 'is_active']


@admin.register(BiodataKader)
class BiodataKaderAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk BiodataKader."""
    list_display = ('npm', 'nama_lengkap', 'program_studi', 'fakultas', 'angkatan', 'jabatan_struktural', 'is_biodata_complete')
    list_filter = ('fakultas', 'angkatan', 'jabatan_struktural', 'is_biodata_complete')
    search_fields = ('npm', 'nama_lengkap')
    ordering = ('nama_lengkap',)
