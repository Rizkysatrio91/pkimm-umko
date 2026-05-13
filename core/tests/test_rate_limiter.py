"""Unit test get_client_ip — fokus pada anti-spoofing CF-Connecting-IP.

Skenario yang dijamin gagal sebelum perbaikan dan harus lolos sekarang:
  - Penyerang akses langsung ke origin (bypass CF) lalu kirim
    CF-Connecting-IP palsu → HARUS diabaikan, pakai REMOTE_ADDR asli.
  - Penyerang lewat nginx lokal (REMOTE_ADDR loopback) tapi tidak via CF
    (XFF rightmost bukan IP edge CF), kirim CF-Connecting-IP palsu →
    HARUS diabaikan, fallback ke XFF rightmost / X-Real-IP.

Skenario positif:
  - Request beneran via CF (XFF rightmost di range CF) →
    CF-Connecting-IP dipercaya.
"""
from django.test import RequestFactory, SimpleTestCase

from core.cloudflare_ips import is_cloudflare_ip
from core.rate_limiter import RateLimiter


class CloudflareIpRangeTests(SimpleTestCase):
    """is_cloudflare_ip — sanity check daftar range."""

    def test_known_cf_v4_inside_range(self):
        # 104.16.0.1 ∈ 104.16.0.0/13
        self.assertTrue(is_cloudflare_ip("104.16.0.1"))

    def test_known_cf_v4_inside_172_range(self):
        # 172.64.0.1 ∈ 172.64.0.0/13
        self.assertTrue(is_cloudflare_ip("172.64.0.1"))

    def test_known_cf_v6_inside_range(self):
        self.assertTrue(is_cloudflare_ip("2606:4700::1"))

    def test_non_cf_public_ip(self):
        # 8.8.8.8 (Google DNS) bukan CF
        self.assertFalse(is_cloudflare_ip("8.8.8.8"))

    def test_loopback_not_cf(self):
        self.assertFalse(is_cloudflare_ip("127.0.0.1"))

    def test_empty_and_invalid_input(self):
        self.assertFalse(is_cloudflare_ip(""))
        self.assertFalse(is_cloudflare_ip("not-an-ip"))
        self.assertFalse(is_cloudflare_ip("999.999.999.999"))


class GetClientIpTests(SimpleTestCase):
    """Validasi keputusan get_client_ip per skenario serangan."""

    def setUp(self):
        self.rf = RequestFactory()

    def _req(self, **meta):
        request = self.rf.get('/')
        request.META.update(meta)
        return request

    # --- Direct access (tanpa proxy) -------------------------------------

    def test_direct_public_remote_addr_used(self):
        """Akses langsung ke gunicorn → header forward harus diabaikan."""
        request = self._req(
            REMOTE_ADDR='203.0.113.5',
            HTTP_X_FORWARDED_FOR='1.2.3.4',
            HTTP_X_REAL_IP='5.6.7.8',
            HTTP_CF_CONNECTING_IP='9.9.9.9',
        )
        self.assertEqual(RateLimiter.get_client_ip(request), '203.0.113.5')

    def test_direct_attacker_spoofs_cf_connecting_ip(self):
        """REMOTE_ADDR publik (bukan loopback) + CF-Connecting-IP palsu →
        pakai REMOTE_ADDR, BUKAN CF-Connecting-IP."""
        request = self._req(
            REMOTE_ADDR='198.51.100.50',
            HTTP_CF_CONNECTING_IP='1.1.1.1',  # spoof: pura-pura "user via CF"
        )
        self.assertEqual(RateLimiter.get_client_ip(request), '198.51.100.50')

    # --- Via nginx, BUKAN via CF -----------------------------------------

    def test_nginx_no_cf_uses_x_real_ip(self):
        """nginx tradisional (set X-Real-IP, XFF rightmost = IP klien)."""
        request = self._req(
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_REAL_IP='203.0.113.10',
            HTTP_X_FORWARDED_FOR='203.0.113.10',
        )
        self.assertEqual(RateLimiter.get_client_ip(request), '203.0.113.10')

    def test_nginx_no_cf_spoofed_cf_connecting_ip_rejected(self):
        """Penyerang akses langsung nginx, kirim CF-Connecting-IP palsu.
        XFF rightmost = IP attacker (nginx append $remote_addr) → BUKAN CF
        → CF-Connecting-IP harus diabaikan, pakai XFF rightmost / X-Real-IP."""
        request = self._req(
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='198.51.100.99',  # IP attacker append nginx
            HTTP_X_REAL_IP='198.51.100.99',
            HTTP_CF_CONNECTING_IP='1.1.1.1',  # spoof
        )
        result = RateLimiter.get_client_ip(request)
        self.assertEqual(result, '198.51.100.99')
        self.assertNotEqual(result, '1.1.1.1')

    def test_nginx_no_cf_xff_chain_rightmost_used(self):
        """XFF rantai dengan rightmost IP attacker (nginx append) — pakai itu."""
        request = self._req(
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='1.2.3.4, 5.6.7.8, 198.51.100.99',
        )
        self.assertEqual(RateLimiter.get_client_ip(request), '198.51.100.99')

    # --- Via CF (XFF rightmost di range CF) ------------------------------

    def test_via_cf_trusts_cf_connecting_ip(self):
        """nginx menerima request dari edge CF → XFF rightmost ada di range
        CF → CF-Connecting-IP dipercaya (= IP user asli)."""
        request = self._req(
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='203.0.113.42, 172.64.0.10',  # rightmost CF edge
            HTTP_CF_CONNECTING_IP='203.0.113.42',
        )
        self.assertEqual(RateLimiter.get_client_ip(request), '203.0.113.42')

    def test_via_cf_attacker_cannot_inject_fake_cf_at_rightmost(self):
        """Penyerang yang TIDAK lewat CF tapi kirim XFF berisi IP CF di
        depan: nginx tetap append $remote_addr (IP attacker) di rightmost
        → rightmost bukan CF → CF-Connecting-IP diabaikan."""
        request = self._req(
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='172.64.0.10, 198.51.100.99',  # nginx append attacker
            HTTP_CF_CONNECTING_IP='1.1.1.1',  # spoof
        )
        result = RateLimiter.get_client_ip(request)
        self.assertEqual(result, '198.51.100.99')

    def test_via_cf_without_cf_connecting_ip_falls_back_to_leftmost(self):
        """Edge case: XFF rightmost CF tapi CF-Connecting-IP tidak ada.
        Fallback ke leftmost XFF (yang ditulis CF = visitor IP)."""
        request = self._req(
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='203.0.113.42, 104.16.0.5',
        )
        self.assertEqual(RateLimiter.get_client_ip(request), '203.0.113.42')

    # --- Fallback / robustness ------------------------------------------

    def test_loopback_without_any_proxy_header(self):
        request = self._req(REMOTE_ADDR='127.0.0.1')
        self.assertEqual(RateLimiter.get_client_ip(request), '127.0.0.1')

    def test_empty_remote_addr(self):
        request = self._req(REMOTE_ADDR='')
        self.assertEqual(RateLimiter.get_client_ip(request), 'unknown')

    def test_xff_with_only_loopback_entries(self):
        """XFF cuma berisi loopback → fallback ke REMOTE_ADDR."""
        request = self._req(
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='127.0.0.1, ::1',
        )
        # XFF rightmost = ::1 (loopback, di-skip oleh loop), result = 127.0.0.1
        self.assertEqual(RateLimiter.get_client_ip(request), '127.0.0.1')
