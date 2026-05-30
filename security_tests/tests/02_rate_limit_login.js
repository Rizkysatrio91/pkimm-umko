// =============================================================================
// 02 — RATE LIMIT LOGIN (BRUTE-FORCE PROTECTION)
// =============================================================================
// Tujuan: Verifikasi endpoint /accounts/login/ punya rate limit yang
// mencegah brute-force credential stuffing. Project pakai
// core/rate_limiter.py:RateLimiter.check_login_limit dengan
// DatabaseCache (shared antar Gunicorn worker, post-pentest fix).
//
// Skenario:
//   1 VU mengirim 30 percobaan login dengan PASSWORD SALAH ke username
//   yang TIDAK PERNAH ADA ('k6_tidak_ada_xxxx'). Setelah N percobaan,
//   server seharusnya:
//     - kembali HTTP 200 dengan pesan "Terlalu banyak percobaan login"
//     - ATAU redirect dengan flash warning
//     - tidak boleh tetap menerima request → harus block
//
// Severity bila gagal: CRITICAL (brute-force terbuka).
//
// CATATAN PENTING:
//   - Test ini sengaja pakai username INVALID supaya tidak mengunci akun
//     real. Django tidak menerapkan account-lock per-username, hanya
//     IP-based rate limit.
//   - Jangan jalankan dari IP yang akan dipakai admin login real
//     setelah test, karena IP Anda akan ke-block sementara.
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/02_rate_limit_login.js
// =============================================================================

import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';
import { parseCsrfToken, randomString } from '../lib/helpers.js';

export const options = {
    vus: 1,
    iterations: 30, // 30 percobaan; project default RateLimiter login = 10/min
    thresholds: {
        // Setelah ~10 request, harus mulai muncul rate-limited responses.
        // Threshold: minimal 50% dari 30 request HARUS ditolak/diblokir.
        'rate_limited_count': ['count>=15'],
    },
};

import { Counter } from 'k6/metrics';
const rateLimitedCounter = new Counter('rate_limited_count');
const loginSuccessCounter = new Counter('login_success_count');

// Username acak yang tidak mungkin ada di DB
const FAKE_USERNAME = `k6_tidak_ada_${randomString(6)}`;
const FAKE_PASSWORD = 'wrong_password_xyz';

export default function () {
    const jar = http.cookieJar();

    // GET halaman login untuk dapatkan csrftoken
    const getRes = http.get(`${BASE_URL}/accounts/login/`, {
        headers: DEFAULT_HEADERS,
        jar,
        timeout: REQUEST_TIMEOUT,
    });
    const csrf = parseCsrfToken(getRes.body);

    if (!csrf) {
        check(getRes, { 'CSRF token bisa diparse': () => false });
        return;
    }

    // POST login dengan credential salah
    const postRes = http.post(
        `${BASE_URL}/accounts/login/`,
        {
            csrfmiddlewaretoken: csrf,
            username: FAKE_USERNAME,
            password: FAKE_PASSWORD,
        },
        {
            headers: { ...DEFAULT_HEADERS, Referer: `${BASE_URL}/accounts/login/` },
            jar,
            redirects: 0, // jangan auto-follow
            timeout: REQUEST_TIMEOUT,
        }
    );

    const body = postRes.body || '';
    const isRateLimited =
        postRes.status === 429 ||
        body.includes('Terlalu banyak') ||
        body.includes('terlalu banyak') ||
        body.includes('rate limit') ||
        body.includes('Too Many');

    const isLoginAccepted = postRes.status === 302; // redirect = login OK (BAHAYA)

    if (isRateLimited) rateLimitedCounter.add(1);
    if (isLoginAccepted) loginSuccessCounter.add(1);

    check(postRes, {
        '[CRIT] Login dengan credential salah JANGAN pernah accept (302)':
            () => !isLoginAccepted,
        '[INFO] Server merespons (bukan crash)':
            () => postRes.status !== 0 && postRes.status < 500,
    });

    // Jeda 200ms antar request supaya tidak overload
    sleep(0.2);
}

export function teardown() {
    console.log('\n--- HASIL UJI RATE LIMIT LOGIN ---');
    console.log('  Jika rate_limited_count >= 15 → rate limit BERFUNGSI ✓');
    console.log('  Jika rate_limited_count == 0  → rate limit TIDAK AKTIF ✗');
    console.log('  Jika login_success_count > 0  → CRITICAL: login terbobol!');
    console.log('-----------------------------------\n');
}
