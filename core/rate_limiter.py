"""
Modul rate limiting menggunakan Django Cache.
Membatasi jumlah request per IP/user untuk mencegah penyalahgunaan.

CATATAN PENTING (post-pentest April-May 2026):
  - Cache backend WAJIB shared antar Gunicorn worker. LocMemCache per-proses
    bocor: 4 worker × limit_per_menit = efektif 4x lipat. Pakai DatabaseCache
    (lihat settings/base.py).
  - get_client_ip TIDAK percaya X-Forwarded-For mentah. Hanya pakai header
    proxy bila request datang dari loopback (artinya melewati nginx lokal).
  - CF-Connecting-IP hanya dipercaya bila XFF rightmost (= IP yang konek
    ke nginx) ada di range edge Cloudflare resmi (core/cloudflare_ips.py).
  - Untuk endpoint mahal (chatbot/OpenAI), batas anonymous lebih ketat
    daripada user terotentikasi.
"""
import time

from django.core.cache import cache

from core.cloudflare_ips import is_cloudflare_ip


# IP loopback yang dianggap sebagai proxy lokal (nginx → gunicorn).
# Hanya saat REMOTE_ADDR salah satu ini, kita boleh percaya X-Real-IP /
# X-Forwarded-For. Dari luar (akses langsung ke gunicorn 8000), kita tidak
# percaya header user-supplied.
_TRUSTED_PROXIES = {'127.0.0.1', '::1', 'localhost'}


class RateLimiter:
    """Kelas pembatas jumlah request per IP/user dalam periode waktu tertentu."""

    @staticmethod
    def get_client_ip(request) -> str:
        """Ambil IP klien dengan aman dari spoofing.

        Topologi production:
          User → Cloudflare edge → nginx (localhost) → gunicorn

        Aturan:
          1. REMOTE_ADDR BUKAN loopback → pakai REMOTE_ADDR (akses langsung
             tanpa proxy, header forward tidak valid).
          2. REMOTE_ADDR loopback (via nginx):
             a. Bila XFF rightmost ada di range edge Cloudflare resmi,
                request memang dari CF → pakai CF-Connecting-IP. nginx
                meng-append $remote_addr (IP yang konek ke nginx) di
                rightmost via $proxy_add_x_forwarded_for, sehingga
                penyerang yang bypass CF tidak bisa memalsukan ini.
             b. Selain itu, pakai X-Real-IP (di-set nginx).
             c. Fallback XFF rightmost (paling dekat nginx).
             d. Terakhir REMOTE_ADDR.

        Penyerang yang mengirim header palsu ke nginx hanya akan membuat
        nginx menambah IP asli mereka di rightmost XFF, jadi rightmost
        selalu IP TCP peer yang nyata.
        """
        remote = request.META.get('REMOTE_ADDR', '').strip()

        if remote not in _TRUSTED_PROXIES:
            return remote or 'unknown'

        # Lewat nginx lokal — cek apakah upstream-nya Cloudflare.
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '').strip()
        xff_ips = [i.strip() for i in xff.split(',') if i.strip()] if xff else []
        edge_ip = xff_ips[-1] if xff_ips else ''

        if edge_ip and is_cloudflare_ip(edge_ip):
            # Tervalidasi: TCP peer nginx ada di range edge CF.
            cf_ip = request.META.get('HTTP_CF_CONNECTING_IP', '').strip()
            if cf_ip:
                return cf_ip
            # Aneh: lewat CF tapi tanpa CF-Connecting-IP. Pakai leftmost XFF
            # (visitor IP yang ditulis CF) sebagai fallback.
            if len(xff_ips) >= 2:
                return xff_ips[0]
            return edge_ip

        # Bukan via CF — pakai header nginx tradisional.
        real_ip = request.META.get('HTTP_X_REAL_IP', '').strip()
        if real_ip:
            return real_ip

        if xff_ips:
            for ip in reversed(xff_ips):
                if ip and ip not in _TRUSTED_PROXIES:
                    return ip

        return remote or 'unknown'

    @staticmethod
    def is_rate_limited(key: str, max_requests: int, period_seconds: int) -> tuple:
        """Sliding window berbasis ``start_ts`` (anchor waktu pembukaan window).

        Window aktif kalau ``now - start_ts < period_seconds``. Counter
        ``key`` selalu di-set dengan TTL = sisa window agar konsisten dengan
        ``start_ts`` — keduanya hidup atau mati bersama.

        BUG FIX (2026-05): implementasi sebelumnya pakai ``cache.incr(key)``,
        tetapi di Django DatabaseCache ``incr()`` memanggil ``set()`` TANPA
        meneruskan timeout, sehingga TTL ter-reset ke default ``CACHES.TIMEOUT``
        (1 hari di proyek ini). Akibatnya counter bertahan 1 hari sementara
        ``start_ts`` expire setelah ``period_seconds`` (60 dtk untuk
        per-menit) — saat ``start_ts`` hilang tapi counter masih max,
        fallback ``remaining_secs = period_seconds`` membuat tiap retry
        menambah 1 window penuh dan user terkunci sampai TTL counter
        habis (24 jam).

        Return: (is_limited, remaining_requests, retry_after_seconds)
        """
        start_key = f"{key}_ts"
        now = time.time()
        start_ts = cache.get(start_key)

        # Window baru: belum ada anchor, atau anchor sudah lewat period.
        if start_ts is None or (now - float(start_ts)) >= period_seconds:
            cache.set(key, 1, period_seconds)
            cache.set(start_key, now, period_seconds)
            return (False, max_requests - 1, 0)

        elapsed = now - float(start_ts)
        remaining_secs = max(1, int(period_seconds - elapsed))
        count = cache.get(key, 0)

        if count >= max_requests:
            return (True, 0, remaining_secs)

        # Naikkan counter dengan TTL = sisa window. Tidak pakai cache.incr()
        # karena di DatabaseCache resets TTL ke default (lihat docstring).
        new_count = count + 1
        cache.set(key, new_count, remaining_secs)
        return (False, max_requests - new_count, 0)

    @staticmethod
    def check_min_interval(key: str, min_seconds: float) -> tuple:
        """Pastikan jeda minimum antar request. Gagal kalau request terlalu cepat.

        Return: (is_too_fast, retry_seconds)
        """
        last = cache.get(key)
        now = time.time()
        if last is not None:
            elapsed = now - float(last)
            if elapsed < min_seconds:
                return (True, max(1, int(min_seconds - elapsed) + 1))
        # Simpan timestamp request ini sebagai "last"
        cache.set(key, now, int(min_seconds * 4) + 1)
        return (False, 0)

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
    #
    # Strategi berlapis:
    #   1. Min interval (1.0 dtk): bunuh request konkuren — k6 dengan 10 VUs
    #      hampir bersamaan akan disaring di lapis ini.
    #   2. Per-menit, per-jam, per-hari: per identifier user/ip.
    #   3. Per-IP terpisah (untuk user terotentikasi): satu sesi tidak bisa
    #      dipakai di banyak mesin sekaligus untuk membakar budget.
    #   4. Per-sesi minimum interval ditambahkan di views (2 dtk antar pesan
    #      di session yang sama).
    #
    # Anonymous lebih ketat karena anonymous = tidak ada kontrak, mahal.

    # Limit anonymous (publik, belum login) — KETAT
    ANON_PER_MIN = 4
    ANON_PER_HOUR = 20
    ANON_PER_DAY = 60

    # Limit user terotentikasi — lebih longgar
    USER_PER_MIN = 8
    USER_PER_HOUR = 40
    USER_PER_DAY = 150

    # Limit per IP terlepas dari status auth (anti session-sharing)
    PER_IP_HARD_DAY = 100

    @classmethod
    def check_chatbot_limit(cls, request, jenis: str = 'umum') -> tuple:
        """
        Batasi chatbot per IP/user.
        Return: (is_limited, pesan_untuk_user, retry_seconds)
        """
        from datetime import datetime, timedelta

        ip = cls.get_client_ip(request)

        if request.user.is_authenticated:
            identifier = f"user_{request.user.id_user}"
            per_min = cls.USER_PER_MIN
            per_hour = cls.USER_PER_HOUR
            per_day = cls.USER_PER_DAY
        else:
            identifier = f"ip_{ip}"
            per_min = cls.ANON_PER_MIN
            per_hour = cls.ANON_PER_HOUR
            per_day = cls.ANON_PER_DAY

        def _msg(retry_secs, label):
            now = datetime.now()
            reset_at = now + timedelta(seconds=retry_secs)
            reset_str = reset_at.strftime('%H:%M')
            return (
                f"Anda telah mencapai batas penggunaan{label}. "
                f"Penggunaan Anda akan direset pada pukul {reset_str} WIB."
            )

        # Per menit
        limited, _, retry_secs = cls.is_rate_limited(
            f"chat_min_{identifier}", per_min, 60,
        )
        if limited:
            return (True, _msg(retry_secs, ''), retry_secs)

        # Per jam
        limited, _, retry_secs = cls.is_rate_limited(
            f"chat_hour_{identifier}", per_hour, 3600,
        )
        if limited:
            return (True, _msg(retry_secs, ' per jam'), retry_secs)

        # Per hari (per identifier)
        limited, _, retry_secs = cls.is_rate_limited(
            f"chat_day_{identifier}", per_day, 86400,
        )
        if limited:
            return (True, _msg(retry_secs, ' harian'), retry_secs)

        # Per-IP harian (anti session-sharing dari banyak mesin)
        limited, _, retry_secs = cls.is_rate_limited(
            f"chat_day_ip_{ip}", cls.PER_IP_HARD_DAY, 86400,
        )
        if limited:
            return (True, _msg(retry_secs, ' harian dari jaringan ini'), retry_secs)

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
