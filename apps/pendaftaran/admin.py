"""Registrasi admin untuk app pendaftaran."""
from django.contrib import admin

from apps.pendaftaran.models import PendaftaranDAD, PeriodeDAD


@admin.register(PendaftaranDAD)
class PendaftaranDADAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk PendaftaranDAD."""
    list_display = ('no_registrasi', 'get_nama', 'get_npm', 'status_verifikasi', 'status_kelulusan', 'is_identic', 'tgl_daftar')
    list_filter = ('status_verifikasi', 'status_kelulusan', 'is_identic')
    search_fields = ('no_registrasi', 'id_biodata__nama_lengkap', 'id_biodata__npm')
    ordering = ('-tgl_daftar',)

    @admin.display(description='Nama')
    def get_nama(self, obj: PendaftaranDAD) -> str:
        return obj.id_biodata.nama_lengkap

    @admin.display(description='NPM')
    def get_npm(self, obj: PendaftaranDAD) -> str:
        return obj.id_biodata.npm


@admin.register(PeriodeDAD)
class PeriodeDADAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk PeriodeDAD."""
    list_display = ('nama_periode', 'tgl_buka_administrasi', 'tgl_tutup_administrasi', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('nama_periode',)
