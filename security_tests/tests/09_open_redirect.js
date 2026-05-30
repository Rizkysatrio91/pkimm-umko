// =============================================================================
// 09 — PROTEKSI OPEN REDIRECT PADA LOGIN
// =============================================================================
// Tujuan: Memastikan parameter ?next= di /accounts/login/ TIDAK bisa dipakai
// untuk mengarahkan korban ke situs eksternal (phishing) setelah login.
//
// Referensi perbaikan: apps/accounts/views.py — LoginView memvalidasi `next`
// dengan url_has_allowed_host_and_scheme (hanya host sendiri / path relatif
// yang diizinkan). URL eksternal diabaikan → jatuh ke dashboard sesuai role.
//
// Skenario:
//   Kirim sederet payload `next` berbahaya (domain luar, skema //, suffix
//   attack). Pastikan server TIDAK PERNAH membalas header Location yang
//   menunjuk ke domain attacker — baik pada GET halaman login maupun POST
//   login yang gagal.
//
// Severity bila gagal: HIGH (phishing redirect — mencuri kepercayaan korban).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/09_open_redirect.js
// =============================================================================

import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';
import { parseCsrfToken, extractCookie } from '../lib/helpers.js';

export const options = {
    vus: 1,
    iterations: 1,
    thresholds: {
        // Semua pengecekan WAJIB lulus — tidak boleh ada satu pun redirect keluar.
        checks: ['rate==1.0'],
    },
};

// Payload klasik open redirect. Semua HARUS ditolak / diabaikan oleh server.
const EVIL_TARGETS = [
    'https://evil.example.com',
    'http://attacker.test/phishing',
    '//evil.example.com',
    'https:evil.example.com',
    'https://pkimm-ftik-umko.my.id.evil.example.com', // domain mirip (suffix attack)
];

// Apakah string Location menunjuk ke host eksternal/attacker?
function isExternalRedirect(location) {
    if (!location) return false;
    // Aman: path relatif ('/...') ke host sendiri. '//' = protocol-relative (bahaya).
    if (location.startsWith('/') && !location.startsWith('//')) return false;
    return /evil\.example\.com|attacker\.test/i.test(location);
}

export default function () {
    console.log('\n=== UJI OPEN REDIRECT (?next= berbahaya) ===');

    for (const target of EVIL_TARGETS) {
        const jar = http.cookieJar();
        const loginUrl = `${BASE_URL}/accounts/login/?next=${encodeURIComponent(target)}`;

        // 1. GET halaman login dengan next berbahaya — jangan redirect keluar.
        const getRes = http.get(loginUrl, {
            headers: DEFAULT_HEADERS,
            jar,
            redirects: 0,
            timeout: REQUEST_TIMEOUT,
        });
        const getLeak = isExternalRedirect(getRes.headers['Location']);

        // 2. POST login dengan kredensial sengaja salah — server tetap tidak
        //    boleh menulis Location ke domain attacker meski next diisi.
        const csrf = parseCsrfToken(getRes.body);
        const postRes = http.post(loginUrl, {
            csrfmiddlewaretoken: csrf || '',
            username: 'k6_tidak_ada_user',
            password: `salah_${Date.now()}`,
        }, {
            headers: { ...DEFAULT_HEADERS, Referer: loginUrl },
            jar,
            redirects: 0,
            timeout: REQUEST_TIMEOUT,
        });
        const postLeak = isExternalRedirect(postRes.headers['Location']);

        check(null, {
            [`[HIGH] GET  next=${target}: tidak redirect ke luar`]: () => !getLeak,
            [`[HIGH] POST next=${target}: tidak redirect ke luar`]: () => !postLeak,
        });

        const tag = (getLeak || postLeak) ? '✗ BOCOR (redirect keluar!)' : '✓ aman';
        console.log(`  ${target.padEnd(50)} ${tag}`);
    }

    console.log('\n  Lulus semua → proteksi open redirect BERFUNGSI ✓\n');
}
