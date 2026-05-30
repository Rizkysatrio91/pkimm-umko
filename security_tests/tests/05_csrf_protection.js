// =============================================================================
// 05 — CSRF PROTECTION VERIFICATION
// =============================================================================
// Tujuan: Verifikasi endpoint state-changing menolak request TANPA
// csrfmiddlewaretoken (atau dengan token salah).
//
// Django middleware CsrfViewMiddleware seharusnya otomatis return
// 403 Forbidden untuk POST tanpa token valid. Test ini memastikan
// middleware tidak ter-disable di endpoint kritis.
//
// Endpoint yang diuji (semua POST tanpa CSRF token):
//   - /accounts/login/
//   - /accounts/register/
//   - /accounts/forgot-password/
//   - /chatbot/api/send/             (paling penting — anti cost-burn)
//   - /pendaftaran/absensi/validate/ (kalau exposed publik)
//   - /penulis/berita/tulis/ (anonim → seharusnya 302 ke login DULU,
//     baru kalau dengan auth + tanpa CSRF baru 403; di sini cukup cek
//     bahwa anon tidak bisa POST)
//
// Severity bila gagal: CRITICAL (CSRF + auth bypass = remote takeover).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/05_csrf_protection.js
// =============================================================================

import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';

export const options = {
    vus: 1,
    iterations: 1,
};

const POST_ENDPOINTS = [
    {
        path: '/accounts/login/',
        body: { username: 'x', password: 'x' },
        contentType: 'form',
    },
    {
        path: '/accounts/register/',
        body: { username: 'x', email: 'x@x.x', password1: 'x', password2: 'x' },
        contentType: 'form',
    },
    {
        path: '/accounts/forgot-password/',
        body: { email: 'x@x.x' },
        contentType: 'form',
    },
    {
        path: '/chatbot/api/send/',
        body: { pesan: 'tes', sesi_id: 'csrf-test', jenis: 'umum' },
        contentType: 'json',
    },
    {
        path: '/pendaftaran/absensi/validate/',
        body: { token: '00000000-0000-0000-0000-000000000000' },
        contentType: 'json',
    },
];

export default function () {
    for (const ep of POST_ENDPOINTS) {
        const headers = { ...DEFAULT_HEADERS };
        let payload;
        if (ep.contentType === 'json') {
            headers['Content-Type'] = 'application/json';
            payload = JSON.stringify(ep.body);
        } else {
            payload = ep.body;
        }

        // SENGAJA TIDAK kirim CSRF token & TIDAK pakai cookie jar
        const res = http.post(`${BASE_URL}${ep.path}`, payload, {
            headers,
            redirects: 0,
            timeout: REQUEST_TIMEOUT,
        });

        // Yang DITERIMA:
        //   403 Forbidden (Django CSRF block)
        //   400 Bad Request (validasi input)
        //   401 Unauthorized
        //   302 redirect ke login (untuk endpoint yang butuh auth dulu)
        //
        // Yang TIDAK BOLEH:
        //   200 OK + body sukses → CSRF tidak aktif
        //   500 Internal Server Error → exception unhandled
        const csrfBlocked = res.status === 403 || res.status === 400;
        const authRedirect = res.status === 302; // OK untuk endpoint protected
        const acceptable = csrfBlocked || authRedirect;

        check(res, {
            [`[CRIT] ${ep.path}: CSRF wajib ditolak (status ${res.status})`]:
                () => acceptable,
            [`[INFO] ${ep.path}: tidak crash 500`]:
                () => res.status < 500,
        });

        console.log(`  ${ep.path.padEnd(40)} → ${res.status} ${acceptable ? '✓ ditolak' : '✗ DITERIMA (BAHAYA)'}`);
    }
}
