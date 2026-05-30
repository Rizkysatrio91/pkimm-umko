// =============================================================================
// 06 — ENDPOINT ENUMERATION (INFO DISCLOSURE)
// =============================================================================
// Tujuan: Cek bahwa endpoint sensitif TIDAK exposed ke publik tanpa auth.
// Test pasif — hanya GET tanpa credential, lihat response status.
//
// Yang diharapkan untuk setiap endpoint protected:
//   - 302 → redirect ke /accounts/login/    (perilaku Django default)
//   - 403 → forbidden                       (juga oke)
//   - 404 → tidak ada endpoint              (oke kalau memang tidak ada)
//
// Yang TIDAK boleh:
//   - 200 OK pada endpoint admin/internal   → auth bypass!
//   - 500 → exception expose stack trace
//
// Severity:
//   CRITICAL — admin endpoint return 200 tanpa auth
//   HIGH     — debug page (.env, DEBUG=True traceback) ter-expose
//   MEDIUM   — API endpoint butuh auth tapi return 200
//   LOW      — endpoint info (robots.txt, sitemap) terbuka — biasa
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/06_endpoint_enumeration.js
// =============================================================================

import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';

export const options = {
    vus: 1,
    iterations: 1,
};

// Endpoint admin yang HARUS protected
const ENDPOINT_PROTECTED = [
    '/admin-dashboard/',
    '/admin-dashboard/users/',
    '/admin-dashboard/kader/',
    '/admin-dashboard/pendaftaran/',
    '/admin-dashboard/periode-dad/',
    '/admin-dashboard/kelompok/',
    '/admin-dashboard/rundown/',
    '/admin-dashboard/chatbot/dataset/',
    '/admin-dashboard/chatbot/dokumen/',
    '/admin-dashboard/profil/sambutan/',
    '/admin-dashboard/laporan/',
    '/admin-dashboard/kelulusan/',
    '/panitia/dashboard/',
    '/panitia/interview/',
    '/panitia/aktivitas/',
    '/panitia/absensi/',
    '/penulis/dashboard/',
    '/penulis/berita/tulis/',
    '/kader/dashboard/',
    '/kader/biodata/',
    '/notifikasi/',
    '/django-admin/',
    '/accounts/profile/',
];

// Endpoint info disclosure — kalau berhasil → CRITICAL
const ENDPOINT_FORBIDDEN = [
    '/.env',
    '/.git/config',
    '/.git/HEAD',
    '/manage.py',
    '/config/settings/base.py',
    '/config/settings/production.py',
    '/requirements.txt',
    '/db.sqlite3',
    '/media/dokumen_pengetahuan/',  // direktori listing
    '/static/',                     // direktori listing
    '/api/',                        // index API
    '/__debug__/',                  // django-debug-toolbar
    '/swagger/',
    '/redoc/',
    '/server-status',               // Apache info leak
    '/server-info',
    '/.DS_Store',
    '/wp-admin/',                   // bukti scanning attack surface
    '/phpmyadmin/',
];

export default function () {
    console.log('\n=== ENDPOINT PROTECTED (harus 302/403/401, BUKAN 200) ===');
    for (const path of ENDPOINT_PROTECTED) {
        const res = http.get(`${BASE_URL}${path}`, {
            headers: DEFAULT_HEADERS,
            redirects: 0,
            timeout: REQUEST_TIMEOUT,
        });

        // Anggap aman: 302 (redirect to login), 403, 401
        // Bahaya: 200 (auth bypass), 500 (exception leak)
        const safe = [302, 403, 401, 404].includes(res.status);
        const dangerous = res.status === 200;

        check(res, {
            [`[CRIT] ${path}: tidak return 200 tanpa auth`]: () => !dangerous,
            [`[MED]  ${path}: tidak crash 500`]: () => res.status < 500,
        });

        const tag = dangerous ? '✗ EXPOSED' : (safe ? '✓ aman' : '? cek');
        console.log(`  [${res.status}] ${path.padEnd(45)} ${tag}`);
    }

    console.log('\n=== INFO DISCLOSURE PATH (semua harus 404/403) ===');
    for (const path of ENDPOINT_FORBIDDEN) {
        const res = http.get(`${BASE_URL}${path}`, {
            headers: DEFAULT_HEADERS,
            redirects: 0,
            timeout: REQUEST_TIMEOUT,
        });

        // Aman: 404 atau 403. Bahaya: 200 (file exposed) atau 301/302 ke
        // file (juga leak).
        const exposed = res.status === 200 ||
                        (res.status === 301 || res.status === 302);

        check(res, {
            [`[CRIT] ${path}: tidak exposed (status ${res.status})`]:
                () => !exposed,
        });

        const tag = exposed ? '✗ BOCOR!' : '✓ aman';
        console.log(`  [${res.status}] ${path.padEnd(45)} ${tag}`);
    }

    // Cek DEBUG=True leak — coba akses URL yang tidak ada, lihat apakah
    // response berisi traceback Django
    console.log('\n=== CEK DEBUG=True LEAK ===');
    const debugRes = http.get(
        `${BASE_URL}/this-url-does-not-exist-${Date.now()}/`,
        { headers: DEFAULT_HEADERS, timeout: REQUEST_TIMEOUT }
    );
    const body = debugRes.body || '';
    const debugLeak =
        body.includes('Traceback') ||
        body.includes('DEBUG = True') ||
        body.includes('django.views.debug') ||
        body.includes('Request Method:');

    check(debugRes, {
        '[CRIT] DEBUG=True tidak boleh aktif di production':
            () => !debugLeak,
    });

    console.log(`  DEBUG leak  : ${debugLeak ? '✗ AKTIF (BAHAYA)' : '✓ tidak aktif'}`);
    console.log(`  404 status  : ${debugRes.status} (seharusnya 404)`);
}
