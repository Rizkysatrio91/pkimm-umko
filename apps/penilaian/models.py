"""Penilaian models: NilaiInterview, NilaiAktivitas, RekapLeaderboard (Skripsi Tabel 3.4-3.6)."""
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.pendaftaran.models import PendaftaranDAD
from core.constants import StatusInterview


class NilaiInterview(models.Model):
    """Nilai interview 5 kategori × 3 sub-item (total 15 sub-skor, hasil 0-100).

    Struktur baru menggantikan 4 aspek lama (aik/wawasan/komitmen/komunikasi).
    Setiap sub-skor 0-100. Nilai kategori = rata-rata 3 sub-skor-nya.
    Nilai interview final (``rata_rata``) = rata-rata 5 nilai kategori = rata-rata 15 sub-skor.
    """

    SUB_FIELDS = (
        # Kategori 1: Al-Qur'an
        'qur_makhraj_tajwid', 'qur_tulis_surat', 'qur_kandungan_surat',
        # Kategori 2: Hafalan
        'hafalan_5_pendek', 'hafalan_2_pengkaderan', 'hafalan_1_favorit',
        # Kategori 3: Ideologi
        'ideologi_umum', 'ideologi_muhammadiyah', 'ideologi_imm',
        # Kategori 4: Dialektika
        'dialektika_tujuan', 'dialektika_minat', 'dialektika_bakat',
        # Kategori 5: Kesiapan
        'kesiapan_ikut_penuh', 'kesiapan_persiapan', 'kesiapan_konsekuensi',
    )

    id_interview = models.AutoField(primary_key=True)
    id_pendaftaran = models.ForeignKey(
        PendaftaranDAD,
        on_delete=models.CASCADE,
        db_column='id_pendaftaran',
        related_name='nilai_interview_set',
    )
    id_panitia = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='id_panitia',
        related_name='interview_dinilai',
    )

    # Kategori 1 — Al-Qur'an
    qur_makhraj_tajwid = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    qur_tulis_surat = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    qur_kandungan_surat = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))

    # Kategori 2 — Hafalan Ayat
    hafalan_5_pendek = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    hafalan_2_pengkaderan = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    hafalan_1_favorit = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))

    # Kategori 3 — Ideologi
    ideologi_umum = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    ideologi_muhammadiyah = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    ideologi_imm = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))

    # Kategori 4 — Dialektika
    dialektika_tujuan = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    dialektika_minat = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    dialektika_bakat = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))

    # Kategori 5 — Kesiapan
    kesiapan_ikut_penuh = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    kesiapan_persiapan = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    kesiapan_konsekuensi = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))

    rata_rata = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    status_interview = models.CharField(
        max_length=20,
        choices=StatusInterview.choices,
        blank=True,
    )
    catatan = models.TextField(null=True, blank=True)
    tgl_penilaian = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'nilai_interview'
        verbose_name = 'Nilai Interview'
        verbose_name_plural = 'Nilai Interview'
        ordering = ['-tgl_penilaian']

    def __str__(self) -> str:
        return f"Interview {self.id_pendaftaran} - Rata-rata: {self.rata_rata}"

    # ─── Nilai per kategori (rata-rata 3 sub-skor) ──────────────────────────
    @property
    def nilai_quran(self) -> Decimal:
        return (self.qur_makhraj_tajwid + self.qur_tulis_surat + self.qur_kandungan_surat) / Decimal('3')

    @property
    def nilai_hafalan(self) -> Decimal:
        return (self.hafalan_5_pendek + self.hafalan_2_pengkaderan + self.hafalan_1_favorit) / Decimal('3')

    @property
    def nilai_ideologi(self) -> Decimal:
        return (self.ideologi_umum + self.ideologi_muhammadiyah + self.ideologi_imm) / Decimal('3')

    @property
    def nilai_dialektika(self) -> Decimal:
        return (self.dialektika_tujuan + self.dialektika_minat + self.dialektika_bakat) / Decimal('3')

    @property
    def nilai_kesiapan(self) -> Decimal:
        return (self.kesiapan_ikut_penuh + self.kesiapan_persiapan + self.kesiapan_konsekuensi) / Decimal('3')

    def hitung_rata_rata(self) -> None:
        """Hitung nilai interview final (0-100) dan tentukan status.

        Final = rata-rata 15 sub-skor = rata-rata 5 nilai kategori.
        """
        total = sum((getattr(self, f) for f in self.SUB_FIELDS), Decimal('0'))
        self.rata_rata = (total / Decimal(len(self.SUB_FIELDS))).quantize(Decimal('0.01'))
        self.status_interview = (
            StatusInterview.LULUS if self.rata_rata >= Decimal('60.00')
            else StatusInterview.GAGAL
        )

    def save(self, *args, **kwargs) -> None:
        """Hitung otomatis rata_rata sebelum disimpan."""
        self.hitung_rata_rata()
        super().save(*args, **kwargs)


class NilaiAktivitas(models.Model):
    """Poin kegiatan DAD harian (Skripsi Tabel 3.5)."""

    id_aktivitas = models.AutoField(primary_key=True)
    id_pendaftaran = models.ForeignKey(
        PendaftaranDAD,
        on_delete=models.CASCADE,
        db_column='id_pendaftaran',
        related_name='nilai_aktivitas_set',
    )
    id_panitia = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='id_panitia',
        related_name='aktivitas_dinilai',
    )
    hari_ke = models.SmallIntegerField()
    poin_keaktifan = models.DecimalField(max_digits=5, decimal_places=2)
    poin_kedisiplinan = models.DecimalField(max_digits=5, decimal_places=2)
    poin_kontribusi = models.DecimalField(max_digits=5, decimal_places=2)
    skor_harian = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    catatan = models.TextField(null=True, blank=True)
    tgl_penilaian = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'nilai_aktivitas'
        verbose_name = 'Nilai Aktivitas'
        verbose_name_plural = 'Nilai Aktivitas'
        unique_together = [('id_pendaftaran', 'hari_ke')]
        ordering = ['id_pendaftaran', 'hari_ke']

    def __str__(self) -> str:
        return f"Aktivitas {self.id_pendaftaran} Hari-{self.hari_ke}: {self.skor_harian}"

    def hitung_skor_harian(self) -> None:
        """Hitung skor harian sebagai rata-rata dari 3 poin."""
        total = self.poin_keaktifan + self.poin_kedisiplinan + self.poin_kontribusi
        self.skor_harian = total / Decimal('3')

    def save(self, *args, **kwargs) -> None:
        """Hitung otomatis skor_harian sebelum disimpan."""
        self.hitung_skor_harian()
        super().save(*args, **kwargs)


class RekapLeaderboard(models.Model):
    """Leaderboard ranking peserta DAD (Skripsi Tabel 3.6)."""

    id_rekap = models.AutoField(primary_key=True)
    id_pendaftaran = models.OneToOneField(
        PendaftaranDAD,
        on_delete=models.CASCADE,
        db_column='id_pendaftaran',
        related_name='rekap_leaderboard',
    )
    total_skor_aktivitas = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    nilai_interview = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    total_akhir = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    peringkat = models.SmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rekap_leaderboard'
        verbose_name = 'Rekap Leaderboard'
        verbose_name_plural = 'Rekap Leaderboard'
        ordering = ['peringkat']

    def __str__(self) -> str:
        return f"Peringkat {self.peringkat} - {self.id_pendaftaran}"

    def hitung_total_akhir(self) -> None:
        """Hitung total_akhir = (total_skor_aktivitas + nilai_interview) / 2."""
        self.total_akhir = (self.total_skor_aktivitas + self.nilai_interview) / Decimal('2')

    @classmethod
    def perbarui_semua_peringkat(cls) -> None:
        """Urutkan ulang semua entri berdasarkan total_akhir secara menurun."""
        semua_rekap = cls.objects.order_by('-total_akhir')
        for idx, rekap in enumerate(semua_rekap, start=1):
            if rekap.peringkat != idx:
                rekap.peringkat = idx
                rekap.save(update_fields=['peringkat'])
