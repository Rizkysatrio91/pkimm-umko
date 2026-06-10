"""Unit test untuk apps.penilaian.services.

Cakupan:
  - AktivitasService.hitung_poin_kedisiplinan: matriks lengkap skenario
    (semua hadir, izin, sakit, alpha, campuran, no row, QR belum ada,
    no sesi absensi, no periode/kelompok, filter hari, filter is_absensi).
  - AktivitasService.sinkron_poin_kedisiplinan_untuk_sesi: re-hitung
    NilaiAktivitas yang sudah ada, no-op jika belum ada.
  - KelulusanService.tetapkan_kelulusan: lulus/tidak lulus, promote kader,
    notifikasi, boundary passing grade, biodata tanpa user.

Dasar aturan bisnis: project_qr_absensi_scoring di MEMORY.md
  hadir=100, izin/sakit=60, alpha (atau no row) = 0.
"""
from decimal import Decimal

from django.test import TestCase

from apps.kader.models import BiodataKader
from apps.notifikasi.models import Notifikasi
from apps.pendaftaran.models import PendaftaranDAD
from apps.penilaian.models import NilaiAktivitas, RekapLeaderboard
from apps.penilaian.services import AktivitasService, KelulusanService
from apps.penilaian.tests import factories as F
from core.constants import (
    JabatanKader,
    NamaKelompok,
    StatusAbsensi,
    StatusKelulusan,
    TipeNotifikasi,
    UserRole,
)


class HitungPoinKedisiplinanTests(TestCase):
    """Test formula AktivitasService.hitung_poin_kedisiplinan.

    Setup default: 1 periode aktif, 1 kelompok A, 1 peserta,
    3 sesi is_absensi di Hari 1 dengan QR sudah dibuat untuk kelompok A.
    Test memodifikasi state default sesuai skenario.
    """

    def setUp(self) -> None:
        self.periode = F.make_periode()
        self.kelompok = F.make_kelompok(self.periode, NamaKelompok.A)
        self.pendaftaran = F.make_pendaftaran(
            periode=self.periode, kelompok=self.kelompok,
        )
        self.sesi_1 = F.make_rundown(self.periode, urutan=1)
        self.sesi_2 = F.make_rundown(self.periode, urutan=2)
        self.sesi_3 = F.make_rundown(self.periode, urutan=3)
        self.qr_1 = F.make_qr(self.sesi_1, self.kelompok)
        self.qr_2 = F.make_qr(self.sesi_2, self.kelompok)
        self.qr_3 = F.make_qr(self.sesi_3, self.kelompok)

    def _hitung(self) -> Decimal:
        return AktivitasService.hitung_poin_kedisiplinan(self.pendaftaran, hari_ke=1)

    # ─── Edge case: data tidak lengkap ───────────────────────────────────────

    def test_no_periode_returns_zero(self):
        self.pendaftaran.id_periode = None
        self.pendaftaran.save()
        self.assertEqual(self._hitung(), Decimal('0.00'))

    def test_no_kelompok_returns_zero(self):
        self.pendaftaran.id_kelompok = None
        self.pendaftaran.save()
        self.assertEqual(self._hitung(), Decimal('0.00'))

    def test_no_sesi_absensi_di_hari_returns_zero(self):
        # Hapus semua sesi → tidak ada sesi is_absensi di Hari 1
        self.sesi_1.delete()
        self.sesi_2.delete()
        self.sesi_3.delete()
        self.assertEqual(self._hitung(), Decimal('0.00'))

    def test_sesi_is_absensi_false_diabaikan(self):
        # Ubah sesi 2 dan 3 jadi non-absensi → hanya sesi 1 yang dihitung
        self.sesi_2.is_absensi = False
        self.sesi_2.save()
        self.sesi_3.is_absensi = False
        self.sesi_3.save()
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.HADIR)
        # 1 sesi × HADIR → 100/1 = 100
        self.assertEqual(self._hitung(), Decimal('100.00'))

    def test_filter_hari_only_target_day(self):
        # Tambah sesi di Hari 2 dengan ALPHA → hari_ke=1 tidak boleh terdampak
        sesi_h2 = F.make_rundown(self.periode, hari_ke='Hari 2', urutan=10)
        qr_h2 = F.make_qr(sesi_h2, self.kelompok)
        # Hari 1: semua hadir
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_2, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.HADIR)
        # Hari 2: alpha (no row), tidak boleh ngurangi nilai Hari 1
        _ = qr_h2  # tidak ada AbsensiDAD untuk hari 2
        self.assertEqual(self._hitung(), Decimal('100.00'))

    def test_hari_label_case_insensitive(self):
        # Standar di codebase: "Hari 1" (kapital H). Verifikasi case-insensitive
        # match seperti yang dijanjikan service via hari_ke__iexact.
        self.sesi_1.hari_ke = 'hari 1'
        self.sesi_1.save()
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_2, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.HADIR)
        self.assertEqual(self._hitung(), Decimal('100.00'))

    # ─── Skor per status ─────────────────────────────────────────────────────

    def test_semua_hadir_returns_100(self):
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_2, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.HADIR)
        self.assertEqual(self._hitung(), Decimal('100.00'))

    def test_semua_izin_returns_60(self):
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.IZIN)
        F.make_absensi(self.pendaftaran, self.qr_2, StatusAbsensi.IZIN)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.IZIN)
        self.assertEqual(self._hitung(), Decimal('60.00'))

    def test_semua_sakit_returns_60(self):
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.SAKIT)
        F.make_absensi(self.pendaftaran, self.qr_2, StatusAbsensi.SAKIT)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.SAKIT)
        self.assertEqual(self._hitung(), Decimal('60.00'))

    def test_semua_alpha_explicit_returns_0(self):
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.ALPHA)
        F.make_absensi(self.pendaftaran, self.qr_2, StatusAbsensi.ALPHA)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.ALPHA)
        self.assertEqual(self._hitung(), Decimal('0.00'))

    def test_no_absensi_row_dianggap_alpha_returns_0(self):
        # Sesi & QR ada, tapi peserta tidak punya row AbsensiDAD sama sekali
        self.assertEqual(self._hitung(), Decimal('0.00'))

    def test_qr_belum_dibuat_untuk_kelompok_dianggap_alpha(self):
        # Hapus QR sesi_2 → service harus anggap sesi_2 sebagai ALPHA (0)
        self.qr_2.delete()
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.HADIR)
        # (100 + 0 + 100) / 3 = 66.666... → 66.67
        self.assertEqual(self._hitung(), Decimal('66.67'))

    # ─── Campuran status ─────────────────────────────────────────────────────

    def test_campuran_2hadir_1izin_returns_avg(self):
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_2, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.IZIN)
        # (100 + 100 + 60) / 3 = 86.666... → 86.67
        self.assertEqual(self._hitung(), Decimal('86.67'))

    def test_campuran_1hadir_1izin_1alpha(self):
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_2, StatusAbsensi.IZIN)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.ALPHA)
        # (100 + 60 + 0) / 3 = 53.333... → 53.33
        self.assertEqual(self._hitung(), Decimal('53.33'))

    def test_hasil_quantize_2_desimal(self):
        # Pastikan output selalu dibatasi 2 digit desimal (penting untuk DB
        # max_digits=5, decimal_places=2).
        F.make_absensi(self.pendaftaran, self.qr_1, StatusAbsensi.HADIR)
        F.make_absensi(self.pendaftaran, self.qr_2, StatusAbsensi.IZIN)
        F.make_absensi(self.pendaftaran, self.qr_3, StatusAbsensi.IZIN)
        result = self._hitung()
        # (100 + 60 + 60) / 3 = 73.333... → 73.33
        self.assertEqual(result, Decimal('73.33'))
        self.assertEqual(result.as_tuple().exponent, -2)


class SinkronPoinKedisiplinanTests(TestCase):
    """Test AktivitasService.sinkron_poin_kedisiplinan_untuk_sesi."""

    def setUp(self) -> None:
        self.panitia = F.make_user(role=UserRole.PANITIA)
        self.periode = F.make_periode()
        self.kelompok = F.make_kelompok(self.periode)
        self.pendaftaran = F.make_pendaftaran(
            periode=self.periode, kelompok=self.kelompok,
        )
        self.rundown = F.make_rundown(self.periode, hari_ke='Hari 2')
        self.qr = F.make_qr(self.rundown, self.kelompok)

    def test_noop_jika_nilai_aktivitas_belum_ada(self):
        # Tidak ada NilaiAktivitas untuk hari_ke=2 → fungsi tidak boleh crash
        # dan tidak boleh bikin row baru.
        AktivitasService.sinkron_poin_kedisiplinan_untuk_sesi(
            self.rundown, self.pendaftaran,
        )
        self.assertEqual(
            NilaiAktivitas.objects.filter(id_pendaftaran=self.pendaftaran).count(),
            0,
        )

    def test_sinkron_recalculates_existing(self):
        # Buat NilaiAktivitas dengan poin lama (stale)
        nilai = NilaiAktivitas.objects.create(
            id_pendaftaran=self.pendaftaran,
            id_panitia=self.panitia,
            hari_ke=2,
            poin_keaktifan=Decimal('80.00'),
            poin_kedisiplinan=Decimal('0.00'),  # stale
            poin_kontribusi=Decimal('80.00'),
        )
        # Lalu peserta scan HADIR → seharusnya poin_kedisiplinan jadi 100
        F.make_absensi(self.pendaftaran, self.qr, StatusAbsensi.HADIR)

        AktivitasService.sinkron_poin_kedisiplinan_untuk_sesi(
            self.rundown, self.pendaftaran,
        )

        nilai.refresh_from_db()
        self.assertEqual(nilai.poin_kedisiplinan, Decimal('100.00'))
        # skor_harian otomatis re-hitung pada save():
        # (80 + 100 + 80) / 3 = 86.666... → DecimalField max 2 desimal
        self.assertEqual(nilai.skor_harian.quantize(Decimal('0.01')), Decimal('86.67'))

    def test_label_hari_tidak_standar_di_skip(self):
        # Rundown.hari_ke = 'Kedatangan' bukan format "Hari N" → sinkron no-op
        rundown_aneh = F.make_rundown(self.periode, hari_ke='Kedatangan')
        # Walau ada NilaiAktivitas di hari 1, fungsi return tanpa menyentuhnya
        nilai = NilaiAktivitas.objects.create(
            id_pendaftaran=self.pendaftaran,
            id_panitia=self.panitia,
            hari_ke=1,
            poin_keaktifan=Decimal('70.00'),
            poin_kedisiplinan=Decimal('70.00'),
            poin_kontribusi=Decimal('70.00'),
        )
        sebelum = nilai.poin_kedisiplinan

        AktivitasService.sinkron_poin_kedisiplinan_untuk_sesi(
            rundown_aneh, self.pendaftaran,
        )

        nilai.refresh_from_db()
        self.assertEqual(nilai.poin_kedisiplinan, sebelum)


class TetapkanKelulusanTests(TestCase):
    """Test KelulusanService.tetapkan_kelulusan.

    Build state dengan membuat RekapLeaderboard langsung (tanpa lewat signal
    NilaiInterview/Aktivitas) supaya skenario nilai total_akhir terkontrol.
    """

    def setUp(self) -> None:
        self.periode = F.make_periode()
        self.kelompok = F.make_kelompok(self.periode)

    def _make_peserta_with_rekap(
        self,
        total_akhir: Decimal,
        with_user: bool = True,
    ) -> tuple[PendaftaranDAD, BiodataKader]:
        user = F.make_user(role=UserRole.CALON_KADER) if with_user else None
        biodata = F.make_biodata(user=user)
        pendaftaran = F.make_pendaftaran(
            biodata=biodata, periode=self.periode, kelompok=self.kelompok,
        )
        RekapLeaderboard.objects.create(
            id_pendaftaran=pendaftaran,
            total_skor_aktivitas=Decimal('0.00'),
            nilai_interview=Decimal('0.00'),
            total_akhir=total_akhir,
            peringkat=1,
        )
        return pendaftaran, biodata

    def test_lulus_set_status_promote_kader_kirim_notifikasi(self):
        pendaftaran, biodata = self._make_peserta_with_rekap(Decimal('85.00'))

        hasil = KelulusanService.tetapkan_kelulusan(Decimal('75.00'))

        self.assertEqual(hasil, {'lulus': 1, 'tidak_lulus': 0})
        pendaftaran.refresh_from_db()
        biodata.refresh_from_db()
        self.assertEqual(pendaftaran.status_kelulusan, StatusKelulusan.LULUS)
        self.assertEqual(biodata.jabatan_struktural, JabatanKader.KADER)
        self.assertEqual(
            Notifikasi.objects.filter(
                id_user=biodata.id_user,
                tipe=TipeNotifikasi.STATUS_KELULUSAN,
            ).count(),
            1,
        )

    def test_tidak_lulus_set_status_dan_notifikasi(self):
        pendaftaran, biodata = self._make_peserta_with_rekap(Decimal('50.00'))

        hasil = KelulusanService.tetapkan_kelulusan(Decimal('75.00'))

        self.assertEqual(hasil, {'lulus': 0, 'tidak_lulus': 1})
        pendaftaran.refresh_from_db()
        biodata.refresh_from_db()
        self.assertEqual(pendaftaran.status_kelulusan, StatusKelulusan.TIDAK_LULUS)
        # Jabatan TIDAK boleh dipromote untuk yang gagal
        self.assertEqual(biodata.jabatan_struktural, JabatanKader.CALON)
        self.assertEqual(
            Notifikasi.objects.filter(
                id_user=biodata.id_user,
                tipe=TipeNotifikasi.STATUS_KELULUSAN,
            ).count(),
            1,
        )

    def test_passing_grade_boundary_inclusive(self):
        # total_akhir tepat == passing_grade → harus LULUS (>=)
        pendaftaran, _ = self._make_peserta_with_rekap(Decimal('75.00'))

        KelulusanService.tetapkan_kelulusan(Decimal('75.00'))

        pendaftaran.refresh_from_db()
        self.assertEqual(pendaftaran.status_kelulusan, StatusKelulusan.LULUS)

    def test_mixed_returns_correct_counts(self):
        self._make_peserta_with_rekap(Decimal('90.00'))
        self._make_peserta_with_rekap(Decimal('80.00'))
        self._make_peserta_with_rekap(Decimal('40.00'))

        hasil = KelulusanService.tetapkan_kelulusan(Decimal('70.00'))

        self.assertEqual(hasil, {'lulus': 2, 'tidak_lulus': 1})

    def test_biodata_tanpa_user_tidak_crash(self):
        # Skenario edge: BiodataKader.id_user = NULL (calon kader yg dihapus
        # akunnya tapi data biodata masih ada). Service tidak boleh crash.
        pendaftaran, biodata = self._make_peserta_with_rekap(
            Decimal('90.00'), with_user=False,
        )

        hasil = KelulusanService.tetapkan_kelulusan(Decimal('75.00'))

        self.assertEqual(hasil, {'lulus': 1, 'tidak_lulus': 0})
        pendaftaran.refresh_from_db()
        biodata.refresh_from_db()
        self.assertEqual(pendaftaran.status_kelulusan, StatusKelulusan.LULUS)
        self.assertEqual(biodata.jabatan_struktural, JabatanKader.KADER)
        # Tidak ada notifikasi (karena user None)
        self.assertEqual(Notifikasi.objects.count(), 0)
