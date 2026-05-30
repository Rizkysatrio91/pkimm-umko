// =============================================================================
// 04 — RATE LIMIT FORGOT PASSWORD (ANTI EMAIL ABUSE)
// =============================================================================
// Tujuan: Verifikasi /accounts/forgot-password/ tidak bisa di-abuse
// untuk membombardir email user (atau membakar quota Gmail SMTP).
//
// Project pakai RateLimiter.check_forgot_password_limit (lihat
// apps/accounts/views.py:196).
//
// Skenario:
//   1 VU mengirim 15 request reset password ke email random yang
//   tidak ada di DB. Server seharusnya:
//     - Beberapa request awal: HTTP 200 dengan flash "OTP sudah dikirim
//       jika email terdaftar" (response sama untuk email valid/invalid
//       — best practice, mencegah enumeration)
//     - Request berikutnya: rate-limited
//
// Severity bila gagal: HIGH (email bombing + biaya Gmail relay).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/04_rate_limit_forgot_password.js
// =============================================================================

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';
import { parseCsrfToken, randomString } from '../lib/helpers.js';

export const options = {
    vus: 1,
    iterations: 15,
    thresholds: {
        // Setelah ~5 request, rate limit harus aktif.
        // Minimal 60% dari 15 request ditolak.
        'rate_limited_forgot': ['count>=9'],
    },
};

const rateLimitedForgot = new Counter('rate_limited_forgot');

export default function () {
    const jar = http.cookieJar();
    const url = `${BASE_URL}/accounts/forgot-password/`;

    const getRes = http.get(url, {
        headers: DEFAULT_HEADERS,
        jar,
        timeout: REQUEST_TIMEOUT,
    });
    const csrf = parseCsrfToken(getRes.body);
    if (!csrf) {
        check(getRes, { 'CSRF forgot-password bisa diparse': () => false });
        return;
    }

    // Email random yang TIDAK ADA di DB — supaya tidak benar-benar
    // mengirim email ke user real
    const fakeEmail = `k6test_${randomString(8)}@example.invalid`;

    const postRes = http.post(
        url,
        { csrfmiddlewaretoken: csrf, email: fakeEmail },
        {
            headers: { ...DEFAULT_HEADERS, Referer: url },
            jar,
            redirects: 0,
            timeout: REQUEST_TIMEOUT,
        }
    );

    const body = postRes.body || '';
    const isRateLimited =
        postRes.status === 429 ||
        body.includes('Terlalu') ||
        body.includes('rate limit') ||
        body.includes('Too Many');

    // Best practice: response untuk email tidak ada vs ada HARUS sama,
    // supaya attacker tidak bisa enumerate email valid.
    // Status 200/302 tanpa pesan "email tidak ditemukan" → BAGUS.
    const enumerationLeak =
        body.includes('tidak terdaftar') ||
        body.includes('tidak ditemukan') ||
        body.includes('email tidak ada');

    if (isRateLimited) rateLimitedForgot.add(1);

    check(postRes, {
        '[HIGH] Tidak bocor info email valid/invalid (anti-enumeration)':
            () => !enumerationLeak,
        '[INFO] Server merespons normal':
            () => postRes.status !== 0 && postRes.status < 500,
    });

    sleep(0.3);
}

export function teardown() {
    console.log('\n--- HASIL UJI RATE LIMIT FORGOT PASSWORD ---');
    console.log('  Target: ≥ 9 dari 15 request harus ditolak (≥ 60%)');
    console.log('  Kalau enumeration_leak terdeteksi → tutup di views.py');
    console.log('--------------------------------------------\n');
}
