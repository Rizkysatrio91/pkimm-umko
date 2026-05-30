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
// Skenario:
//   Lewati langkah forgot-password (set session) lalu kirim 20 percobaan OTP
//   acak yang salah. Setelah ~5 percobaan, server HARUS mulai menolak dengan
//   pesan "Terlalu banyak percobaan kode OTP".
//
// CATATAN PENTING:
//   - Test ini memakai email yang TIDAK terdaftar, jadi OTP tidak akan pernah
//     cocok — aman, tidak mengubah password siapa pun.
//   - Alur butuh session 'reset_email'. Kita set lewat POST forgot-password
//     dulu (rate limit forgot-password = 3/15mnt, jadi cukup 1x panggil).
//   - Karena per-IP, jalankan BUKAN dari IP yang dipakai user reset password
//     real setelahnya (IP akan ter-limit sementara).
//
// Severity bila gagal: CRITICAL (akun bisa dibajak via brute-force OTP).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/10_rate_limit_otp.js
// =============================================================================

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';
import { parseCsrfToken, randomString } from '../lib/helpers.js';

const otpBlockedCounter = new Counter('otp_attempt_blocked');
const otpAcceptedCounter = new Counter('otp_wrong_accepted');

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

export default function () {
    const jar = http.cookieJar();
    // Email acak yang tidak terdaftar — OTP tak akan pernah cocok.
    const fakeEmail = `k6_${randomString(8)}@example.invalid`;

    // 1. Set session 'reset_email' via forgot-password (1x panggil saja).
    const fpGet = http.get(`${BASE_URL}/accounts/forgot-password/`, {
        headers: DEFAULT_HEADERS, jar, timeout: REQUEST_TIMEOUT,
    });
    const fpCsrf = parseCsrfToken(fpGet.body);
    http.post(`${BASE_URL}/accounts/forgot-password/`, {
        csrfmiddlewaretoken: fpCsrf || '',
        email: fakeEmail,
    }, {
        headers: { ...DEFAULT_HEADERS, Referer: `${BASE_URL}/accounts/forgot-password/` },
        jar, redirects: 1, timeout: REQUEST_TIMEOUT,
    });

    // 2. Banjir percobaan OTP salah.
    console.log('\n=== UJI BRUTE-FORCE OTP (20 percobaan kode salah) ===');
    for (let i = 1; i <= TOTAL_ATTEMPTS; i++) {
        const voGet = http.get(`${BASE_URL}/accounts/verify-otp/`, {
            headers: DEFAULT_HEADERS, jar, redirects: 0, timeout: REQUEST_TIMEOUT,
        });
        // Kalau session hilang, server redirect balik ke forgot-password.
        const voCsrf = parseCsrfToken(voGet.body);

        // OTP acak 6 digit yang (hampir pasti) salah.
        const guess = String(Math.floor(100000 + Math.random() * 900000));
        const res = http.post(`${BASE_URL}/accounts/verify-otp/`, {
            csrfmiddlewaretoken: voCsrf || '',
            otp: guess,
        }, {
            headers: { ...DEFAULT_HEADERS, Referer: `${BASE_URL}/accounts/verify-otp/` },
            jar, redirects: 0, timeout: REQUEST_TIMEOUT,
        });

        const body = res.body || '';
        const blocked =
            res.status === 429 ||
            body.includes('Terlalu banyak percobaan kode OTP') ||
            body.includes('Terlalu banyak');
        // Redirect ke reset-password = OTP diterima (BAHAYA — tidak boleh terjadi).
        const accepted =
            res.status === 302 &&
            (res.headers['Location'] || '').includes('reset-password');

        if (blocked) otpBlockedCounter.add(1);
        if (accepted) otpAcceptedCounter.add(1);

        const tag = accepted ? '✗ DITERIMA!' : (blocked ? '■ diblokir' : '· ditolak');
        console.log(`  Percobaan ${String(i).padStart(2)} [${res.status}] ${tag}`);

        sleep(0.15);
    }
}

export function teardown() {
    console.log('\n--- HASIL UJI RATE LIMIT OTP ---');
    console.log('  otp_attempt_blocked >= 10 → rate limit OTP BERFUNGSI ✓');
    console.log('  otp_wrong_accepted  == 0  → tidak ada OTP salah yang lolos ✓');
    console.log('  Jika blocked == 0         → CRITICAL: OTP bisa di-brute-force ✗');
    console.log('---------------------------------\n');
}
