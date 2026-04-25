"""PendaftaranDAD model (Skripsi Tabel 3.3) + Kelompok, Rundown, QR Absensi."""
import random
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.kader.models import BiodataKader
from core.constants import NamaKelompok, StatusAbsensi, StatusInterview, StatusKelulusan, StatusVerifikasi


class PeriodeDAD(models.Model):
    """Periode kegiatan Darul Arqam Dasar dengan jadwal per tahap."""

    id_periode = models.AutoField(primary_key=True)
    nama_periode = models.CharField(max_length=100)

    # Tahap 1: Administrasi Pendaftaran
    tgl_buka_administrasi = models.DateTimeField()
    tgl_tutup_administrasi = models.DateTimeField()

    # Tahap 2: Seleksi Interview
    tgl_mulai_interview = models.DateTimeField(null=True, blank=True)
    tgl_selesai_interview = models.DateTimeField(null=True, blank=True)

    # Tahap 3: Kegiatan DAD (3 hari)
    tgl_mulai_kegiatan = models.DateTimeField(null=True, blank=True)
    tgl_selesai_kegiatan = models.DateTimeField(null=True, blank=True)

    # Tahap 4: Pengumuman Kelulusan
    tgl_pengumuman_kelulusan = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'periode_dad'
        verbose_name = 'Periode DAD'
        verbose_name_plural = 'Periode DAD'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.nama_periode} ({self.info_tahap['label']})"

    @property
    def tahap_saat_ini(self) -> str:
        """Return tahap yang sedang berjalan berdasarkan tanggal sekarang."""
        now = timezone.now()
        if not self.is_active:
            return 'nonaktif'
        if now < self.tgl_buka_administrasi:
            return 'belum_dimulai'
        if self.tgl_buka_administrasi <= now <= self.tgl_tutup_administrasi:
            return 'administrasi'
        if self.tgl_mulai_interview and self.tgl_selesai_interview:
            if self.tgl_mulai_interview <= now <= self.tgl_selesai_interview:
                return 'interview'
        if self.tgl_mulai_kegiatan and self.tgl_selesai_kegiatan:
            if self.tgl_mulai_kegiatan <= now <= self.tgl_selesai_kegiatan:
                return 'kegiatan_dad'
        if self.tgl_pengumuman_kelulusan and now >= self.tgl_pengumuman_kelulusan:
            return 'pengumuman'
        return 'jeda_antar_tahap'

    @property
    def info_tahap(self) -> dict:
        """Return dict info tahap saat ini untuk ditampilkan ke user."""
        tahap = self.tahap_saat_ini
        info = {
            'nonaktif': {'label': 'Nonaktif', 'warna': 'gray'},
            'belum_dimulai': {'label': 'Belum Dimulai', 'warna': 'gray'},
            'administrasi': {'label': 'Tahap 1: Pendaftaran Administrasi', 'warna': 'green'},
            'interview': {'label': 'Tahap 2: Seleksi Interview', 'warna': 'blue'},
            'kegiatan_dad': {'label': 'Tahap 3: Kegiatan DAD', 'warna': 'purple'},
            'pengumuman': {'label': 'Tahap 4: Pengumuman Kelulusan', 'warna': 'gold'},
            'jeda_antar_tahap': {'label': 'Jeda Antar Tahap', 'warna': 'yellow'},
        }
        return info.get(tahap, info['nonaktif'])

    @property
    def is_open(self) -> bool:
        """Periksa apakah pendaftaran (administrasi) sedang dibuka."""
        return self.tahap_saat_ini == 'administrasi'

    @classmethod
    def get_active_period(cls):
        """Ambil periode yang sedang aktif, atau None."""
        return cls.objects.filter(is_active=True).first()


class PendaftaranDAD(models.Model):
    """Pendaftaran Darul Arqam Dasar (DAD)."""

    id_pendaftaran = models.AutoField(primary_key=True)
    id_periode = models.ForeignKey(
        PeriodeDAD,
        on_delete=models.SET_NULL,
        db_column='id_periode',
        related_name='pendaftaran_set',
        null=True,
        blank=True,
    )
    id_biodata = models.OneToOneField(
        BiodataKader,
        on_delete=models.CASCADE,
        db_column='id_biodata',
        related_name='pendaftaran',
    )
    no_registrasi = models.CharField(max_length=20, unique=True, blank=True)
    api_nama_sso = models.CharField(max_length=200, null=True, blank=True)
    api_status_mahasiswa = models.CharField(max_length=50, null=True, blank=True)
    api_program_studi = models.CharField(max_length=100, null=True, blank=True)
    is_identic = models.BooleanField(default=False)
    status_verifikasi = models.CharField(
        max_length=30,
        choices=StatusVerifikasi.choices,
        default=StatusVerifikasi.MENUNGGU,
    )
    status_kelulusan = models.CharField(
        max_length=20,
        choices=StatusKelulusan.choices,
        default=StatusKelulusan.BELUM,
    )
    id_kelompok = models.ForeignKey(
        'KelompokDAD',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_kelompok',
        related_name='anggota_set',
    )
    tgl_daftar = models.DateTimeField(auto_now_add=True)
    tgl_verifikasi = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'pendaftaran_dad'
        verbose_name = 'Pendaftaran DAD'
        verbose_name_plural = 'Pendaftaran DAD'
        ordering = ['-tgl_daftar']

    def __str__(self) -> str:
        return f"{self.no_registrasi} - {self.id_biodata.nama_lengkap}"

    def generate_no_registrasi(self) -> str:
        """Generate nomor registrasi unik: REG-{tahun}-{4 digit acak}."""
        year = timezone.now().year
        while True:
            rand = random.randint(1000, 9999)
            no_reg = f"REG-{year}-{rand}"
            if not PendaftaranDAD.objects.filter(no_registrasi=no_reg).exists():
                return no_reg

    def validasi_identitas(self) -> None:
        """
        Validasi identitas dengan membandingkan data dari API SSO
        dengan data biodata kader.
        """
        if not self.api_nama_sso:
            self.is_identic = False
            self.status_verifikasi = StatusVerifikasi.DITOLAK
            return

        nama_sso = self.api_nama_sso.strip().lower()
        nama_biodata = self.id_biodata.nama_lengkap.strip().lower()

        # NPM sudah pasti cocok karena kita query by_nim dari NPM biodata
        # Yang perlu dicek adalah apakah nama cocok
        if nama_sso == nama_biodata:
            self.is_identic = True
            self.status_verifikasi = StatusVerifikasi.LOLOS
        else:
            self.is_identic = False
            self.status_verifikasi = StatusVerifikasi.DITOLAK

    def save(self, *args, **kwargs) -> None:
        """Generate otomatis no_registrasi saat pertama kali dibuat."""
        if not self.no_registrasi:
            self.no_registrasi = self.generate_no_registrasi()
        super().save(*args, **kwargs)

    # ─── Tahap progress calon kader (otomatis dari data turunan) ────────────
    TAHAP_CODES = (
        ('menunggu_verifikasi', 'Menunggu Verifikasi'),
        ('ditolak_administrasi', 'Ditolak Administrasi'),
        ('lolos_administrasi', 'Lolos Administrasi'),
        ('lolos_interview', 'Lolos Interview'),
        ('gagal_interview', 'Gagal Interview'),
        ('aktivitas_dad', 'Aktivitas DAD Berjalan'),
        ('lulus_dad', 'Lulus DAD'),
        ('tidak_lulus_dad', 'Tidak Lulus DAD'),
    )

    @property
    def tahap_display(self) -> dict:
        """Status progress calon kader — diturunkan otomatis dari data terkait.

        Urutan tahap (naik):
            Menunggu Verifikasi → Lolos/Ditolak Administrasi →
            Lolos/Gagal Interview → Aktivitas DAD Berjalan →
            Lulus/Tidak Lulus DAD
        """
        # Tahap final dari penetapan kelulusan — override semua tahap sebelumnya
        if self.status_kelulusan == StatusKelulusan.LULUS:
            return {'code': 'lulus_dad', 'label': 'Lulus DAD', 'color': 'gold'}
        if self.status_kelulusan == StatusKelulusan.TIDAK_LULUS:
            return {'code': 'tidak_lulus_dad', 'label': 'Tidak Lulus DAD', 'color': 'red'}

        # Tahap administrasi
        if self.status_verifikasi == StatusVerifikasi.MENUNGGU:
            return {'code': 'menunggu_verifikasi', 'label': 'Menunggu Verifikasi', 'color': 'yellow'}
        if self.status_verifikasi == StatusVerifikasi.DITOLAK:
            return {'code': 'ditolak_administrasi', 'label': 'Ditolak Administrasi', 'color': 'red'}

        # Setelah lolos admin — cek data aktivitas & interview (tanpa extra query
        # kalau sudah di-prefetch)
        has_aktivitas = any(True for _ in self.nilai_aktivitas_set.all())
        interview = next(iter(self.nilai_interview_set.all()), None)

        if has_aktivitas:
            return {'code': 'aktivitas_dad', 'label': 'Aktivitas DAD Berjalan', 'color': 'blue'}

        if interview is not None:
            if interview.status_interview == StatusInterview.LULUS:
                return {'code': 'lolos_interview', 'label': 'Lolos Interview', 'color': 'green'}
            if interview.status_interview == StatusInterview.GAGAL:
                return {'code': 'gagal_interview', 'label': 'Gagal Interview', 'color': 'red'}

        return {'code': 'lolos_administrasi', 'label': 'Lolos Administrasi', 'color': 'green'}


# ═══════════════════════════════════════════════════════════════════════════════
# Kelompok DAD (A, B, C)
# ═══════════════════════════════════════════════════════════════════════════════

class KelompokDAD(models.Model):
    """Kelompok/kelas DAD (A, B, C) dengan PJ panitia per kelompok."""

    id_kelompok = models.AutoField(primary_key=True)
    id_periode = models.ForeignKey(
        PeriodeDAD,
        on_delete=models.CASCADE,
        db_column='id_periode',
        related_name='kelompok_set',
    )
    nama_kelompok = models.CharField(
        max_length=1,
        choices=NamaKelompok.choices,
    )
    id_pj = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_pj',
        related_name='kelompok_pj_set',
    )

    class Meta:
        db_table = 'kelompok_dad'
        verbose_name = 'Kelompok DAD'
        verbose_name_plural = 'Kelompok DAD'
        unique_together = [('id_periode', 'nama_kelompok')]
        ordering = ['nama_kelompok']

    def __str__(self) -> str:
        return f"Kelas {self.nama_kelompok} — {self.id_periode.nama_periode}"

    @property
    def jumlah_anggota(self) -> int:
        return self.anggota_set.count()


# ═══════════════════════════════════════════════════════════════════════════════
# Rundown DAD
# ═══════════════════════════════════════════════════════════════════════════════

class RundownDAD(models.Model):
    """Sesi/acara dalam rundown kegiatan DAD."""

    id_rundown = models.AutoField(primary_key=True)
    id_periode = models.ForeignKey(
        PeriodeDAD,
        on_delete=models.CASCADE,
        db_column='id_periode',
        related_name='rundown_set',
    )
    hari_ke = models.CharField(
        max_length=30,
        help_text='Label hari. Contoh: "Kedatangan", "Hari 1", "Hari 2", "Hari 3".',
    )
    tanggal = models.DateField()
    jam_mulai = models.TimeField()
    jam_selesai = models.TimeField()
    materi = models.CharField(max_length=255)
    pemateri_a = models.CharField(max_length=150, blank=True, default='')
    pemateri_b = models.CharField(max_length=150, blank=True, default='')
    pemateri_c = models.CharField(max_length=150, blank=True, default='')
    pj_a = models.CharField(max_length=150, blank=True, default='')
    pj_b = models.CharField(max_length=150, blank=True, default='')
    pj_c = models.CharField(max_length=150, blank=True, default='')
    is_absensi = models.BooleanField(
        default=False,
        help_text='Apakah sesi ini memerlukan absensi via QR',
    )
    urutan = models.SmallIntegerField(default=0)

    class Meta:
        db_table = 'rundown_dad'
        verbose_name = 'Rundown DAD'
        verbose_name_plural = 'Rundown DAD'
        ordering = ['hari_ke', 'urutan', 'jam_mulai']

    def __str__(self) -> str:
        return f"Hari {self.hari_ke} — {self.materi} ({self.jam_mulai.strftime('%H:%M')})"


# ═══════════════════════════════════════════════════════════════════════════════
# QR Absensi
# ═══════════════════════════════════════════════════════════════════════════════

class QRAbsensi(models.Model):
    """Token QR unik per sesi rundown per kelompok untuk absensi."""

    id_qr = models.AutoField(primary_key=True)
    id_rundown = models.ForeignKey(
        RundownDAD,
        on_delete=models.CASCADE,
        db_column='id_rundown',
        related_name='qr_set',
    )
    id_kelompok = models.ForeignKey(
        KelompokDAD,
        on_delete=models.CASCADE,
        db_column='id_kelompok',
        related_name='qr_set',
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'qr_absensi'
        verbose_name = 'QR Absensi'
        verbose_name_plural = 'QR Absensi'
        unique_together = [('id_rundown', 'id_kelompok')]

    def __str__(self) -> str:
        return f"QR Kelas {self.id_kelompok.nama_kelompok} — {self.id_rundown.materi}"

    def activate(self) -> None:
        """Aktifkan QR code dan regenerate token untuk keamanan."""
        self.is_active = True
        self.activated_at = timezone.now()
        self.token = uuid.uuid4()
        self.save(update_fields=['is_active', 'activated_at', 'token'])

    def deactivate(self) -> None:
        """Nonaktifkan QR code setelah sesi selesai."""
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.save(update_fields=['is_active', 'deactivated_at'])


# ═══════════════════════════════════════════════════════════════════════════════
# Absensi DAD
# ═══════════════════════════════════════════════════════════════════════════════

class AbsensiDAD(models.Model):
    """Rekam kehadiran peserta per sesi.

    Aturan perhitungan poin kedisiplinan (lihat ``apps.penilaian.services``):
      - status HADIR          → 100 poin
      - status IZIN / SAKIT   → 60 poin
      - status ALPHA / no row → 0 poin

    Row dengan status HADIR selalu punya ``waktu_scan`` (dari scan QR).
    Row dengan status IZIN/SAKIT/ALPHA di-input manual oleh panitia
    dan ``waktu_scan`` dibiarkan NULL.
    """

    id_absensi = models.AutoField(primary_key=True)
    id_pendaftaran = models.ForeignKey(
        PendaftaranDAD,
        on_delete=models.CASCADE,
        db_column='id_pendaftaran',
        related_name='absensi_set',
    )
    id_qr = models.ForeignKey(
        QRAbsensi,
        on_delete=models.CASCADE,
        db_column='id_qr',
        related_name='absensi_set',
    )
    waktu_scan = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=StatusAbsensi.choices,
        default=StatusAbsensi.HADIR,
    )
    keterangan = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'absensi_dad'
        verbose_name = 'Absensi DAD'
        verbose_name_plural = 'Absensi DAD'
        unique_together = [('id_pendaftaran', 'id_qr')]
        ordering = ['-waktu_scan']

    def __str__(self) -> str:
        return f"Absensi {self.id_pendaftaran} — {self.id_qr.id_rundown.materi} [{self.get_status_display()}]"
