"""Helper keamanan: signed token & verifikasi anti-bot untuk chatbot publik.

Strategi:
  - Server menerbitkan token HMAC saat halaman chatbot di-render (GET).
  - Token = base64(payload) + '.' + base64(hmac_sha256(SECRET_KEY, payload))
    Payload = "{issued_ts}:{client_fp}" (timestamp + fingerprint IP+UA).
  - Token wajib dikirim balik di body POST. Token kadaluarsa 30 menit.
  - Bot yang langsung POST tanpa GET halaman dulu tidak punya token → ditolak.

Tujuan:
  - Memaksa setiap penyerang minimal melakukan GET dulu (lebih mahal).
  - Mengikat token ke IP+UA → dipakai dari mesin lain langsung tidak valid.
  - Tidak butuh JS yang mahal — token cukup di-inject di template.

Bukan pengganti rate limit — ini lapisan tambahan.
"""
import base64
import hashlib
import hmac
import time

from django.conf import settings


# Token kadaluarsa 30 menit. Cukup lama untuk percakapan normal,
# tapi tidak cukup untuk dipakai berhari-hari oleh bot.
TOKEN_TTL_SECONDS = 30 * 60


def _client_fingerprint(ip: str, user_agent: str) -> str:
    """Hash pendek dari IP+UA. Token akan terikat fingerprint ini."""
    raw = f"{ip}|{user_agent or ''}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(s: str) -> bytes:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_chat_token(ip: str, user_agent: str) -> str:
    """Terbitkan token HMAC untuk klien dengan IP & UA tertentu.

    Token formatnya: <payload_b64>.<sig_b64>
    """
    fp = _client_fingerprint(ip, user_agent)
    issued = int(time.time())
    payload = f"{issued}:{fp}".encode('utf-8')
    sig = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha256,
    ).digest()
    return f"{_b64url(payload)}.{_b64url(sig)}"


def verify_chat_token(token: str, ip: str, user_agent: str) -> bool:
    """Cek token valid: signature cocok, belum expired, fingerprint sesuai."""
    if not token or '.' not in token:
        return False
    try:
        payload_b64, sig_b64 = token.split('.', 1)
        payload = _b64url_decode(payload_b64)
        sig = _b64url_decode(sig_b64)
    except (ValueError, TypeError):
        return False

    expected_sig = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(sig, expected_sig):
        return False

    try:
        issued_str, fp = payload.decode('utf-8').split(':', 1)
        issued = int(issued_str)
    except (ValueError, UnicodeDecodeError):
        return False

    # Cek expired
    if int(time.time()) - issued > TOKEN_TTL_SECONDS:
        return False

    # Cek fingerprint cocok (token hanya valid untuk IP+UA yang menerbitkannya)
    if fp != _client_fingerprint(ip, user_agent):
        return False

    return True
