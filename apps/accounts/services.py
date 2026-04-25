"""Service layer untuk app accounts."""
import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.accounts.models import User

logger = logging.getLogger(__name__)


class OTPService:
    """Service untuk pembuatan OTP dan pengiriman email."""

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
