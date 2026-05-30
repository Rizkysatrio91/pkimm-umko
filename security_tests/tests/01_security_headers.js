// =============================================================================
// 01 — SECURITY HEADERS AUDIT
// =============================================================================
// Tujuan: Verifikasi response menyertakan header keamanan dasar.
// Ini test pasif — hanya GET satu kali, tidak membebani server.
//
// Header yang diperiksa:
//   - X-Frame-Options       : cegah clickjacking (Django: 'DENY' default)
//   - X-Content-Type-Options: cegah MIME sniffing ('nosniff')
//   - Strict-Transport-Sec  : enforce HTTPS (HSTS — hanya saat USE_HTTPS=True)
//   - Referrer-Policy       : kontrol kebocoran URL ke 3rd party (opsional)
//   - Content-Security-Policy: cegah XSS (BELUM ada di project — info)
//   - Server header         : seharusnya tidak expose versi (Django/Nginx)
//   - Set-Cookie Secure/HttpOnly: untuk csrftoken & sessionid
//
// Severity:
//   CRITICAL  — HSTS hilang saat HTTPS aktif, atau Set-Cookie Secure hilang
//   HIGH      — X-Frame-Options hilang
//   MEDIUM    — X-Content-Type-Options hilang, atau CSP hilang
//   LOW       — Referrer-Policy hilang, Server header expose versi
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/01_security_headers.js
// =============================================================================

import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';

export const options = {
    vus: 1,
    iterations: 1,
};

export default function () {
    const isHttps = BASE_URL.startsWith('https://');
    const res = http.get(`${BASE_URL}/`, {
        headers: DEFAULT_HEADERS,
        timeout: REQUEST_TIMEOUT,
    });

    // Normalisasi nama header (lower-case) — k6 case-sensitive
    const headers = {};
    for (const [k, v] of Object.entries(res.headers || {})) {
        headers[k.toLowerCase()] = v;
    }

    const xfo = headers['x-frame-options'] || '';
    const xcto = headers['x-content-type-options'] || '';
    const hsts = headers['strict-transport-security'] || '';
    const referrer = headers['referrer-policy'] || '';
    const csp = headers['content-security-policy'] || '';
    const xxp = headers['x-xss-protection'] || '';
    const server = headers['server'] || '';
    const setCookie = (headers['set-cookie'] || '').toLowerCase();

    check(res, {
        '[CRIT] X-Frame-Options di-set (anti clickjacking)':
            () => xfo.toUpperCase() === 'DENY' || xfo.toUpperCase() === 'SAMEORIGIN',

        '[MED]  X-Content-Type-Options: nosniff':
            () => xcto.toLowerCase() === 'nosniff',

        '[CRIT] HSTS aktif (jika HTTPS)':
            () => !isHttps || hsts.includes('max-age='),

        '[HIGH] HSTS includeSubDomains (jika HTTPS)':
            () => !isHttps || hsts.toLowerCase().includes('includesubdomains'),

        '[MED]  Referrer-Policy di-set':
            () => referrer.length > 0,

        '[MED]  Content-Security-Policy di-set':
            () => csp.length > 0,

        '[LOW]  Server header tidak expose versi exact':
            () => !/(\d+\.\d+\.\d+)/.test(server),

        '[CRIT] Set-Cookie csrftoken HttpOnly atau ada Secure (jika HTTPS)':
            () => !setCookie.includes('csrftoken') ||
                  (!isHttps || setCookie.includes('secure')),

        '[CRIT] Set-Cookie sessionid HttpOnly':
            () => !setCookie.includes('sessionid') || setCookie.includes('httponly'),
    });

    // Tampilkan nilai header agar tester bisa bandingkan dengan baseline
    console.log('\n--- HEADER YANG DITERIMA ---');
    console.log(`  X-Frame-Options          : ${xfo || '(KOSONG)'}`);
    console.log(`  X-Content-Type-Options   : ${xcto || '(KOSONG)'}`);
    console.log(`  Strict-Transport-Security: ${hsts || '(KOSONG)'}`);
    console.log(`  Referrer-Policy          : ${referrer || '(KOSONG)'}`);
    console.log(`  Content-Security-Policy  : ${csp ? csp.slice(0, 80) + '...' : '(KOSONG)'}`);
    console.log(`  X-XSS-Protection         : ${xxp || '(KOSONG)'}`);
    console.log(`  Server                   : ${server || '(KOSONG)'}`);
    console.log(`  HTTPS aktif              : ${isHttps ? 'YA' : 'TIDAK'}`);
    console.log('-----------------------------\n');
}
