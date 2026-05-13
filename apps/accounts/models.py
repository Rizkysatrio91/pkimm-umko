"""Model User dengan akses berbasis role dan dukungan OTP."""
import random
import string
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

from core.constants import UserRole


class UserManager(BaseUserManager):
    """Manager kustom untuk model User."""

    def create_user(
        self,
        username: str,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> 'User':
        """Buat dan kembalikan user biasa."""
        if not email:
            raise ValueError('Email harus diisi.')
        if not username:
            raise ValueError('Username harus diisi.')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        username: str,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> 'User':
        """Buat dan kembalikan superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.ADMIN)
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """Model user kustom dengan field role dan OTP (Skripsi Tabel 3.1)."""

    id_user = models.AutoField(primary_key=True)
    password = models.CharField(max_length=128, db_column='password_hash')
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(max_length=100, unique=True)
    role = models.CharField(
        max_length=15,
        choices=UserRole.choices,
        default=UserRole.CALON_KADER,
    )
    is_active = models.BooleanField(default=True)
    foto_profil = models.ImageField(upload_to='profil/', blank=True, null=True)
    otp_token = models.CharField(max_length=6, null=True, blank=True)
    otp_expired_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"

    def generate_otp(self) -> str:
        """Buat OTP 6 digit dan set waktu kedaluarsa 10 menit."""
        self.otp_token = ''.join(random.choices(string.digits, k=6))
        self.otp_expired_at = timezone.now() + timedelta(minutes=10)
        self.save(update_fields=['otp_token', 'otp_expired_at'])
        return self.otp_token

    def check_otp(self, otp: str) -> str:
        """
        Cek OTP dan kembalikan string status:
        'valid'   — cocok dan belum kedaluarsa
        'expired' — cocok tapi sudah kedaluarsa
        'invalid' — kode salah atau belum pernah generate OTP
        """
        if not self.otp_token or not self.otp_expired_at:
            return 'invalid'
        if self.otp_token != otp.strip():
            return 'invalid'
        if timezone.now() >= self.otp_expired_at:
            return 'expired'
        return 'valid'

    def is_otp_valid(self, otp: str) -> bool:
        """Cek apakah OTP yang diberikan cocok dan belum kedaluarsa."""
        return self.check_otp(otp) == 'valid'

    def clear_otp(self) -> None:
        """Hapus OTP token dan waktu kedaluarsanya."""
        self.otp_token = None
        self.otp_expired_at = None
        self.save(update_fields=['otp_token', 'otp_expired_at'])


class AuditLog(models.Model):
    """Catatan audit aksi sensitif (lookup data SSO mahasiswa, dll).

    Tabel append-only: tidak ada UI untuk delete/edit. Tujuan:
      - Akuntabilitas: siapa admin yang mengakses data mahasiswa mana, kapan
      - Bukti forensik bila terjadi insiden kebocoran data
      - Deteksi pola enumerasi NPM yang tidak normal

    Field id_user nullable supaya event sistem (mis. percobaan akses tanpa
    login) tetap bisa dicatat tanpa FK orphan.
    """

    ACTION_SSO_LOOKUP = 'sso_lookup'
    ACTION_CHOICES = [
        (ACTION_SSO_LOOKUP, 'Lookup data mahasiswa via SSO UMKO'),
    ]

    id_audit = models.AutoField(primary_key=True)
    id_user = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='id_user',
        related_name='audit_logs',
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    target = models.CharField(
        max_length=200,
        blank=True,
        help_text='Detail target aksi, mis. "npm=2259201005"',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Log'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['id_user', '-created_at']),
        ]

    def __str__(self) -> str:
        who = self.id_user.username if self.id_user_id else 'anonymous'
        ts = self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '-'
        return f'[{ts}] {who} → {self.action} ({self.target})'
