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
