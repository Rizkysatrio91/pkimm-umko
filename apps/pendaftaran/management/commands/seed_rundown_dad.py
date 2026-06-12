"""Seed rundown DAD dari dokumen resmi RUNDOWN_DAD_FTIK_FIX.docx.

Sumber data: templates/laporan_template/RUNDOWN_DAD_FTIK_FIX.docx
(Rundown Darul Arqom Dasar PK IMM FTIK UMKO, 20-23 November 2025).

Idempoten: sesi di-update_or_create berdasarkan (periode, tanggal,
jam_mulai, materi), lalu QR absensi di-generate untuk semua sesi
is_absensi x kelompok A/B/C (skip yang sudah ada) — sama seperti
tombol "Generate QR" di dashboard admin.
"""
from datetime import date, time

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pendaftaran.models import PeriodeDAD, RundownDAD
from apps.pendaftaran.services import AbsensiService

TGL_KEDATANGAN = date(2025, 11, 20)  # Kamis
TGL_HARI1 = date(2025, 11, 21)       # Jum'at
TGL_HARI2 = date(2025, 11, 22)       # Sabtu
TGL_HARI3 = date(2025, 11, 23)       # Minggu

# Tiap baris: (hari_ke, tanggal, jam_mulai, jam_selesai, materi,
#              pemateri_a, pemateri_b, pemateri_c, pj_a, pj_b, pj_c,
#              is_absensi, urutan)
# Catatan koreksi typo dokumen: "11.30 - 13.000" -> 13:00,
# "Instruksur" -> "Instruktur". Nama pemateri ditulis apa adanya.
RUNDOWN_DATA = [
    # ── Kedatangan — Kamis, 20 November 2025 ──────────────────────────
    ('Kedatangan', TGL_KEDATANGAN, time(14, 0), time(15, 0), 'Kedatangan Peserta',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 1),
    ('Kedatangan', TGL_KEDATANGAN, time(15, 0), time(15, 30), 'Sholat Ashar',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 2),
    ('Kedatangan', TGL_KEDATANGAN, time(15, 30), time(17, 0), 'Pembukaan DAD',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 3),
    ('Kedatangan', TGL_KEDATANGAN, time(17, 0), time(18, 0), 'MCK',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 4),
    ('Kedatangan', TGL_KEDATANGAN, time(18, 0), time(21, 30), 'Ishoma',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 5),
    ('Kedatangan', TGL_KEDATANGAN, time(21, 30), time(0, 0), 'Pendobrakan dan Kontrak Belajar',
     'MOT', 'MOT', 'MOT', 'Instruktur', 'Instruktur', 'Instruktur', True, 6),

    # ── Hari 1 — Jum'at, 21 November 2025 ─────────────────────────────
    ('Hari 1', TGL_HARI1, time(0, 0), time(3, 0), 'Wisata Pulau Kapuk',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 1),
    ('Hari 1', TGL_HARI1, time(3, 0), time(6, 0), 'Tahajud, Shalat Subuh, Fathul Qulub',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 2),
    ('Hari 1', TGL_HARI1, time(6, 0), time(6, 30), 'Senam',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 3),
    ('Hari 1', TGL_HARI1, time(6, 30), time(7, 45), 'MCK dan Sarapan',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 4),
    ('Hari 1', TGL_HARI1, time(8, 0), time(9, 30), 'Al Islam',
     'Izzah Azizah', 'Drs. H. Zainal Abidin, M.Pd.I', 'Abi Fikri Maksum, S.Pd',
     'Instruktur', 'Instruktur', 'Instruktur', True, 5),
    ('Hari 1', TGL_HARI1, time(9, 30), time(11, 0), 'Kemuhammadiyahan',
     'Abi H. Ahmad Junaidi, M.Ag', 'Dr. Muryadi, S.Pd.I., S.H., M.Pd.I', 'Abi Ngadiyan, S.Pd.I., M.Pd.I',
     'Instruktur', 'Instruktur', 'Instruktur', True, 6),
    ('Hari 1', TGL_HARI1, time(11, 0), time(11, 30), 'Evaluasi',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 7),
    ('Hari 1', TGL_HARI1, time(11, 30), time(13, 0), 'Ishoma',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 8),
    ('Hari 1', TGL_HARI1, time(13, 0), time(15, 0), 'Ke-IMMan',
     'PC IMM LAMPURA', 'PC IMM LAMPURA', 'PC IMM LAMPURA',
     'Instruktur', 'Instruktur', 'Instruktur', True, 9),
    ('Hari 1', TGL_HARI1, time(15, 0), time(15, 30), 'Shalat Ashar',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 10),
    ('Hari 1', TGL_HARI1, time(15, 30), time(17, 0), 'Manajemen Organisasi',
     'Yansen Atik', 'Bram Fikma', 'Okta Irjun Saputra',
     'Instruktur', 'Instruktur', 'Instruktur', True, 11),
    ('Hari 1', TGL_HARI1, time(17, 0), time(18, 0), 'MCK',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 12),
    ('Hari 1', TGL_HARI1, time(18, 0), time(19, 30), 'Ishoma',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 13),
    ('Hari 1', TGL_HARI1, time(19, 30), time(20, 0), 'Evaluasi',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 14),
    ('Hari 1', TGL_HARI1, time(20, 0), time(21, 30), 'DDL',
     'Kanda Dewan', 'Yunda Amal', 'Ako',
     'Instruktur', 'Instruktur', 'Instruktur', True, 15),
    ('Hari 1', TGL_HARI1, time(21, 30), time(0, 0), 'FGD',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 16),

    # ── Hari 2 — Sabtu, 22 November 2025 ──────────────────────────────
    ('Hari 2', TGL_HARI2, time(0, 0), time(3, 0), 'Wisata Pulau Kapuk',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 1),
    ('Hari 2', TGL_HARI2, time(3, 0), time(6, 0), 'Tahajud, Shalat Subuh, Fathul Qulub',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 2),
    ('Hari 2', TGL_HARI2, time(6, 0), time(7, 0), 'Senam',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 3),
    ('Hari 2', TGL_HARI2, time(7, 0), time(8, 0), 'MCK dan Sarapan',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 4),
    ('Hari 2', TGL_HARI2, time(8, 0), time(9, 30), 'Analisis Sosial',
     'Kanda Firman Atik', 'Kanda Jefri Ramdani', 'Kanda Mirdan Kurniawan',
     'Instruktur', 'Instruktur', 'Instruktur', True, 5),
    ('Hari 2', TGL_HARI2, time(9, 30), time(10, 0), 'Evaluasi',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 6),
    ('Hari 2', TGL_HARI2, time(10, 0), time(11, 30), 'Inovasi Digital di Era Society 5.0',
     'Ibunda Khusnul Khotimah', 'Adi Wibowo', 'Ryan Aji Wijaya',
     'Instruktur', 'Instruktur', 'Instruktur', True, 7),
    ('Hari 2', TGL_HARI2, time(11, 30), time(13, 0), 'Ishoma',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 8),
    ('Hari 2', TGL_HARI2, time(13, 0), time(14, 30), 'Agitasi Propaganda',
     'Yudi Saputra', 'Hagi Julio Salas', 'Irhammudin',
     'Instruktur', 'Instruktur', 'Instruktur', True, 9),
    ('Hari 2', TGL_HARI2, time(14, 30), time(15, 0), 'Evaluasi',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 10),
    ('Hari 2', TGL_HARI2, time(15, 0), time(15, 30), 'Sholat Ashar',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 11),
    ('Hari 2', TGL_HARI2, time(15, 30), time(17, 0), 'FGD',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 12),
    ('Hari 2', TGL_HARI2, time(17, 0), time(18, 0), 'MCK',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 13),
    ('Hari 2', TGL_HARI2, time(18, 0), time(19, 30), 'Ishoma',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 14),
    ('Hari 2', TGL_HARI2, time(20, 0), time(21, 30), 'Teknik Sidang',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', True, 15),
    ('Hari 2', TGL_HARI2, time(21, 30), time(0, 0), 'Simulasi Sidang',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', True, 16),

    # ── Hari 3 — Minggu, 23 November 2025 ─────────────────────────────
    ('Hari 3', TGL_HARI3, time(0, 0), time(2, 30), 'Wisata Pulau Kapuk',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 1),
    ('Hari 3', TGL_HARI3, time(2, 30), time(6, 0), 'Tahajud, Shalat Subuh, Renungan',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', False, 2),
    ('Hari 3', TGL_HARI3, time(6, 0), time(7, 0), 'Istirahat',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 3),
    ('Hari 3', TGL_HARI3, time(7, 0), time(8, 0), 'MCK dan Sarapan',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 4),
    ('Hari 3', TGL_HARI3, time(8, 0), time(10, 30), 'Arah Gerakan',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', True, 5),
    ('Hari 3', TGL_HARI3, time(10, 30), time(12, 0), 'RTL',
     '', '', '', 'Instruktur', 'Instruktur', 'Instruktur', True, 6),
    ('Hari 3', TGL_HARI3, time(12, 0), time(13, 0), 'Ishoma',
     '', '', '', 'Panitia', 'Panitia', 'Panitia', False, 7),
]


class Command(BaseCommand):
    help = (
        'Seed rundown DAD 20-23 November 2025 (Kedatangan + Hari 1-3) dari '
        'dokumen resmi, lalu generate QR absensi per sesi x kelompok.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--periode',
            type=int,
            help='id_periode target. Default: periode yang sedang aktif.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Tampilkan apa yang akan dibuat tanpa menyimpan ke database.',
        )

    def handle(self, *args, **options):
        if options['periode']:
            periode = PeriodeDAD.objects.filter(pk=options['periode']).first()
            if not periode:
                self.stderr.write(f"Periode id={options['periode']} tidak ditemukan.")
                return
        else:
            periode = PeriodeDAD.get_active_period()
            if not periode:
                self.stderr.write('Tidak ada periode aktif. Gunakan --periode <id>.')
                return

        self.stdout.write(f'Target periode: [{periode.pk}] {periode.nama_periode}')
        self.stdout.write(f'Jumlah sesi di dokumen: {len(RUNDOWN_DATA)}')

        if options['dry_run']:
            for row in RUNDOWN_DATA:
                hari, tgl, mulai, selesai, materi = row[0], row[1], row[2], row[3], row[4]
                qr = 'QR' if row[11] else '--'
                self.stdout.write(
                    f'  [{qr}] {hari:<10} {tgl} {mulai:%H:%M}-{selesai:%H:%M}  {materi}'
                )
            self.stdout.write(self.style.WARNING('Dry-run: tidak ada yang disimpan.'))
            return

        created, updated = 0, 0
        with transaction.atomic():
            for row in RUNDOWN_DATA:
                (hari, tgl, mulai, selesai, materi,
                 pa, pb, pc, ja, jb, jc, absen, urutan) = row
                _, is_new = RundownDAD.objects.update_or_create(
                    id_periode=periode,
                    tanggal=tgl,
                    jam_mulai=mulai,
                    materi=materi,
                    defaults={
                        'hari_ke': hari,
                        'jam_selesai': selesai,
                        'pemateri_a': pa, 'pemateri_b': pb, 'pemateri_c': pc,
                        'pj_a': ja, 'pj_b': jb, 'pj_c': jc,
                        'is_absensi': absen,
                        'urutan': urutan,
                    },
                )
                if is_new:
                    created += 1
                else:
                    updated += 1

            qr_created = AbsensiService.generate_all_qr(periode)

        total_qr_sesi = sum(1 for r in RUNDOWN_DATA if r[11])
        self.stdout.write(self.style.SUCCESS(
            f'Selesai: {created} sesi dibuat, {updated} sesi di-update. '
            f'{total_qr_sesi} sesi ber-QR, {qr_created} QR absensi baru '
            f'di-generate (kelompok A/B/C).'
        ))
