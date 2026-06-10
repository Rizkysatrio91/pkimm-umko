"""Test regresi bug timezone pada jadwal input nilai aktivitas DAD harian.

Bug: ``periode.tgl_mulai_kegiatan.date()`` mengambil tanggal dari datetime
aware ber-UTC. Karena TIME_ZONE = Asia/Jakarta (UTC+7), jadwal yang di-set
admin jam 00:00–06:59 WIB tersimpan sebagai UTC pada TANGGAL SEBELUMNYA,
sehingga seluruh pemetaan Hari 1/2/3 bergeser mundur 1 hari dan panitia
bisa menilai Hari ke-2 padahal masih Hari ke-1.

Fix: konversi dengan ``timezone.localtime()`` sebelum ``.date()``.
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

POST_DATA = {'poin_keaktifan': '80', 'poin_kontribusi': '80'}


class AktivitasTanggalTimezoneTest(TestCase):
    """Kegiatan DAD mulai hari ini jam 00:00 WIB → hanya Hari 1 yang boleh diisi."""

    def setUp(self):
        now_local = timezone.localtime()
        mulai_kegiatan = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        self.periode = make_periode(
            tgl_buka_administrasi=now_local - timedelta(days=10),
            tgl_tutup_administrasi=now_local - timedelta(days=8),
            tgl_mulai_interview=now_local - timedelta(days=6),
            tgl_selesai_interview=now_local - timedelta(days=4),
            tgl_mulai_kegiatan=mulai_kegiatan,
            tgl_selesai_kegiatan=mulai_kegiatan + timedelta(days=2, hours=23),
        )
        self.panitia = make_user(role=UserRole.PANITIA)
        kelompok = make_kelompok(self.periode, NamaKelompok.A, pj=self.panitia)
        self.peserta = make_pendaftaran(
            periode=self.periode, kelompok=kelompok,
            status_verifikasi=StatusVerifikasi.LOLOS,
        )
        NilaiInterview.objects.create(
            id_pendaftaran=self.peserta,
            id_panitia=self.panitia,
            **{f: Decimal('80') for f in NilaiInterview.SUB_FIELDS},
        )
        self.client.force_login(self.panitia)

    def test_hari_1_boleh_diisi(self):
        url = reverse('panitia:aktivitas_create', args=[self.peserta.id_pendaftaran, 1])
        self.client.post(url, POST_DATA)
        self.assertTrue(
            NilaiAktivitas.objects.filter(
                id_pendaftaran=self.peserta, hari_ke=1,
            ).exists(),
        )

    def test_hari_2_ditolak_sebelum_tanggalnya(self):
        """Regresi bug timezone: Hari 2 = besok, TIDAK boleh diisi hari ini."""
        url = reverse('panitia:aktivitas_create', args=[self.peserta.id_pendaftaran, 2])
        resp = self.client.post(url, POST_DATA)
        self.assertRedirects(resp, reverse('panitia:aktivitas_list'))
        self.assertFalse(
            NilaiAktivitas.objects.filter(
                id_pendaftaran=self.peserta, hari_ke=2,
            ).exists(),
        )

    def test_hari_3_ditolak_sebelum_tanggalnya(self):
        url = reverse('panitia:aktivitas_create', args=[self.peserta.id_pendaftaran, 3])
        resp = self.client.post(url, POST_DATA)
        self.assertRedirects(resp, reverse('panitia:aktivitas_list'))
        self.assertFalse(
            NilaiAktivitas.objects.filter(
                id_pendaftaran=self.peserta, hari_ke=3,
            ).exists(),
        )

    def test_list_status_tersedia_per_hari(self):
        """Di daftar peserta: kolom Hari 1 terbuka, Hari 2 & 3 terkunci."""
        resp = self.client.get(reverse('panitia:aktivitas_list'))
        self.assertEqual(resp.status_code, 200)
        peserta = list(resp.context['peserta_list'])[0]
        tersedia_map = {h['hari']: h['tersedia'] for h in peserta.hari_status}
        self.assertTrue(tersedia_map[1])
        self.assertFalse(tersedia_map[2])
        self.assertFalse(tersedia_map[3])

    def test_tanggal_hari_sesuai_waktu_lokal(self):
        """Tanggal Hari 1 harus = tanggal lokal hari ini (bukan tanggal UTC)."""
        resp = self.client.get(reverse('panitia:aktivitas_list'))
        peserta = list(resp.context['peserta_list'])[0]
        tanggal_map = {h['hari']: h['tanggal'] for h in peserta.hari_status}
        today_local = timezone.localdate()
        self.assertEqual(tanggal_map[1], today_local)
        self.assertEqual(tanggal_map[2], today_local + timedelta(days=1))
        self.assertEqual(tanggal_map[3], today_local + timedelta(days=2))
