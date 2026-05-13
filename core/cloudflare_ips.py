"""Daftar IP edge Cloudflare + helper validasi.

Dipakai oleh ``core.rate_limiter.RateLimiter.get_client_ip`` untuk
memastikan header ``CF-Connecting-IP`` hanya dipercaya bila request
benar-benar datang dari edge Cloudflare. Tanpa validasi ini, penyerang
yang akses langsung ke origin (bypass CF) bisa kirim CF-Connecting-IP
palsu dan mem-bypass rate limit per-IP.

Sumber resmi (cek ulang sebelum deploy, jarang berubah):
  - https://www.cloudflare.com/ips-v4/
  - https://www.cloudflare.com/ips-v6/
"""
import ipaddress
from functools import lru_cache

# Snapshot 2024-2026. Update saat Cloudflare mengumumkan range baru.
_CF_IPV4_RANGES = (
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
)

_CF_IPV6_RANGES = (
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
)


@lru_cache(maxsize=1)
def _cf_networks():
    return tuple(
        ipaddress.ip_network(r)
        for r in (_CF_IPV4_RANGES + _CF_IPV6_RANGES)
    )


def is_cloudflare_ip(ip: str) -> bool:
    """Return True jika ``ip`` berada di salah satu range edge Cloudflare."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    return any(addr in net for net in _cf_networks())
