"""Test pembatasan penilaian panitia per kelompok (KelompokScopeMixin).

Aturan bisnis:
  - Panitia (PJ kelompok) hanya melihat & menilai peserta kelompoknya sendiri,
    baik pada seleksi interview maupun penilaian aktivitas DAD 3 hari.
  - Admin tidak dibatasi — bisa melihat & menilai semua kelompok.
  - Panitia tanpa kelompok PJ tidak melihat peserta mana pun.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.penilaian.models import NilaiAktivitas, NilaiInterview
from apps.penilaian.tests.factories import (
    make_kelompok,
    make_pendaftaran,
    make_periode,
    make_user,
)
from core.constants import NamaKelompok, StatusVerifikasi, UserRole


def _periode_tahap_interview():
    """Periode aktif yang sedang berada di tahap interview."""
    now = timezone.now()
    return make_periode(
        tgl_buka_administrasi=now - timedelta(days=10),
        tgl_tutup_administrasi=now - timedelta(days=5),
        tgl_mulai_interview=now - timedelta(days=1),
        tgl_selesai_interview=now + timedelta(days=1),
    )


def _periode_tahap_kegiatan():
    """Periode aktif yang sedang berada di tahap kegiatan DAD (3 hari)."""
    now = timezone.now()
    return make_periode(
        tgl_buka_administrasi=now - timedelta(days=10),
        tgl_tutup_administrasi=now - timedelta(days=8),
        tgl_mulai_interview=now - timedelta(days=6),
        tgl_selesai_interview=now - timedelta(days=4),
        tgl_mulai_kegiatan=now - timedelta(days=1),
        tgl_selesai_kegiatan=now + timedelta(days=2),
    )


INTERVIEW_POST_DATA = {
    f: '80' for f in NilaiInterview.SUB_FIELDS
}


class InterviewScopeTest(TestCase):
    """Panitia hanya melihat & menilai interview peserta kelompoknya."""

    def setUp(self):
        self.periode = _periode_tahap_interview()
        self.panitia_a = make_user(role=UserRole.PANITIA)
        self.panitia_b = make_user(role=UserRole.PANITIA)
        self.kelompok_a = make_kelompok(self.periode, NamaKelompok.A, pj=self.panitia_a)
        self.kelompok_b = make_kelompok(self.periode, NamaKelompok.B, pj=self.panitia_b)
        self.peserta_a = make_pendaftaran(
            periode=self.periode, kelompok=self.kelompok_a,
            status_verifikasi=StatusVerifikasi.LOLOS,
        )
        self.peserta_b = make_pendaftaran(
            periode=self.periode, kelompok=self.kelompok_b,
            status_verifikasi=StatusVerifikasi.LOLOS,
        )

    def test_list_hanya_kelompok_sendiri(self):
        self.client.force_login(self.panitia_a)
        resp = self.client.get(reverse('panitia:interview_list'))
        self.assertEqual(resp.status_code, 200)
        ids = [p.id_pendaftaran for p in resp.context['pendaftaran_list']]
        self.assertIn(self.peserta_a.id_pendaftaran, ids)
        self.assertNotIn(self.peserta_b.id_pendaftaran, ids)

    def test_panitia_tanpa_kelompok_list_kosong(self):
        panitia_baru = make_user(role=UserRole.PANITIA)
        self.client.force_login(panitia_baru)
        resp = self.client.get(reverse('panitia:interview_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['pendaftaran_list']), 0)

    def test_tidak_bisa_nilai_kelompok_lain(self):
        self.client.force_login(self.panitia_a)
        url = reverse('panitia:interview_create', args=[self.peserta_b.id_pendaftaran])
        resp = self.client.post(url, INTERVIEW_POST_DATA)
        self.assertRedirects(resp, reverse('panitia:interview_list'))
        self.assertFalse(
            NilaiInterview.objects.filter(id_pendaftaran=self.peserta_b).exists(),
        )

    def test_bisa_nilai_kelompok_sendiri(self):
        self.client.force_login(self.panitia_a)
        url = reverse('panitia:interview_create', args=[self.peserta_a.id_pendaftaran])
        resp = self.client.post(url, INTERVIEW_POST_DATA)
        self.assertRedirects(resp, reverse('panitia:interview_list'))
        self.assertTrue(
            NilaiInterview.objects.filter(id_pendaftaran=self.peserta_a).exists(),
        )

    def test_admin_bisa_nilai_semua_kelompok(self):
        admin = make_user(role=UserRole.ADMIN)
        self.client.force_login(admin)
        url = reverse('panitia:interview_create', args=[self.peserta_b.id_pendaftaran])
        resp = self.client.post(url, INTERVIEW_POST_DATA)
        # fetch_redirect_response=False: sidebar admin me-render URL dari app
        # yang dibuang di settings test (chatbot/laporan/berita).
        self.assertRedirects(
            resp, reverse('panitia:interview_list'), fetch_redirect_response=False,
        )
        self.assertTrue(
            NilaiInterview.objects.filter(id_pendaftaran=self.peserta_b).exists(),
        )

    def test_detail_kelompok_lain_404(self):
        nilai_b = NilaiInterview.objects.create(
            id_pendaftaran=self.peserta_b,
            id_panitia=self.panitia_b,
            **{f: Decimal('80') for f in NilaiInterview.SUB_FIELDS},
        )
        self.client.force_login(self.panitia_a)
        url = reverse('panitia:interview_detail', args=[nilai_b.id_interview])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


class AktivitasScopeTest(TestCase):
    """Panitia hanya melihat & menilai aktivitas DAD peserta kelompoknya."""

    def setUp(self):
        self.periode = _periode_tahap_kegiatan()
        self.panitia_a = make_user(role=UserRole.PANITIA)
        self.panitia_b = make_user(role=UserRole.PANITIA)
        self.kelompok_a = make_kelompok(self.periode, NamaKelompok.A, pj=self.panitia_a)
        self.kelompok_b = make_kelompok(self.periode, NamaKelompok.B, pj=self.panitia_b)
        self.peserta_a = make_pendaftaran(
            periode=self.periode, kelompok=self.kelompok_a,
            status_verifikasi=StatusVerifikasi.LOLOS,
        )
        self.peserta_b = make_pendaftaran(
            periode=self.periode, kelompok=self.kelompok_b,
            status_verifikasi=StatusVerifikasi.LOLOS,
        )
        # Keduanya sudah lulus interview agar muncul di daftar aktivitas
        for peserta, panitia in (
            (self.peserta_a, self.panitia_a),
            (self.peserta_b, self.panitia_b),
        ):
            NilaiInterview.objects.create(
                id_pendaftaran=peserta,
                id_panitia=panitia,
                **{f: Decimal('80') for f in NilaiInterview.SUB_FIELDS},
            )

    def test_list_hanya_kelompok_sendiri(self):
        self.client.force_login(self.panitia_a)
        resp = self.client.get(reverse('panitia:aktivitas_list'))
        self.assertEqual(resp.status_code, 200)
        ids = [p.id_pendaftaran for p in resp.context['peserta_list']]
        self.assertIn(self.peserta_a.id_pendaftaran, ids)
        self.assertNotIn(self.peserta_b.id_pendaftaran, ids)

    def test_tidak_bisa_nilai_kelompok_lain(self):
        self.client.force_login(self.panitia_a)
        url = reverse('panitia:aktivitas_create', args=[self.peserta_b.id_pendaftaran, 1])
        resp = self.client.post(url, {'poin_keaktifan': '80', 'poin_kontribusi': '80'})
        self.assertRedirects(resp, reverse('panitia:aktivitas_list'))
        self.assertFalse(
            NilaiAktivitas.objects.filter(id_pendaftaran=self.peserta_b).exists(),
        )

    def test_bisa_nilai_kelompok_sendiri(self):
        self.client.force_login(self.panitia_a)
        url = reverse('panitia:aktivitas_create', args=[self.peserta_a.id_pendaftaran, 1])
        resp = self.client.post(url, {'poin_keaktifan': '80', 'poin_kontribusi': '80'})
        self.assertRedirects(resp, reverse('panitia:aktivitas_list'))
        self.assertTrue(
            NilaiAktivitas.objects.filter(
                id_pendaftaran=self.peserta_a, hari_ke=1,
            ).exists(),
        )

    def test_admin_bisa_nilai_semua_kelompok(self):
        admin = make_user(role=UserRole.ADMIN)
        self.client.force_login(admin)
        url = reverse('panitia:aktivitas_create', args=[self.peserta_b.id_pendaftaran, 1])
        resp = self.client.post(url, {'poin_keaktifan': '80', 'poin_kontribusi': '80'})
        # fetch_redirect_response=False: sidebar admin me-render URL dari app
        # yang dibuang di settings test (chatbot/laporan/berita).
        self.assertRedirects(
            resp, reverse('panitia:aktivitas_list'), fetch_redirect_response=False,
        )
        self.assertTrue(
            NilaiAktivitas.objects.filter(
                id_pendaftaran=self.peserta_b, hari_ke=1,
            ).exists(),
        )
