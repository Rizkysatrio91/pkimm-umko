"""Seed entri dataset chatbot contoh."""
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.chatbot.models import DatasetChatbot


class Command(BaseCommand):
    help = 'Seed 3 entri dataset chatbot contoh (jenis=umum)'

    def handle(self, *args, **options):
        admin = User.objects.filter(role='admin').first()
        if not admin:
            self.stderr.write('Tidak ada user admin yang ditemukan. Buat terlebih dahulu.')
            return

        datasets = [
            {
                'intent_keyword': 'ideologi, ideologi imm, tri kompetensi, trikologi',
                'respon_jawaban': (
                    'IMM memiliki Tri Kompetensi Dasar (Trikologi) yaitu: '
                    '1) Religiusitas - pemahaman dan pengamalan nilai-nilai Islam, '
                    '2) Intelektualitas - pengembangan keilmuan dan daya kritis, '
                    '3) Humanitas - kepekaan sosial dan kemanusiaan. '
                    'Ketiga kompetensi ini menjadi landasan gerakan kader IMM.'
                ),
                'instruksi_ai': (
                    'Kamu adalah asisten IMM yang menjelaskan ideologi dan nilai-nilai IMM. '
                    'Jawab dengan ramah, informatif, dan gunakan bahasa Indonesia yang baik.'
                ),
                'kategori': 'umum',
                'jenis_chatbot': 'umum',
            },
            {
                'intent_keyword': 'sejarah, sejarah imm, kapan berdiri, pendiri',
                'respon_jawaban': (
                    'Ikatan Mahasiswa Muhammadiyah (IMM) didirikan pada tanggal 14 Maret 1964 '
                    'di Yogyakarta. IMM merupakan organisasi otonom (ortom) Muhammadiyah '
                    'di kalangan mahasiswa. Pendirinya antara lain Djamaluddin Aly dan '
                    'tokoh-tokoh mahasiswa Muhammadiyah lainnya. IMM bertujuan untuk '
                    'membentuk akademisi Islam yang berakhlak mulia, berpengetahuan luas, '
                    'dan berguna bagi masyarakat.'
                ),
                'instruksi_ai': (
                    'Kamu adalah asisten IMM yang menjelaskan sejarah IMM. '
                    'Jawab dengan akurat, ramah, dan dalam bahasa Indonesia yang baik.'
                ),
                'kategori': 'umum',
                'jenis_chatbot': 'umum',
            },
            {
                'intent_keyword': 'struktur, organisasi, pengurus, pimpinan, komisariat',
                'respon_jawaban': (
                    'Struktur organisasi IMM terdiri dari: '
                    '1) Dewan Pimpinan Pusat (DPP) - tingkat nasional, '
                    '2) Dewan Pimpinan Daerah (DPD) - tingkat provinsi, '
                    '3) Dewan Pimpinan Cabang (DPC) - tingkat kabupaten/kota, '
                    '4) Pimpinan Komisariat (PK) - tingkat perguruan tinggi. '
                    'PK IMM FTIK UMKO merupakan komisariat di Universitas Muhammadiyah Kota Bumi.'
                ),
                'instruksi_ai': (
                    'Kamu adalah asisten IMM yang menjelaskan struktur organisasi IMM. '
                    'Jawab dengan ramah dan informatif dalam bahasa Indonesia.'
                ),
                'kategori': 'umum',
                'jenis_chatbot': 'umum',
            },
        ]

        created = 0
        for ds_data in datasets:
            _, was_created = DatasetChatbot.objects.get_or_create(
                intent_keyword=ds_data['intent_keyword'],
                defaults={**ds_data, 'created_by': admin},
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(f'Berhasil seed {created} entri dataset (lewati {len(datasets) - created} yang sudah ada).'))
