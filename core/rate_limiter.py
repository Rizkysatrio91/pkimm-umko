"""
Modul rate limiting menggunakan Django Cache.
Membatasi jumlah request per IP/user untuk mencegah penyalahgunaan.
Tidak perlu library tambahan — menggunakan cache bawaan Django.
"""
import time

from django.core.cache import cache


class RateLimiter:
    """Kelas pembatas jumlah request per IP/user dalam periode waktu tertentu."""

    @staticmethod
    def get_client_ip(request) -> str:
        """Ambil IP address dari request."""
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')

    @staticmethod
    def is_rate_limited(key: str, max_requests: int, period_seconds: int) -> tuple:
        """
        Cek apakah request sudah melebihi batas.
        Menyimpan waktu mulai periode agar bisa menghitung SISA WAKTU yang akurat.
        Return: (is_limited, remaining_requests, retry_after_seconds)
        """
        count = cache.get(key, 0)
        start_key = f"{key}_ts"

        if count >= max_requests:
            # Hitung sisa waktu SEBENARNYA berdasarkan kapan periode dimulai
            start_ts = cache.get(start_key)
            if start_ts:
                elapsed = time.time() - start_ts
                remaining_secs = max(1, int(period_seconds - elapsed))
            else:
                remaining_secs = period_seconds
            return (True, 0, remaining_secs)

        if count == 0:
            cache.set(key, 1, period_seconds)
            cache.set(start_key, time.time(), period_seconds)
        else:
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, period_seconds)
                cache.set(start_key, time.time(), period_seconds)

        return (False, max_requests - count - 1, 0)

    # === LOGIN RATE LIMIT ===

    @classmethod
    def check_login_limit(cls, request) -> tuple:
        """Batasi login: maks 5 percobaan per 15 menit per IP."""
        ip = cls.get_client_ip(request)
        return cls.is_rate_limited(f"login_{ip}", max_requests=5, period_seconds=900)

    @classmethod
    def get_login_attempts(cls, request) -> int:
        """Ambil jumlah percobaan login saat ini."""
        ip = cls.get_client_ip(request)
        return cache.get(f"login_{ip}", 0)

    @classmethod
    def reset_login_limit(cls, request):
        """Reset counter login setelah berhasil login."""
        ip = cls.get_client_ip(request)
        cache.delete(f"login_{ip}")

    # === FORGOT PASSWORD RATE LIMIT ===

    @classmethod
    def check_forgot_password_limit(cls, request) -> tuple:
        """Batasi pengiriman OTP reset password: maks 3 percobaan per 15 menit per IP.

        Mencegah spam OTP (habiskan kuota Gmail) dan mempersulit attacker
        yang ingin enumerasi email terdaftar lewat respons waktu.
        """
        ip = cls.get_client_ip(request)
        return cls.is_rate_limited(f"forgot_pwd_{ip}", max_requests=3, period_seconds=900)

    # === CHATBOT RATE LIMIT ===

    @classmethod
    def check_chatbot_limit(cls, request, jenis: str = 'umum') -> tuple:
        """
        Batasi chatbot per IP/user. Longgar agar user nyaman.
        Batas: 10/menit, 60/jam, 300/hari.
        Return: (is_limited, pesan_untuk_user, retry_seconds)
        """
        from datetime import datetime, timedelta

        if request.user.is_authenticated:
            identifier = f"user_{request.user.id_user}"
        else:
            identifier = f"ip_{cls.get_client_ip(request)}"

        # Per menit: maks 10 pesan (anti flood/spam bot)
        limited, _, retry_secs = cls.is_rate_limited(
            f"chat_min_{identifier}", 10, 60,
        )
        if limited:
            now = datetime.now()
            reset_at = now + timedelta(seconds=retry_secs)
            reset_str = reset_at.strftime('%H:%M')
            msg = (
                f"Anda telah mencapai batas penggunaan. "
                f"Penggunaan Anda akan direset pada pukul {reset_str} WIB."
            )
            return (True, msg, retry_secs)

        # Per jam: maks 60 pesan
        limited, _, retry_secs = cls.is_rate_limited(
            f"chat_hour_{identifier}", 60, 3600,
        )
        if limited:
            now = datetime.now()
            reset_at = now + timedelta(seconds=retry_secs)
            reset_str = reset_at.strftime('%H:%M')
            msg = (
                f"Anda telah mencapai batas penggunaan per jam. "
                f"Penggunaan Anda akan direset pada pukul {reset_str} WIB."
            )
            return (True, msg, retry_secs)

        # Per hari: maks 300 pesan
        limited, _, retry_secs = cls.is_rate_limited(
            f"chat_day_{identifier}", 300, 86400,
        )
        if limited:
            now = datetime.now()
            reset_at = now + timedelta(seconds=retry_secs)
            reset_str = reset_at.strftime('%H:%M')
            msg = (
                f"Anda telah mencapai batas penggunaan harian. "
                f"Penggunaan Anda akan direset pada pukul {reset_str} WIB."
            )
            return (True, msg, retry_secs)

        return (False, '', 0)

    # === OCR RATE LIMIT ===

    @classmethod
    def check_ocr_limit(cls, request) -> tuple:
        """Batasi upload KRS: maks 3x per hari per user."""
        if request.user.is_authenticated:
            identifier = f"user_{request.user.id_user}"
        else:
            identifier = f"ip_{cls.get_client_ip(request)}"

        return cls.is_rate_limited(f"ocr_day_{identifier}", max_requests=3, period_seconds=86400)

    # === SMART EDITOR RATE LIMIT ===

    @classmethod
    def check_editor_limit(cls, request) -> tuple:
        """Batasi koreksi AI berita: maks 10x per hari per user."""
        if request.user.is_authenticated:
            identifier = f"user_{request.user.id_user}"
        else:
            identifier = f"ip_{cls.get_client_ip(request)}"

        return cls.is_rate_limited(f"editor_day_{identifier}", max_requests=10, period_seconds=86400)
