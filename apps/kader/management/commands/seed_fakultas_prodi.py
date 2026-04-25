"""Seed data awal Fakultas dan Program Studi."""
from django.core.management.base import BaseCommand

from apps.kader.models import Fakultas, ProgramStudi

SEED_DATA = [
    {
        'nama': 'Fakultas Keguruan dan Ilmu Pendidikan',
        'kode': 'FKIP',
        'prodi': [
            ('Pendidikan Guru Sekolah Dasar', 'PGSD'),
            ('Pendidikan Jasmani', 'PENJAS'),
            ('Pendidikan Bahasa Inggris', 'PBI'),
            ('Pendidikan Matematika', 'PM'),
            ('Pendidikan Bahasa Indonesia', 'PBINDO'),
        ],
    },
    {
        'nama': 'Fakultas Hukum dan Ilmu Sosial',
        'kode': 'FHIS',
        'prodi': [
            ('Hukum', 'HK'),
            ('Ilmu Komunikasi', 'IKOM'),
        ],
    },
    {
        'nama': 'Fakultas Pertanian dan Peternakan',
        'kode': 'FPP',
        'prodi': [
            ('Agribisnis', 'AGB'),
            ('Agroteknologi', 'AGT'),
            ('Nutrisi dan Teknologi Pakan Ternak', 'NTPT'),
        ],
    },
    {
        'nama': 'Fakultas Teknik dan Komputer',
        'kode': 'FTK',
        'prodi': [
            ('Sistem Teknologi Informasi', 'STI'),
            ('Informatika Medis', 'IM'),
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed data Fakultas dan Program Studi'

    def handle(self, *args, **options):
        for fak_data in SEED_DATA:
            fakultas, created = Fakultas.objects.get_or_create(
                kode_fakultas=fak_data['kode'],
                defaults={'nama_fakultas': fak_data['nama']},
            )
            action = 'Dibuat' if created else 'Sudah ada'
            self.stdout.write(f"  {action}: {fakultas.nama_fakultas}")

            for nama_prodi, kode_prodi in fak_data['prodi']:
                prodi, p_created = ProgramStudi.objects.get_or_create(
                    kode_prodi=kode_prodi,
                    defaults={
                        'fakultas': fakultas,
                        'nama_prodi': nama_prodi,
                    },
                )
                p_action = 'Dibuat' if p_created else 'Sudah ada'
                self.stdout.write(f"    {p_action}: {prodi.nama_prodi} ({kode_prodi})")

        self.stdout.write(self.style.SUCCESS('Seed fakultas & prodi selesai.'))
