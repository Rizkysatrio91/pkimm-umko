// =============================================================================
// 07 — IP SPOOFING (RATE LIMIT BYPASS via X-Forwarded-For)
// =============================================================================
// Tujuan: Verifikasi RateLimiter TIDAK bisa di-bypass dengan mengirim
// header X-Forwarded-For palsu yang berbeda-beda tiap request.
//
// Project sudah memitigasi ini di core/rate_limiter.py:get_client_ip
// dengan rule:
//   - Hanya percaya XFF kalau REMOTE_ADDR adalah loopback (127.0.0.1, ::1)
//   - Pakai RIGHTMOST XFF (paling dekat ke nginx, paling dipercaya)
//
// Skenario:
//   Kirim 30 request ke /chatbot/api/send/ dengan header X-Forwarded-For
//   acak yang BERBEDA tiap request. Kalau RateLimiter naive (ambil
//   leftmost XFF), 30 request akan terlihat sebagai 30 IP berbeda dan
//   tidak terblokir → BYPASS.
//
//   Tapi karena project pakai rightmost dan hanya percaya XFF kalau
//   REMOTE_ADDR loopback, request dari internet (REMOTE_ADDR = IP
//   penyerang publik) seharusnya tetap dihitung sebagai 1 IP saja.
//
// Severity bila gagal: CRITICAL (semua rate limit chatbot bypass-able).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/07_ip_spoofing.js
// =============================================================================

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';
import { parseCsrfToken } from '../lib/helpers.js';

export const options = {
    vus: 1,
    iterations: 30,
    thresholds: {
        // Walaupun XFF berbeda-beda, ≥ 70% request HARUS tetap ditolak
        // karena server pakai REMOTE_ADDR (IP asli kita) sebagai key.
        'spoof_blocked': ['count>=21'],
    },
};

const spoofBlocked = new Counter('spoof_blocked');
const spoofBypassed = new Counter('spoof_bypassed');

function fakeIp() {
    // Generate IP acak di range 1.0.0.0 - 254.255.255.255
    const r = () => Math.floor(Math.random() * 254) + 1;
    return `${r()}.${r()}.${r()}.${r()}`;
}

export default function () {
    const jar = http.cookieJar();

    // GET CSRF dulu
    const getRes = http.get(`${BASE_URL}/chatbot/`, {
        headers: DEFAULT_HEADERS,
        jar,
        timeout: REQUEST_TIMEOUT,
    });
    const csrf = parseCsrfToken(getRes.body);
    if (!csrf) {
        check(getRes, { 'CSRF chatbot bisa diparse': () => false });
        return;
    }

    const spoofedIp = fakeIp();

    const apiRes = http.post(
        `${BASE_URL}/chatbot/api/send/`,
        JSON.stringify({
            pesan: 'tes spoofing',
            sesi_id: `k6-spoof-${__ITER}`,
            jenis: 'umum',
        }),
        {
            headers: {
                ...DEFAULT_HEADERS,
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf,
                'X-Forwarded-For': spoofedIp, // ← payload spoofing
                'X-Real-IP': spoofedIp,        // ← payload spoofing
                'X-Originating-IP': spoofedIp, // ← payload spoofing
                'X-Client-IP': spoofedIp,      // ← payload spoofing
                Referer: `${BASE_URL}/chatbot/`,
            },
            jar,
            timeout: REQUEST_TIMEOUT,
        }
    );

    const body = apiRes.body || '';
    let parsed = {};
    try { parsed = JSON.parse(body); } catch (e) { /* not json */ }

    const isBlocked =
        apiRes.status === 429 ||
        body.includes('Terlalu') ||
        body.includes('tunggu') ||
        body.includes('rate limit') ||
        (parsed.error && /(rate|limit|tunggu|cooldown)/i.test(parsed.error));

    if (isBlocked) {
        spoofBlocked.add(1);
    } else if (apiRes.status === 200 && (parsed.respon_bot || '').length > 30) {
        spoofBypassed.add(1);
    }

    check(apiRes, {
        '[INFO] Server merespons (bukan crash)':
            (r) => r.status !== 0 && r.status < 500,
    });
}

export function teardown() {
    console.log('\n--- HASIL UJI IP SPOOFING ---');
    console.log('  Target: ≥ 21 dari 30 request harus tetap diblokir (≥ 70%)');
    console.log('  Kalau spoof_bypassed > 5 → CRITICAL: regresi rate_limiter.py');
    console.log('  Cek: get_client_ip() pakai REMOTE_ADDR untuk request');
    console.log('       dari internet, bukan trust XFF mentah.');
    console.log('-------------------------------\n');
}
