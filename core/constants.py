"""Semua konstanta TextChoices untuk proyek ini."""
from django.db import models


class UserRole(models.TextChoices):
    """Pilihan role untuk model User."""
    ADMIN = 'admin', 'Admin'
    PANITIA = 'panitia', 'Panitia/Instruktur'
    PENULIS = 'penulis', 'Penulis'
    CALON_KADER = 'calon_kader', 'Calon Kader'


class JenisKelamin(models.TextChoices):
    """Pilihan jenis kelamin."""
    LAKI = 'L', 'Laki-laki'
    PEREMPUAN = 'P', 'Perempuan'


class StatusVerifikasi(models.TextChoices):
    """Status verifikasi untuk pendaftaran DAD."""
    MENUNGGU = 'menunggu', 'Menunggu'
    LOLOS = 'lolos_administrasi', 'Lolos Administrasi'
    DITOLAK = 'ditolak', 'Ditolak'


class StatusKelulusan(models.TextChoices):
    """Status kelulusan."""
    BELUM = 'belum_ditentukan', 'Belum Ditentukan'
    LULUS = 'lulus', 'Lulus'
    TIDAK_LULUS = 'tidak_lulus', 'Tidak Lulus'


class StatusInterview(models.TextChoices):
    """Status hasil interview."""
    LULUS = 'lulus_interview', 'Lulus Interview'
    GAGAL = 'gagal_interview', 'Gagal Interview'


class StatusBerita(models.TextChoices):
    """Status artikel berita."""
    DRAFT = 'draft', 'Draft'
    PUBLISHED = 'published', 'Published'


class KategoriBerita(models.TextChoices):
    """Pilihan kategori berita."""
    KAMPUS = 'kampus', 'Kampus'
    AKADEMIK = 'akademik', 'Akademik'
    MAHASISWA = 'mahasiswa', 'Mahasiswa'
    EVENT = 'event', 'Event'


class JenisChatbot(models.TextChoices):
    """Pilihan tipe chatbot."""
    UMUM = 'umum', 'Umum (Publik)'
    PENDAFTARAN = 'pendaftaran', 'Pendaftaran (Dashboard)'


class KategoriDataset(models.TextChoices):
    """Pilihan kategori dataset."""
    UMUM = 'umum', 'Umum'
    PENDAFTARAN = 'pendaftaran', 'Pendaftaran'
    KELULUSAN = 'kelulusan', 'Kelulusan'
    TEKNIS = 'teknis', 'Teknis'


class JabatanKader(models.TextChoices):
    """Pilihan jabatan struktural."""
    CALON = 'calon', 'Calon Kader'
    KADER = 'kader', 'Kader'
    # Pimpinan Inti
    KETUA_UMUM = 'ketua_umum', 'Ketua Umum'
    SEKRETARIS_UMUM = 'sekretaris_umum', 'Sekretaris Umum'
    BENDAHARA_UMUM = 'bendahara_umum', 'Bendahara Umum'
    # Bidang Organisasi
    KETUA_BID_ORGANISASI = 'ketua_bid_organisasi', 'Ketua Bidang Organisasi'
    SEKRETARIS_BID_ORGANISASI = 'sekretaris_bid_organisasi', 'Sekretaris Bidang Organisasi'
    # Bidang Kaderisasi
    KETUA_BID_KADERISASI = 'ketua_bid_kaderisasi', 'Ketua Bidang Kaderisasi'
    SEKRETARIS_BID_KADERISASI = 'sekretaris_bid_kaderisasi', 'Sekretaris Bidang Kaderisasi'
    # Bidang Riset dan Teknologi
    KETUA_BID_RISTEK = 'ketua_bid_ristek', 'Ketua Bidang Riset dan Teknologi'
    SEKRETARIS_BID_RISTEK = 'sekretaris_bid_ristek', 'Sekretaris Bidang Riset dan Teknologi'
    # Bidang Kajian dan Keislaman
    KETUA_BID_KAJIAN = 'ketua_bid_kajian', 'Ketua Bidang Kajian dan Keislaman'
    SEKRETARIS_BID_KAJIAN = 'sekretaris_bid_kajian', 'Sekretaris Bidang Kajian dan Keislaman'
    # Bidang Hikmah dan Kebijakan Publik
    KETUA_BID_HIKMAH = 'ketua_bid_hikmah', 'Ketua Bidang Hikmah dan Kebijakan Publik'
    SEKRETARIS_BID_HIKMAH = 'sekretaris_bid_hikmah', 'Sekretaris Bidang Hikmah dan Kebijakan Publik'
    # Bidang Imawati
    KETUA_BID_IMAWATI = 'ketua_bid_imawati', 'Ketua Bidang Imawati'
    SEKRETARIS_BID_IMAWATI = 'sekretaris_bid_imawati', 'Sekretaris Bidang Imawati'
    # Bidang Media dan Komunikasi
    KETUA_BID_MEDKOM = 'ketua_bid_medkom', 'Ketua Bidang Media dan Komunikasi'
    SEKRETARIS_BID_MEDKOM = 'sekretaris_bid_medkom', 'Sekretaris Bidang Media dan Komunikasi'
    # Bidang Sosial dan Pemberdayaan Masyarakat
    KETUA_BID_SOSIAL = 'ketua_bid_sosial', 'Ketua Bidang Sosial dan Pemberdayaan Masyarakat'
    SEKRETARIS_BID_SOSIAL = 'sekretaris_bid_sosial', 'Sekretaris Bidang Sosial dan Pemberdayaan Masyarakat'
    # Bidang Lingkungan Hidup
    KETUA_BID_LH = 'ketua_bid_lh', 'Ketua Bidang Lingkungan Hidup'
    SEKRETARIS_BID_LH = 'sekretaris_bid_lh', 'Sekretaris Bidang Lingkungan Hidup'
    # Bidang Ekonomi dan Kewirausahaan
    KETUA_BID_EKONOMI = 'ketua_bid_ekonomi', 'Ketua Bidang Ekonomi dan Kewirausahaan'
    SEKRETARIS_BID_EKONOMI = 'sekretaris_bid_ekonomi', 'Sekretaris Bidang Ekonomi dan Kewirausahaan'
    # Bidang Kepemudaan dan Olahraga
    KETUA_BID_PEMUDA = 'ketua_bid_pemuda', 'Ketua Bidang Kepemudaan dan Olahraga'
    SEKRETARIS_BID_PEMUDA = 'sekretaris_bid_pemuda', 'Sekretaris Bidang Kepemudaan dan Olahraga'


class NamaKelompok(models.TextChoices):
    """Pilihan kelompok/kelas DAD."""
    A = 'A', 'Kelas A'
    B = 'B', 'Kelas B'
    C = 'C', 'Kelas C'


class StatusPeriode(models.TextChoices):
    """Status periode pendaftaran."""
    DIBUKA = 'dibuka', 'Dibuka'
    DITUTUP = 'ditutup', 'Ditutup'
    BELUM_DIBUKA = 'belum_dibuka', 'Belum Dibuka'


class TipeNotifikasi(models.TextChoices):
    """Pilihan tipe notifikasi."""
    STATUS_OCR = 'status_ocr', 'Status OCR (Legacy)'
    STATUS_VERIFIKASI = 'status_verifikasi', 'Status Verifikasi'
    STATUS_KELULUSAN = 'status_kelulusan', 'Status Kelulusan'
    CHATBOT = 'chatbot', 'Chatbot'


class StatusAbsensi(models.TextChoices):
    """Status kehadiran peserta untuk satu sesi absensi DAD.

    Digunakan oleh model AbsensiDAD untuk membedakan apakah row
    berasal dari scan QR (HADIR), input manual panitia (IZIN / SAKIT),
    atau tidak hadir tanpa keterangan (ALPHA — row tetap ada agar
    perhitungan poin kedisiplinan tidak perlu query ganda).
    """
    HADIR = 'hadir', 'Hadir'
    IZIN = 'izin', 'Izin'
    SAKIT = 'sakit', 'Sakit'
    ALPHA = 'alpha', 'Alpha'
