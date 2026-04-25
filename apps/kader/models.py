"""Model BiodataKader (Skripsi Tabel 3.2)."""
from django.conf import settings
from django.db import models

from core.constants import JabatanKader, JenisKelamin


class Fakultas(models.Model):
    """Data fakultas di universitas."""

    id_fakultas = models.AutoField(primary_key=True)
    nama_fakultas = models.CharField(max_length=100, unique=True)
    kode_fakultas = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'fakultas'
        ordering = ['nama_fakultas']

    def __str__(self):
        return self.nama_fakultas


class ProgramStudi(models.Model):
    """Data program studi per fakultas."""

    id_prodi = models.AutoField(primary_key=True)
    fakultas = models.ForeignKey(
        Fakultas,
        on_delete=models.CASCADE,
        db_column='id_fakultas',
        related_name='prodi_list',
    )
    nama_prodi = models.CharField(max_length=100)
    kode_prodi = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'program_studi'
        ordering = ['nama_prodi']

    def __str__(self):
        return f"{self.nama_prodi} - {self.fakultas.nama_fakultas}"


class KonfigurasiSistem(models.Model):
    """Konfigurasi sistem untuk pendaftaran (singleton).

    Menyimpan fakultas yang diizinkan untuk registrasi akun dan pendaftaran DAD.
    API SSO UMKO tidak mengekspos relasi prodi→fakultas, sehingga admin memilih
    fakultas sekaligus centang prodi mana saja yang termasuk fakultas tersebut.

    Catatan: data billing OpenAI (biaya + token) diambil realtime dari
    OpenAI Admin API — lihat core.services.OpenAIBillingService.
    """

    id_konfigurasi = models.AutoField(primary_key=True)
    sso_id_fakultas = models.IntegerField(null=True, blank=True)
    sso_kode_fakultas = models.CharField(max_length=20, blank=True, default='')
    sso_nama_fakultas = models.CharField(max_length=150, blank=True, default='')
    allowed_prodi_codes = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'konfigurasi_sistem'
        verbose_name = 'Konfigurasi Sistem'
        verbose_name_plural = 'Konfigurasi Sistem'

    def __str__(self) -> str:
        return self.sso_nama_fakultas or 'Belum dikonfigurasi'

    @classmethod
    def get_instance(cls) -> 'KonfigurasiSistem':
        """Return singleton — buat jika belum ada."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def is_prodi_allowed(self, id_program_studi: str) -> bool:
        """Cek apakah sebuah id_program_studi diizinkan mendaftar."""
        if not self.allowed_prodi_codes:
            return False
        return str(id_program_studi) in [str(x) for x in self.allowed_prodi_codes]


class BiodataKader(models.Model):
    """Biodata lengkap kader dan calon kader IMM."""

    id_biodata = models.AutoField(primary_key=True)
    id_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='id_user',
        related_name='biodata',
    )
    npm = models.CharField(max_length=20, unique=True)
    nama_lengkap = models.CharField(max_length=100)
    program_studi = models.CharField(max_length=50)
    fakultas = models.CharField(max_length=50)
    angkatan = models.CharField(max_length=4)
    tempat_lahir = models.CharField(max_length=50, blank=True, default='')
    tgl_lahir = models.DateField(null=True, blank=True)
    jenis_kelamin = models.CharField(
        max_length=1,
        choices=JenisKelamin.choices,
        blank=True,
        default='',
    )
    alamat_domisili = models.TextField(blank=True, default='')
    no_hp = models.CharField(max_length=15, blank=True, default='')
    nama_ayah = models.CharField(max_length=100, blank=True, default='')
    nama_ibu = models.CharField(max_length=100, blank=True, default='')
    no_hp_ortu = models.CharField(max_length=15, blank=True, default='')
    jabatan_struktural = models.CharField(
        max_length=50,
        choices=JabatanKader.choices,
        default=JabatanKader.CALON,
    )
    periode_jabatan = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text='Contoh: 2024-2025',
    )
    foto_profil = models.ImageField(upload_to='profil/', blank=True)
    is_biodata_complete = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'biodata_kader'
        verbose_name = 'Biodata Kader'
        verbose_name_plural = 'Biodata Kader'
        ordering = ['nama_lengkap']

    def __str__(self) -> str:
        return f"{self.npm} - {self.nama_lengkap}"

    def check_completeness(self) -> bool:
        """Periksa apakah semua field wajib terisi, perbarui is_biodata_complete."""
        required_fields = [
            self.npm, self.nama_lengkap, self.program_studi,
            self.fakultas, self.angkatan, self.tempat_lahir,
            self.tgl_lahir, self.jenis_kelamin, self.alamat_domisili,
            self.no_hp, self.nama_ayah, self.nama_ibu, self.no_hp_ortu,
        ]
        is_complete = all(required_fields)
        if self.is_biodata_complete != is_complete:
            self.is_biodata_complete = is_complete
            self.save(update_fields=['is_biodata_complete'])
        return is_complete
