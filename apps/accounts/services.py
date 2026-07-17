"""Service layer untuk app accounts."""
import logging
import secrets
import string

from django.conf import settings
from django.core.mail import send_mail

from apps.accounts.models import User

logger = logging.getLogger(__name__)


class OTPService:
    """Service untuk pembuatan OTP dan pengiriman email."""

    @staticmethod
    def generate_code() -> str:
        """Buat kode OTP 6 digit memakai CSPRNG (bukan random biasa).

        Dipakai oleh alur pendaftaran yang belum punya record User (OTP disimpan
        sementara di session dalam bentuk hash), berbeda dari User.generate_otp()
        yang menyimpan OTP pada record user untuk reset password.
        """
        return ''.join(secrets.choice(string.digits) for _ in range(6))

    @staticmethod
    def send_registration_otp(email: str, code: str, username: str) -> bool:
        """Kirim OTP verifikasi pendaftaran ke email KAMPUS mahasiswa.

        Tujuan: membuktikan pendaftar benar-benar pemilik NPM tersebut, karena
        hanya pemilik mailbox @umko.ac.id yang bisa membaca kodenya.
        """
        subject = 'Verifikasi Pendaftaran Akun - PK IMM FTIK UMKO'
        message = (
            f'Halo {username},\n\n'
            f'Kode verifikasi pendaftaran akun Anda:\n\n'
            f'    {code}\n\n'
            f'Kode ini berlaku selama 10 menit dan dikirim ke email kampus Anda\n'
            f'untuk memastikan Anda adalah pemilik NPM yang didaftarkan.\n\n'
            f'Jika Anda tidak merasa mendaftar akun di sistem PK IMM FTIK UMKO,\n'
            f'abaikan email ini — akun tidak akan dibuat tanpa kode ini.\n\n'
            f'Salam,\nTim PK IMM FTIK UMKO'
        )
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            return True
        except Exception:
            logger.exception('Gagal mengirim OTP pendaftaran ke %s', email)
            return False

    @staticmethod
    def send_otp_email(user: User) -> bool:
        """Buat OTP dan kirim ke email user."""
        from django.utils import timezone
        otp = user.generate_otp()
        # Tampilkan waktu kedaluarsa dalam WIB (UTC+7)
        from datetime import timezone as dt_tz, timedelta
        wib_offset = timedelta(hours=7)
        expired_wib = user.otp_expired_at.astimezone(dt_tz(wib_offset))
        expired_str = expired_wib.strftime('%H:%M WIB')
        subject = 'Reset Password - PK IMM FTIK UMKO'
        message = (
            f'Halo {user.username},\n\n'
            f'Kode OTP untuk reset password Anda:\n\n'
            f'    {otp}\n\n'
            f'Kode ini berlaku selama 10 menit (kedaluarsa pukul {expired_str}).\n\n'
            f'PENTING: Jika Anda menerima beberapa email OTP, gunakan HANYA kode\n'
            f'dari email TERBARU ini. Kode lama otomatis tidak berlaku.\n\n'
            f'Jika Anda tidak meminta reset password, abaikan email ini.\n\n'
            f'Salam,\nTim PK IMM FTIK UMKO'
        )
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            return True
        except Exception:
            logger.exception('Gagal mengirim email OTP ke %s', user.email)
            return False
