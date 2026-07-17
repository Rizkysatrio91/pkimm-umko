"""Rapikan nilai `program_studi` & `fakultas` di BiodataKader agar PERSIS sama
dengan nama resmi di SSO API UMKO (endpoint `faculties/` & `departments/`).

Latar belakang: data biodata terisi dari beberapa jalur (registrasi mandiri,
autofill SSO, import) sehingga formatnya tidak konsisten, mis.:
    program_studi : "S1 - Sistem dan Teknologi Informasi"
                    "Sistem Teknologi Informasi"        (varian lama)
    fakultas      : "Fakultas Teknik dan Komputer"      (varian lama)
Padahal SSO memakai nama kanonik:
    program_studi : "Sistem dan Teknologi Informasi"    (departments.nama_unit)
    fakultas      : "Teknik dan Ilmu Komputer"          (faculties.nama_unit)

Command mencocokkan tiap nilai tersimpan ke nama SSO via irisan kata utama
(word-overlap), lalu meng-update baris yang berubah. Nilai yang TIDAK menemukan
padanan SSO (skor < ambang) dibiarkan apa adanya dan dilaporkan agar admin bisa
memeriksanya manual — TIDAK ada tebakan yang dipaksakan.

Catatan: field snapshot SSO di PendaftaranDAD (`api_program_studi`,
`api_status_mahasiswa`, dst.) sengaja TIDAK diubah karena merupakan rekaman
mentah apa adanya dari SSO saat pendaftaran (jejak audit).

Default = dry-run (hanya menampilkan rencana). Tambah `--apply` untuk menulis.
Contoh:
    python manage.py normalisasi_prodi_fakultas            # pratinjau
    python manage.py normalisasi_prodi_fakultas --apply    # eksekusi
    python manage.py normalisasi_prodi_fakultas --threshold 0.6
"""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.kader.models import BiodataKader
from core.exceptions import SSOServiceError
from core.services import SSOService

# Kata yang diabaikan saat mencocokkan (jenjang, kata sambung, kata generik).
STOP_WORDS = {
    'dan', 'atau', 'the', 'of', 'ilmu', 's1', 's2', 's3', 'd3', 'd4',
    'fakultas', 'fak', 'prodi', 'program', 'studi', 'jurusan',
}


def _kata_utama(s: str) -> set:
    """Pecah string jadi himpunan kata utama (lowercase, buang tanda baca & stopword)."""
    bersih = re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower())
    return {w for w in bersih.split() if w not in STOP_WORDS and len(w) > 1}


def _best_match(value: str, candidates: list, threshold: float):
    """Cari nama kandidat terbaik untuk `value` via rasio irisan kata utama.

    Return (nama_terbaik, skor) bila skor >= threshold, selain itu (None, skor).
    """
    tv = _kata_utama(value)
    if not tv:
        return None, 0.0
    best_name, best_score = None, 0.0
    for name in candidates:
        tc = _kata_utama(name)
        if not tc:
            continue
        irisan = tv & tc
        score = len(irisan) / max(len(tv), len(tc), 1)
        if score > best_score:
            best_score, best_name = score, name
    return (best_name, best_score) if best_score >= threshold else (None, best_score)


class Command(BaseCommand):
    help = 'Normalisasi program_studi & fakultas BiodataKader agar sesuai nama resmi SSO UMKO.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Tulis perubahan ke database. Tanpa flag ini hanya pratinjau (dry-run).',
        )
        parser.add_argument(
            '--threshold',
            type=float,
            default=0.5,
            help='Ambang minimal rasio kecocokan kata (0..1). Default 0.5.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        threshold = options['threshold']

        # ── Ambil daftar kanonik dari SSO ────────────────────────────────────
        try:
            sso = SSOService()
            faculties = sso.get_faculties()
            departments = sso.get_departments()
        except SSOServiceError as e:
            raise CommandError(f'Gagal mengambil data SSO: {e}')

        fakultas_names = sorted({f['nama_unit'] for f in faculties if f.get('nama_unit')})
        prodi_names = sorted({d['nama_unit'] for d in departments if d.get('nama_unit')})

        if not fakultas_names or not prodi_names:
            raise CommandError('SSO mengembalikan daftar fakultas/prodi kosong. Batalkan.')

        self.stdout.write(f'SSO: {len(fakultas_names)} fakultas, {len(prodi_names)} prodi (nama kanonik).')

        # ── Petakan tiap nilai DISTINCT tersimpan → nama SSO ─────────────────
        # order_by eksplisit WAJIB: tanpa ini Meta.ordering=['nama_lengkap'] ikut
        # ke SELECT sehingga DISTINCT jadi atas pasangan (kolom, nama_lengkap).
        distinct_prodi = sorted(
            BiodataKader.objects.exclude(program_studi='')
            .order_by('program_studi')
            .values_list('program_studi', flat=True).distinct()
        )
        distinct_fak = sorted(
            BiodataKader.objects.exclude(fakultas='')
            .order_by('fakultas')
            .values_list('fakultas', flat=True).distinct()
        )

        prodi_map, prodi_unmatched = {}, []
        for val in distinct_prodi:
            match, score = _best_match(val, prodi_names, threshold)
            if match and match != val:
                prodi_map[val] = match
            elif not match:
                prodi_unmatched.append((val, score))

        fak_map, fak_unmatched = {}, []
        for val in distinct_fak:
            match, score = _best_match(val, fakultas_names, threshold)
            if match and match != val:
                fak_map[val] = match
            elif not match:
                fak_unmatched.append((val, score))

        # ── Laporan rencana ──────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('== PROGRAM STUDI =='))
        for val in distinct_prodi:
            n = BiodataKader.objects.filter(program_studi=val).count()
            if val in prodi_map:
                self.stdout.write(f'  [ubah] "{val}"  →  "{prodi_map[val]}"   ({n} baris)')
            else:
                tail = '' if any(val == p for p in prodi_names) else '  (TIDAK ada padanan SSO — dibiarkan)'
                self.stdout.write(f'  [tetap] "{val}"   ({n} baris){tail}')

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('== FAKULTAS =='))
        for val in distinct_fak:
            n = BiodataKader.objects.filter(fakultas=val).count()
            if val in fak_map:
                self.stdout.write(f'  [ubah] "{val}"  →  "{fak_map[val]}"   ({n} baris)')
            else:
                tail = '' if any(val == f for f in fakultas_names) else '  (TIDAK ada padanan SSO — dibiarkan)'
                self.stdout.write(f'  [tetap] "{val}"   ({n} baris){tail}')

        if prodi_unmatched or fak_unmatched:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Perlu diperiksa manual (tanpa padanan SSO):'))
            for val, score in prodi_unmatched:
                self.stdout.write(self.style.WARNING(f'  prodi   "{val}" (skor terbaik {score:.2f})'))
            for val, score in fak_unmatched:
                self.stdout.write(self.style.WARNING(f'  fakultas "{val}" (skor terbaik {score:.2f})'))

        # ── Eksekusi ─────────────────────────────────────────────────────────
        total_prodi_rows = sum(
            BiodataKader.objects.filter(program_studi=v).count() for v in prodi_map
        )
        total_fak_rows = sum(
            BiodataKader.objects.filter(fakultas=v).count() for v in fak_map
        )

        self.stdout.write('')
        if not apply:
            self.stdout.write(self.style.NOTICE(
                f'DRY-RUN: {total_prodi_rows} baris program_studi & {total_fak_rows} baris fakultas '
                f'AKAN diubah. Jalankan ulang dengan --apply untuk menulis.'
            ))
            return

        with transaction.atomic():
            for old, new in prodi_map.items():
                BiodataKader.objects.filter(program_studi=old).update(program_studi=new)
            for old, new in fak_map.items():
                BiodataKader.objects.filter(fakultas=old).update(fakultas=new)

        self.stdout.write(self.style.SUCCESS(
            f'Selesai. {total_prodi_rows} baris program_studi & {total_fak_rows} baris fakultas diperbarui.'
        ))
