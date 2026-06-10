"""Unit test untuk model di apps.penilaian.

Cakupan:
  - NilaiInterview.hitung_rata_rata (rata-rata 15 sub-skor, status LULUS/GAGAL).
  - NilaiInterview.save() auto-compute rata_rata.
  - NilaiInterview properti nilai_quran / hafalan / ideologi / dialektika / kesiapan
    (masing-masing rata-rata 3 sub-skor).
  - NilaiAktivitas.hitung_skor_harian (rata-rata 3 poin).
  - NilaiAktivitas.save() auto-compute skor_harian.
  - RekapLeaderboard.hitung_total_akhir.
  - RekapLeaderboard.perbarui_semua_peringkat.
"""
from decimal import Decimal

from django.test import TestCase

from apps.penilaian.models import (
    NilaiAktivitas,
    NilaiInterview,
    RekapLeaderboard,
)
from apps.penilaian.tests import factories as F
from core.constants import StatusInterview, UserRole


class NilaiInterviewFormulaTests(TestCase):
    """Test rumus NilaiInterview 15 sub-skor."""

    def setUp(self) -> None:
        self.panitia = F.make_user(role=UserRole.PANITIA)
        self.pendaftaran = F.make_pendaftaran()

    def _make_interview(self, value: Decimal) -> NilaiInterview:
        """Buat NilaiInterview dengan semua 15 sub-skor diisi nilai sama."""
        kwargs = {f: value for f in NilaiInterview.SUB_FIELDS}
        # NOTE: kita sengaja TIDAK panggil .save() di sini karena save() akan
        # auto-hitung rata_rata. Test ingin verifikasi metode hitung_rata_rata
        # eksplisit dulu, baru test save() di test lain.
        return NilaiInterview(
            id_pendaftaran=self.pendaftaran,
            id_panitia=self.panitia,
            **kwargs,
        )

    def test_semua_seratus_lulus(self):
        interview = self._make_interview(Decimal('100.00'))
        interview.hitung_rata_rata()
        self.assertEqual(interview.rata_rata, Decimal('100.00'))
        self.assertEqual(interview.status_interview, StatusInterview.LULUS)

    def test_semua_nol_gagal(self):
        interview = self._make_interview(Decimal('0.00'))
        interview.hitung_rata_rata()
        self.assertEqual(interview.rata_rata, Decimal('0.00'))
        self.assertEqual(interview.status_interview, StatusInterview.GAGAL)

    def test_boundary_60_lulus(self):
        # Threshold LULUS: rata_rata >= 60.00
        interview = self._make_interview(Decimal('60.00'))
        interview.hitung_rata_rata()
        self.assertEqual(interview.rata_rata, Decimal('60.00'))
        self.assertEqual(interview.status_interview, StatusInterview.LULUS)

    def test_under_60_gagal(self):
        interview = self._make_interview(Decimal('59.99'))
        interview.hitung_rata_rata()
        self.assertEqual(interview.status_interview, StatusInterview.GAGAL)

    def test_rata_rata_15_sub_skor(self):
        # 5 sub-skor = 100, 10 sub-skor = 0 → rata-rata = 500/15 = 33.33...
        interview = NilaiInterview(
            id_pendaftaran=self.pendaftaran,
            id_panitia=self.panitia,
        )
        nilai_per_field = [Decimal('100')] * 5 + [Decimal('0')] * 10
        for f, v in zip(NilaiInterview.SUB_FIELDS, nilai_per_field):
            setattr(interview, f, v)
        interview.hitung_rata_rata()
        self.assertEqual(interview.rata_rata, Decimal('33.33'))
        self.assertEqual(interview.status_interview, StatusInterview.GAGAL)

    def test_save_auto_hitung_rata_rata(self):
        # Simpan dengan semua sub-skor = 80, rata_rata harus auto-set ke 80.
        kwargs = {f: Decimal('80.00') for f in NilaiInterview.SUB_FIELDS}
        interview = NilaiInterview.objects.create(
            id_pendaftaran=self.pendaftaran,
            id_panitia=self.panitia,
            **kwargs,
        )
        # rata_rata di-init 0 di constructor → di-overwrite oleh save()
        self.assertEqual(interview.rata_rata, Decimal('80.00'))
        self.assertEqual(interview.status_interview, StatusInterview.LULUS)

    def test_property_nilai_kategori(self):
        interview = NilaiInterview(
            id_pendaftaran=self.pendaftaran,
            id_panitia=self.panitia,
            qur_makhraj_tajwid=Decimal('90'),
            qur_tulis_surat=Decimal('60'),
            qur_kandungan_surat=Decimal('30'),
            hafalan_5_pendek=Decimal('40'),
            hafalan_2_pengkaderan=Decimal('70'),
            hafalan_1_favorit=Decimal('100'),
        )
        # (90 + 60 + 30) / 3 = 60
        self.assertEqual(interview.nilai_quran, Decimal('60'))
        # (40 + 70 + 100) / 3 = 70
        self.assertEqual(interview.nilai_hafalan, Decimal('70'))
        # Field kategori lain default 0 → property = 0
        self.assertEqual(interview.nilai_ideologi, Decimal('0'))
        self.assertEqual(interview.nilai_dialektika, Decimal('0'))
        self.assertEqual(interview.nilai_kesiapan, Decimal('0'))


class NilaiAktivitasFormulaTests(TestCase):
    """Test rumus NilaiAktivitas.skor_harian = rata-rata 3 poin."""

    def setUp(self) -> None:
        self.panitia = F.make_user(role=UserRole.PANITIA)
        self.pendaftaran = F.make_pendaftaran()

    def test_hitung_skor_harian_rata_rata_3_poin(self):
        aktivitas = NilaiAktivitas(
            id_pendaftaran=self.pendaftaran,
            id_panitia=self.panitia,
            hari_ke=1,
            poin_keaktifan=Decimal('100'),
            poin_kedisiplinan=Decimal('80'),
            poin_kontribusi=Decimal('60'),
        )
        aktivitas.hitung_skor_harian()
        # (100 + 80 + 60) / 3 = 80
        self.assertEqual(aktivitas.skor_harian, Decimal('80'))

    def test_save_auto_compute_skor_harian(self):
        aktivitas = NilaiAktivitas.objects.create(
            id_pendaftaran=self.pendaftaran,
            id_panitia=self.panitia,
            hari_ke=1,
            poin_keaktifan=Decimal('90.00'),
            poin_kedisiplinan=Decimal('60.00'),
            poin_kontribusi=Decimal('60.00'),
        )
        # (90 + 60 + 60) / 3 = 70 → DecimalField max 2 desimal
        self.assertEqual(aktivitas.skor_harian.quantize(Decimal('0.01')), Decimal('70.00'))


class RekapLeaderboardTests(TestCase):
    """Test RekapLeaderboard.hitung_total_akhir & perbarui_semua_peringkat."""

    def setUp(self) -> None:
        self.periode = F.make_periode()
        self.kelompok = F.make_kelompok(self.periode)

    def _make_rekap(
        self,
        total_skor_aktivitas: Decimal,
        nilai_interview: Decimal,
        peringkat: int = 0,
    ) -> RekapLeaderboard:
        pendaftaran = F.make_pendaftaran(
            periode=self.periode, kelompok=self.kelompok,
        )
        return RekapLeaderboard.objects.create(
            id_pendaftaran=pendaftaran,
            total_skor_aktivitas=total_skor_aktivitas,
            nilai_interview=nilai_interview,
            peringkat=peringkat,
        )

    def test_hitung_total_akhir_rata_dua(self):
        rekap = self._make_rekap(Decimal('80.00'), Decimal('60.00'))
        rekap.hitung_total_akhir()
        # (80 + 60) / 2 = 70
        self.assertEqual(rekap.total_akhir, Decimal('70'))

    def test_hitung_total_akhir_dengan_nol(self):
        rekap = self._make_rekap(Decimal('0.00'), Decimal('0.00'))
        rekap.hitung_total_akhir()
        self.assertEqual(rekap.total_akhir, Decimal('0'))

    def test_perbarui_semua_peringkat_urut_descending(self):
        # Ada beberapa rekap dengan total_akhir berbeda — peringkat harus
        # turun (terbesar = peringkat 1).
        r1 = self._make_rekap(Decimal('40'), Decimal('40'))  # total 40
        r2 = self._make_rekap(Decimal('90'), Decimal('90'))  # total 90
        r3 = self._make_rekap(Decimal('60'), Decimal('60'))  # total 60
        # set total_akhir manual karena signal sudah dijalankan saat create
        for r in (r1, r2, r3):
            r.hitung_total_akhir()
            r.save()

        RekapLeaderboard.perbarui_semua_peringkat()

        r1.refresh_from_db()
        r2.refresh_from_db()
        r3.refresh_from_db()
        self.assertEqual(r2.peringkat, 1)
        self.assertEqual(r3.peringkat, 2)
        self.assertEqual(r1.peringkat, 3)
