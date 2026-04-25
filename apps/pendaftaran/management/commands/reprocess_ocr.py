"""Management command untuk memproses ulang verifikasi SSO yang terhenti."""
from django.core.management.base import BaseCommand

from apps.pendaftaran.models import PendaftaranDAD
from apps.pendaftaran.services import PendaftaranService
from core.constants import StatusVerifikasi


class Command(BaseCommand):
    help = 'Proses ulang verifikasi SSO untuk record pendaftaran yang terhenti di status menunggu.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--id',
            type=int,
            help='Proses ulang satu pendaftaran tertentu berdasarkan id_pendaftaran.',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Proses ulang semua record dengan status menunggu.',
        )

    def handle(self, *args, **options):
        if options['id']:
            qs = PendaftaranDAD.objects.filter(id_pendaftaran=options['id'])
        elif options['all']:
            qs = PendaftaranDAD.objects.filter(status_verifikasi=StatusVerifikasi.MENUNGGU)
        else:
            self.stderr.write('Tentukan --id <pk> atau --all')
            return

        count = qs.count()
        self.stdout.write(f'Ditemukan {count} record yang akan diproses ulang.')

        for p in qs:
            self.stdout.write(f'Memproses {p.no_registrasi} ({p.id_biodata.nama_lengkap})...')
            # Reset status sebelum diproses ulang
            p.status_verifikasi = StatusVerifikasi.MENUNGGU
            p.is_identic = False
            p.api_nama_sso = None
            p.api_status_mahasiswa = None
            p.api_program_studi = None
            p.tgl_verifikasi = None
            p.save()

            PendaftaranService.process_verifikasi_sso(p)
            p.refresh_from_db()
            self.stdout.write(
                f'  -> Status: {p.get_status_verifikasi_display()}, '
                f'Nama SSO: {p.api_nama_sso}'
            )

        self.stdout.write(self.style.SUCCESS(f'Selesai. Berhasil memproses {count} record.'))
