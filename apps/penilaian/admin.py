"""Registrasi admin untuk app penilaian."""
from django.contrib import admin

from apps.penilaian.models import NilaiAktivitas, NilaiInterview, RekapLeaderboard


class NilaiInterviewInline(admin.TabularInline):
    """Inline untuk NilaiInterview di dalam PendaftaranDAD."""
    model = NilaiInterview
    extra = 0
    readonly_fields = ('rata_rata', 'status_interview')


class NilaiAktivitasInline(admin.TabularInline):
    """Inline untuk NilaiAktivitas di dalam PendaftaranDAD."""
    model = NilaiAktivitas
    extra = 0
    readonly_fields = ('skor_harian',)


@admin.register(NilaiInterview)
class NilaiInterviewAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk NilaiInterview (5 kategori × 3 sub-item)."""
    list_display = ('id_pendaftaran', 'id_panitia', 'rata_rata', 'status_interview', 'tgl_penilaian')
    list_filter = ('status_interview',)
    search_fields = ('id_pendaftaran__id_biodata__nama_lengkap',)
    readonly_fields = ('rata_rata', 'status_interview', 'tgl_penilaian')
    fieldsets = (
        (None, {'fields': ('id_pendaftaran', 'id_panitia', 'catatan')}),
        ("Al-Qur'an", {'fields': ('qur_makhraj_tajwid', 'qur_tulis_surat', 'qur_kandungan_surat')}),
        ('Hafalan Ayat', {'fields': ('hafalan_5_pendek', 'hafalan_2_pengkaderan', 'hafalan_1_favorit')}),
        ('Ideologi', {'fields': ('ideologi_umum', 'ideologi_muhammadiyah', 'ideologi_imm')}),
        ('Dialektika', {'fields': ('dialektika_tujuan', 'dialektika_minat', 'dialektika_bakat')}),
        ('Kesiapan', {'fields': ('kesiapan_ikut_penuh', 'kesiapan_persiapan', 'kesiapan_konsekuensi')}),
        ('Hasil', {'fields': ('rata_rata', 'status_interview', 'tgl_penilaian')}),
    )


@admin.register(NilaiAktivitas)
class NilaiAktivitasAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk NilaiAktivitas."""
    list_display = ('id_pendaftaran', 'hari_ke', 'poin_keaktifan', 'poin_kedisiplinan', 'poin_kontribusi', 'skor_harian')
    list_filter = ('hari_ke',)
    search_fields = ('id_pendaftaran__id_biodata__nama_lengkap',)
    readonly_fields = ('skor_harian',)


@admin.register(RekapLeaderboard)
class RekapLeaderboardAdmin(admin.ModelAdmin):
    """Konfigurasi admin untuk RekapLeaderboard."""
    list_display = ('peringkat', 'id_pendaftaran', 'total_skor_aktivitas', 'nilai_interview', 'total_akhir')
    ordering = ('peringkat',)
    readonly_fields = ('total_akhir', 'peringkat')
