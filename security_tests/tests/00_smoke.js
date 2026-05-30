// =============================================================================
// 00 — SMOKE TEST
// =============================================================================
// Tujuan: Verifikasi target hidup, response time wajar, halaman publik utama
// kembali HTTP 200. Ini WAJIB lulus sebelum menjalankan test lain — kalau
// smoke gagal, hasil test lain tidak bermakna.
//
// Severity bila gagal: blocker (server tidak siap diuji).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/00_smoke.js
// =============================================================================

import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT, P95_THRESHOLD_MS } from '../config.js';

export const options = {
    vus: 1,
    iterations: 5, // 5 putaran cukup untuk cek stabilitas
    thresholds: {
        // Semua check harus 100% lulus
        checks: ['rate==1.0'],
        // p95 response time tidak boleh > 1.5 detik
        http_req_duration: [`p(95)<${P95_THRESHOLD_MS}`],
        // Rate failure HTTP < 1%
        http_req_failed: ['rate<0.01'],
    },
};

// Endpoint dibagi 2: read-only (tidak perlu CSRF cookie) vs form-bearing
// (WAJIB ada CSRF cookie supaya form POST bisa berfungsi).
const ENDPOINTS_PUBLIK = [
    { path: '/',                            label: 'Beranda',              hasForm: false },
    { path: '/berita/',                     label: 'Daftar Berita',        hasForm: false },
    { path: '/profil/visi-misi/',           label: 'Visi & Misi',          hasForm: false },
    { path: '/profil/sejarah/',             label: 'Sejarah',              hasForm: false },
    { path: '/profil/struktur-organisasi/', label: 'Struktur Organisasi',  hasForm: false },
    // /chatbot/ pakai AJAX + X-CSRFToken header (bukan <form> klasik) →
    // hasForm:false di sini. Proteksi CSRF endpoint /chatbot/api/send/
    // diuji terpisah di tests/05_csrf_protection.js.
    { path: '/chatbot/',                    label: 'Chatbot Publik UI',    hasForm: false },
    { path: '/accounts/login/',             label: 'Halaman Login',        hasForm: true  },
    { path: '/accounts/register/',          label: 'Halaman Register',     hasForm: true  },
];

export default function () {
    for (const ep of ENDPOINTS_PUBLIK) {
        const res = http.get(`${BASE_URL}${ep.path}`, {
            headers: DEFAULT_HEADERS,
            timeout: REQUEST_TIMEOUT,
        });

        const checks = {
            [`${ep.label}: status 200`]: (r) => r.status === 200,
            [`${ep.label}: bukan halaman error`]: (r) =>
                !r.body || (!r.body.includes('Server Error') && !r.body.includes('Page not found')),
        };

        // Hanya halaman dengan form yang WAJIB punya CSRF token di body.
        // (Set-Cookie csrftoken kadang tidak dikirim ulang kalau cookie sudah ada
        // di request sebelumnya — yang penting form punya csrfmiddlewaretoken.)
        if (ep.hasForm) {
            checks[`${ep.label}: ada csrfmiddlewaretoken di form`] = (r) =>
                /name=["']csrfmiddlewaretoken["']/.test(r.body || '');
        }

        check(res, checks);
        sleep(0.3); // jeda kecil supaya tidak spam server saat smoke
    }
}

export function handleSummary(data) {
    return {
        'stdout': textSummary(data),
        'reports/00_smoke.json': JSON.stringify(data, null, 2),
    };
}

function textSummary(data) {
    const lines = [];
    lines.push('');
    lines.push('═══════════════════════════════════════════════════════════════');
    lines.push('  SMOKE TEST — PK IMM FTIK UMKO');
    lines.push('═══════════════════════════════════════════════════════════════');
    lines.push(`  Target          : ${BASE_URL}`);
    lines.push(`  Iterasi         : ${data.metrics.iterations.values.count}`);
    lines.push(`  HTTP request    : ${data.metrics.http_reqs.values.count}`);
    lines.push(`  HTTP failed     : ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%`);
    lines.push(`  p95 duration    : ${data.metrics.http_req_duration.values['p(95)'].toFixed(0)} ms`);
    lines.push(`  Checks pass     : ${(data.metrics.checks.values.rate * 100).toFixed(2)}%`);
    lines.push('═══════════════════════════════════════════════════════════════');
    lines.push('');
    return lines.join('\n');
}
