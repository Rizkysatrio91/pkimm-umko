// =============================================================================
// 10 — RATE LIMIT VERIFIKASI OTP (ANTI BRUTE-FORCE RESET PASSWORD)
// =============================================================================
// Tujuan: Verifikasi endpoint verifikasi OTP (/accounts/verify-otp/) membatasi
// jumlah percobaan tebak kode. OTP hanya 6 digit (1 juta kombinasi) dengan TTL
// 10 menit — tanpa rate limit, kode bisa di-brute-force untuk membajak akun
// lewat alur reset password.
//
// Referensi perbaikan:
//   - core/rate_limiter.py — RateLimiter.check_otp_verify_limit
//     (maks 5 percobaan / 15 menit per IP)
//   - apps/accounts/views.py — VerifyOTPView memanggil limiter sebelum cek OTP
//   - apps/accounts/models.py — OTP pakai secrets (CSPRNG) + compare_digest
//
// CARA KERJA (penting — alur 3 langkah + CSRF):
//   Endpoint OTP dilindungi CSRF. Agar request sampai ke logika OTP (bukan
//   ditolak CSRF lebih dulu), test:
//     1. GET forgot-password → dapatkan cookie csrftoken.
//     2. POST forgot-password (pakai token cookie) → set session reset_email.
//        Django menerima nilai cookie csrftoken langsung sebagai
//        csrfmiddlewaretoken, jadi tidak perlu parse HTML yang rapuh.
//     3. POST verify-otp 20x dengan kode acak salah. Setelah 5 percobaan,
//        server HARUS menolak: render "Terlalu banyak percobaan kode OTP".
//
// CATATAN PENTING:
//   - Memakai email yang TIDAK terdaftar → OTP tak pernah cocok, tidak
//     mengubah akun siapa pun.
//   - Per-IP: jalankan BUKAN dari IP yang dipakai user reset password real
//     setelahnya (IP akan ter-limit ~15 menit — itu memang buktinya bekerja).
//   - Status 403 = ditolak CSRF (alur gagal disiapkan), BUKAN bukti limiter.
//     Test membedakan ini lewat counter terpisah agar tidak menyesatkan.
//
// Severity bila gagal: CRITICAL (akun bisa dibajak via brute-force OTP).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/10_rate_limit_otp.js
// =============================================================================

import http from 'k6/http';
import { sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';
import { extractCookie, parseCsrfToken, randomString } from '../lib/helpers.js';

const otpBlockedCounter = new Counter('otp_attempt_blocked');   // ditolak rate limit
const otpAcceptedCounter = new Counter('otp_wrong_accepted');   // OTP salah diterima (BAHAYA)
const csrfBlockedCounter = new Counter('otp_csrf_blocked');     // 403 (alur gagal disiapkan)

export const options = {
    vus: 1,
    iterations: 1,
    thresholds: {
        // Dari 20 percobaan, mayoritas (>=10) HARUS sudah diblokir rate limit.
        'otp_attempt_blocked': ['count>=10'],
        // OTP salah TIDAK BOLEH pernah diterima sebagai valid.
        'otp_wrong_accepted': ['count==0'],
    },
};

const TOTAL_ATTEMPTS = 20;
const FORGOT_URL = `${BASE_URL}/accounts/forgot-password/`;
const VERIFY_URL = `${BASE_URL}/accounts/verify-otp/`;

export default function () {
    const jar = http.cookieJar();
    // Email acak yang tidak terdaftar — OTP tak akan pernah cocok.
    const fakeEmail = `k6_${randomString(8)}@example.invalid`;

    // --- Langkah 1: GET forgot-password untuk dapatkan cookie csrftoken -------
    const fpGet = http.get(FORGOT_URL, {
        headers: DEFAULT_HEADERS, jar, timeout: REQUEST_TIMEOUT,
    });
    // Django menerima nilai cookie csrftoken langsung sebagai form token.
    // Lebih tangguh daripada parse HTML (yang gagal bila halaman redirect).
    let csrfToken = extractCookie(fpGet, 'csrftoken') || parseCsrfToken(fpGet.body);

    if (!csrfToken) {
        console.log('  ✗ Gagal memperoleh csrftoken — tidak bisa menyiapkan alur. Cek server.');
        return;
    }

    // --- Langkah 2: POST forgot-password untuk set session reset_email -------
    const fpPost = http.post(FORGOT_URL, {
        csrfmiddlewaretoken: csrfToken,
        email: fakeEmail,
    }, {
        headers: { ...DEFAULT_HEADERS, Referer: FORGOT_URL },
        jar, redirects: 0, timeout: REQUEST_TIMEOUT,
    });
    // Refresh token bila cookie diputar.
    csrfToken = extractCookie(fpPost, 'csrftoken') || csrfToken;

    if (fpPost.status === 403) {
        console.log('  ✗ POST forgot-password ditolak CSRF (403) — alur tidak bisa disiapkan.');
        return;
    }

    // --- Langkah 3: banjir percobaan OTP salah ------------------------------
    console.log('\n=== UJI BRUTE-FORCE OTP (20 percobaan kode salah) ===');
    for (let i = 1; i <= TOTAL_ATTEMPTS; i++) {
        const guess = String(Math.floor(100000 + Math.random() * 900000));
        const res = http.post(VERIFY_URL, {
            csrfmiddlewaretoken: csrfToken,
            otp: guess,
        }, {
            headers: { ...DEFAULT_HEADERS, Referer: VERIFY_URL },
            jar, redirects: 0, timeout: REQUEST_TIMEOUT,
        });
        csrfToken = extractCookie(res, 'csrftoken') || csrfToken;

        const body = res.body || '';
        const blocked =
            res.status === 429 ||
            body.includes('Terlalu banyak percobaan kode OTP') ||
            body.includes('Terlalu banyak');
        const accepted =
            res.status === 302 &&
            (res.headers['Location'] || '').includes('reset-password');
        const csrfBlocked = res.status === 403;

        if (blocked) otpBlockedCounter.add(1);
        if (accepted) otpAcceptedCounter.add(1);
        if (csrfBlocked) csrfBlockedCounter.add(1);

        let tag;
        if (accepted) tag = '✗ DITERIMA! (bahaya)';
        else if (blocked) tag = '■ diblokir rate-limit';
        else if (csrfBlocked) tag = '✗ ditolak CSRF (alur gagal)';
        else tag = '· ditolak (OTP salah)';
        console.log(`  Percobaan ${String(i).padStart(2)} [${res.status}] ${tag}`);

        sleep(0.15);
    }
}

export function teardown() {
    console.log('\n--- HASIL UJI RATE LIMIT OTP ---');
    console.log('  otp_attempt_blocked >= 10 → rate limit OTP BERFUNGSI ✓');
    console.log('  otp_wrong_accepted  == 0  → tidak ada OTP salah yang lolos ✓');
    console.log('  otp_csrf_blocked > 0      → alur CSRF gagal disiapkan (perbaiki test, bukan vuln)');
    console.log('---------------------------------\n');
}
