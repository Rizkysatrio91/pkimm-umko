"""Management command untuk mengisi data awal keperluan testing."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.berita.models import Berita
from apps.chatbot.models import DatasetChatbot
from apps.kader.models import BiodataKader


class Command(BaseCommand):
    help = 'Seed data awal untuk testing (users, dataset chatbot, berita, kader).'

    def handle(self, *args, **options):
        self.stdout.write('Seeding data...\n')

        # ── Users ────────────────────────────────────────────────
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@pkimm.com',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        if created:
            admin.set_password('admin123')
            admin.save()
            self.stdout.write(self.style.SUCCESS('  + User admin dibuat'))
        else:
            self.stdout.write('  - User admin sudah ada')

        panitia, created = User.objects.get_or_create(
            username='panitia',
            defaults={
                'email': 'panitia@pkimm.com',
                'role': 'panitia',
            },
        )
        if created:
            panitia.set_password('panitia123')
            panitia.save()
            self.stdout.write(self.style.SUCCESS('  + User panitia dibuat'))
        else:
            self.stdout.write('  - User panitia sudah ada')

        penulis, created = User.objects.get_or_create(
            username='penulis',
            defaults={
                'email': 'penulis@pkimm.com',
                'role': 'penulis',
            },
        )
        if created:
            penulis.set_password('penulis123')
            penulis.save()
            self.stdout.write(self.style.SUCCESS('  + User penulis dibuat'))
        else:
            self.stdout.write('  - User penulis sudah ada')

        # ── Dataset Chatbot Umum ─────────────────────────────────
        datasets_umum = [
            {
                'intent_keyword': 'ideologi imm, ideologi, dasar perjuangan',
                'respon_jawaban': 'Ideologi IMM berlandaskan pada Al-Quran dan As-Sunnah dengan semangat tajdid (pembaruan). IMM bergerak di tiga ranah: keagamaan, kemasyarakatan, dan kemahasiswaan.',
                'instruksi_ai': 'Jelaskan tentang ideologi dan dasar perjuangan IMM berdasarkan Al-Quran dan As-Sunnah.',
                'kategori': 'umum',
                'jenis_chatbot': 'umum',
            },
            {
                'intent_keyword': 'sejarah imm, sejarah, berdiri, kapan didirikan',
                'respon_jawaban': 'IMM (Ikatan Mahasiswa Muhammadiyah) didirikan pada 14 Maret 1964 di Yogyakarta. IMM merupakan organisasi otonom (ortom) Muhammadiyah di kalangan mahasiswa.',
                'instruksi_ai': 'Jelaskan sejarah berdirinya IMM secara singkat.',
                'kategori': 'umum',
                'jenis_chatbot': 'umum',
            },
            {
                'intent_keyword': 'struktur organisasi, struktur, ketua, pengurus',
                'respon_jawaban': 'Struktur organisasi IMM terdiri dari: Dewan Pimpinan Pusat (DPP), Dewan Pimpinan Wilayah (DPW), Dewan Pimpinan Daerah (DPD), Pimpinan Cabang (PC), dan Pimpinan Komisariat (PK).',
                'instruksi_ai': 'Jelaskan struktur organisasi IMM dari pusat hingga komisariat.',
                'kategori': 'umum',
                'jenis_chatbot': 'umum',
            },
            {
                'intent_keyword': 'tri kompetensi, tridharma, kompetensi dasar',
                'respon_jawaban': 'Tri Kompetensi Dasar IMM meliputi: (1) Religiusitas - penguatan nilai keislaman, (2) Intelektualitas - pengembangan keilmuan dan kritis, (3) Humanitas - kepedulian sosial dan kemanusiaan.',
                'instruksi_ai': 'Jelaskan Tri Kompetensi Dasar IMM beserta penjelasan masing-masing.',
                'kategori': 'umum',
                'jenis_chatbot': 'umum',
            },
            {
                'intent_keyword': 'ad art, anggaran dasar, anggaran rumah tangga',
                'respon_jawaban': 'AD/ART IMM mengatur tentang asas, tujuan, keanggotaan, struktur organisasi, musyawarah, dan ketentuan lainnya. AD/ART ditetapkan dan diubah dalam Musyawarah Nasional (MUNAS).',
                'instruksi_ai': 'Jelaskan tentang AD/ART IMM dan bagaimana penetapannya.',
                'kategori': 'umum',
                'jenis_chatbot': 'umum',
            },
        ]

        for ds_data in datasets_umum:
            _, created = DatasetChatbot.objects.get_or_create(
                intent_keyword=ds_data['intent_keyword'],
                defaults={**ds_data, 'created_by': admin, 'is_active': True},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  + Dataset umum: {ds_data["intent_keyword"][:30]}...'))

        # ── Dataset Chatbot Pendaftaran ──────────────────────────
        datasets_pendaftaran = [
            {
                'intent_keyword': 'cara daftar, daftar dad, pendaftaran, bagaimana mendaftar',
                'respon_jawaban': 'Untuk mendaftar DAD IMM UMKO: (1) Register akun di website, (2) Lengkapi biodata diri, (3) Upload KRS semester berjalan, (4) Tunggu verifikasi otomatis via OCR. Pastikan data di KRS sesuai dengan biodata yang diisi.',
                'instruksi_ai': 'Jelaskan langkah-langkah pendaftaran DAD IMM UMKO secara detail.',
                'kategori': 'pendaftaran',
                'jenis_chatbot': 'pendaftaran',
            },
            {
                'intent_keyword': 'berkas syarat, syarat pendaftaran, dokumen, persyaratan',
                'respon_jawaban': 'Berkas yang diperlukan untuk pendaftaran DAD: (1) KRS semester berjalan (format JPG/PNG, maks 5MB), (2) Biodata lengkap (NPM, nama, prodi, fakultas, dll). Pastikan foto KRS jelas dan terbaca.',
                'instruksi_ai': 'Jelaskan berkas dan syarat yang diperlukan untuk mendaftar DAD.',
                'kategori': 'pendaftaran',
                'jenis_chatbot': 'pendaftaran',
            },
            {
                'intent_keyword': 'jadwal dad, jadwal kegiatan, kapan dilaksanakan',
                'respon_jawaban': 'Jadwal DAD IMM UMKO akan diumumkan melalui website resmi dan notifikasi di dashboard. Pendaftaran dibuka setiap awal semester. Kegiatan DAD berlangsung selama 3 hari penuh.',
                'instruksi_ai': 'Jelaskan jadwal dan timeline kegiatan DAD IMM UMKO.',
                'kategori': 'pendaftaran',
                'jenis_chatbot': 'pendaftaran',
            },
        ]

        for ds_data in datasets_pendaftaran:
            _, created = DatasetChatbot.objects.get_or_create(
                intent_keyword=ds_data['intent_keyword'],
                defaults={**ds_data, 'created_by': admin, 'is_active': True},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  + Dataset pendaftaran: {ds_data["intent_keyword"][:30]}...'))

        # ── Berita ───────────────────────────────────────────────
        berita_data = [
            {
                'judul': 'Pendaftaran DAD IMM UMKO Semester Genap 2026 Dibuka',
                'slug': 'pendaftaran-dad-imm-umko-semester-genap-2026',
                'kategori': 'kampus',
                'konten_draft': 'Pimpinan Komisariat IMM UMKO membuka pendaftaran Darul Arqam Dasar (DAD) untuk semester genap tahun 2026. Pendaftaran dapat dilakukan melalui website resmi PK IMM FTIK UMKO. Calon peserta wajib mengisi biodata lengkap dan mengupload KRS semester berjalan.',
                'konten_final': 'Pimpinan Komisariat IMM UMKO membuka pendaftaran Darul Arqam Dasar (DAD) untuk semester genap tahun 2026. Pendaftaran dapat dilakukan melalui website resmi PK IMM FTIK UMKO. Calon peserta wajib mengisi biodata lengkap dan mengunggah KRS semester berjalan. Verifikasi berkas dilakukan secara otomatis menggunakan teknologi OCR.',
                'status': 'published',
                'tgl_terbit': timezone.now(),
            },
            {
                'judul': 'Kegiatan Kajian Rutin IMM UMKO: Membangun Intelektualitas Kader',
                'slug': 'kegiatan-kajian-rutin-imm-umko',
                'kategori': 'akademik',
                'konten_draft': 'IMM UMKO mengadakan kajian rutin setiap pekan sebagai upaya meningkatkan kapasitas intelektual kader. Kajian membahas berbagai topik dari keislaman, kemuhammadiyahan, hingga isu-isu kontemporer.',
                'konten_final': 'IMM UMKO mengadakan kajian rutin setiap pekan sebagai upaya meningkatkan kapasitas intelektual kader. Kajian membahas berbagai topik dari keislaman, kemuhammadiyahan, hingga isu-isu kontemporer. Kegiatan ini terbuka untuk seluruh mahasiswa UMKO.',
                'status': 'published',
                'tgl_terbit': timezone.now(),
            },
            {
                'judul': 'IMM UMKO Raih Penghargaan di Jambore Nasional Muhammadiyah',
                'slug': 'imm-umko-raih-penghargaan-jambore-nasional',
                'kategori': 'mahasiswa',
                'konten_draft': 'Delegasi IMM UMKO berhasil meraih penghargaan dalam Jambore Nasional Muhammadiyah yang diselenggarakan di Jakarta. Prestasi ini menunjukkan kualitas kader IMM UMKO di tingkat nasional.',
                'konten_final': 'Delegasi IMM UMKO berhasil meraih penghargaan dalam Jambore Nasional Muhammadiyah yang diselenggarakan di Jakarta. Prestasi ini menunjukkan kualitas kader IMM UMKO di tingkat nasional. Ketua PK IMM FTIK UMKO mengapresiasi dedikasi seluruh anggota yang telah berkontribusi.',
                'status': 'published',
                'tgl_terbit': timezone.now(),
            },
        ]

        for b_data in berita_data:
            _, created = Berita.objects.get_or_create(
                slug=b_data['slug'],
                defaults={**b_data, 'id_penulis': penulis},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  + Berita: {b_data["judul"][:40]}...'))

        # ── Data Kader Contoh ────────────────────────────────────
        kader_data = [
            {
                'npm': '2259201001',
                'nama_lengkap': 'Ahmad Fauzi',
                'program_studi': 'Sistem dan Teknologi Informasi',
                'fakultas': 'FTIK',
                'angkatan': '2022',
                'jenis_kelamin': 'L',
                'tempat_lahir': 'Kotabumi',
                'jabatan_struktural': 'kader',
            },
            {
                'npm': '2259201002',
                'nama_lengkap': 'Siti Aisyah',
                'program_studi': 'Teknik Informatika',
                'fakultas': 'FTIK',
                'angkatan': '2022',
                'jenis_kelamin': 'P',
                'tempat_lahir': 'Lampung Utara',
                'jabatan_struktural': 'kader',
            },
            {
                'npm': '2259201003',
                'nama_lengkap': 'Muhammad Rizki',
                'program_studi': 'Sistem dan Teknologi Informasi',
                'fakultas': 'FTIK',
                'angkatan': '2023',
                'jenis_kelamin': 'L',
                'tempat_lahir': 'Bandar Lampung',
                'jabatan_struktural': 'kader',
            },
        ]

        for k_data in kader_data:
            _, created = BiodataKader.objects.get_or_create(
                npm=k_data['npm'],
                defaults=k_data,
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  + Kader: {k_data["nama_lengkap"]}'))

        self.stdout.write(self.style.SUCCESS('\nSeed data selesai!'))
