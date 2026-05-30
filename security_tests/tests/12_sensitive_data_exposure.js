// =============================================================================
// 12 — PERLINDUNGAN DATA SENSITIF (SSO MAHASISWA & DOKUMEN)
// =============================================================================
// Tujuan: Sistem ini menyimpan data pribadi mahasiswa (NPM, nama, tanggal
// lahir, alamat, no HP — diambil dari SSO UMKO) dan dokumen pendaftaran.
// Test ini membuktikan data tersebut TIDAK bisa diakses tanpa autentikasi &
// otorisasi yang benar, serta tidak bocor lewat endpoint/IDOR/direktori.
//
// Yang diuji:
//   A. Endpoint API kader & lookup SSO menolak akses anonim (302/403/401/404).
//   B. IDOR: menebak ID biodata/dokumen lewat URL tidak mengembalikan data
//      milik orang lain (harus redirect login / 403 / 404 — bukan 200 berisi
//      data pribadi).
//   C. Direktori media (KTM/dokumen) tidak bisa di-listing.
//   D. Respons tidak mengandung kebocoran pola data sensitif (NPM/NIK/email)
//      saat diakses anonim.
//
// Referensi: core/decorators.py & core/mixins.py (kontrol akses berbasis role),
//   apps/accounts/models.py AuditLog (akses SSO dicatat), core/rate_limiter.py.
//
// Test ini PASIF & read-only (hanya GET anonim) — aman untuk production.
//
// Severity bila gagal: CRITICAL (kebocoran data pribadi — pelanggaran privasi).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/12_sensitive_data_exposure.js
// =============================================================================

import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';

export const options = {
    vus: 1,
    iterations: 1,
    thresholds: {
        checks: ['rate==1.0'],
    },
};

// A. Endpoint yang menyajikan/mengelola data sensitif — harus tertutup anonim.
const SENSITIVE_ENDPOINTS = [
    '/admin-dashboard/kader/',
    '/admin-dashboard/users/',
    '/admin-dashboard/pendaftaran/',
    '/kader/biodata/',
    '/accounts/profile/',
    '/api/',
    '/kader/api/',
];

// B. Pola IDOR — coba akses objek by-id sebagai anonim.
//    (Path disusun dari konvensi admin-dashboard; bila tidak ada → 404, aman.)
const IDOR_PATHS = [
    '/admin-dashboard/kader/1/',
    '/admin-dashboard/kader/2/',
    '/admin-dashboard/kader/1/edit/',
    '/admin-dashboard/users/1/',
    '/admin-dashboard/pendaftaran/1/',
];

// C. Direktori media yang mungkin berisi dokumen pribadi — tidak boleh listing.
const MEDIA_DIRS = [
    '/media/',
    '/media/profil/',
    '/media/berita/',
    '/media/dokumen_pengetahuan/',
    '/media/ckeditor/',
];

// D. Pola data sensitif yang TIDAK boleh muncul di respons anonim.
const SENSITIVE_PATTERNS = [
    { re: /\b\d{16}\b/, name: 'NIK 16 digit' },
    { re: /id_program_studi/i, name: 'field SSO id_program_studi' },
    { re: /tanggal_lahir/i, name: 'field tanggal_lahir' },
    { re: /alamat_domisili/i, name: 'field alamat_domisili' },
];

function isProtected(status) {
    // Aman bila tidak menyajikan konten ke anonim.
    return [301, 302, 401, 403, 404].includes(status);
}

export default function () {
    console.log('\n=== A. ENDPOINT DATA SENSITIF (harus tertutup anonim) ===');
    for (const path of SENSITIVE_ENDPOINTS) {
        const res = http.get(`${BASE_URL}${path}`, {
            headers: DEFAULT_HEADERS, redirects: 0, timeout: REQUEST_TIMEOUT,
        });
        const exposed = res.status === 200;
        check(res, {
            [`[CRIT] ${path}: tidak menyajikan data tanpa auth`]: () => !exposed,
            [`[MED]  ${path}: tidak crash 500`]: () => res.status < 500,
        });
        console.log(`  [${res.status}] ${path.padEnd(40)} ${exposed ? '✗ TERBUKA' : '✓ aman'}`);
    }

    console.log('\n=== B. UJI IDOR (akses objek by-id sebagai anonim) ===');
    for (const path of IDOR_PATHS) {
        const res = http.get(`${BASE_URL}${path}`, {
            headers: DEFAULT_HEADERS, redirects: 0, timeout: REQUEST_TIMEOUT,
        });
        const exposed = res.status === 200;
        check(res, {
            [`[CRIT] ${path}: objek tidak bocor tanpa auth`]: () => !exposed,
        });
        console.log(`  [${res.status}] ${path.padEnd(40)} ${exposed ? '✗ BOCOR' : '✓ aman'}`);
    }

    console.log('\n=== C. DIREKTORI MEDIA (tidak boleh listing) ===');
    for (const path of MEDIA_DIRS) {
        const res = http.get(`${BASE_URL}${path}`, {
            headers: DEFAULT_HEADERS, redirects: 0, timeout: REQUEST_TIMEOUT,
        });
        const body = res.body || '';
        // Listing terbuka bila status 200 DAN body terlihat seperti index direktori.
        const looksLikeListing =
            res.status === 200 &&
            (/Index of/i.test(body) || /<a href=["'][^"']+\.(pdf|jpg|jpeg|png|webp|docx)/i.test(body));
        check(res, {
            [`[HIGH] ${path}: tidak bisa di-listing`]: () => !looksLikeListing,
        });
        const tag = looksLikeListing ? '✗ LISTING TERBUKA' : (isProtected(res.status) ? '✓ aman' : '? cek');
        console.log(`  [${res.status}] ${path.padEnd(40)} ${tag}`);
    }

    console.log('\n=== D. KEBOCORAN POLA DATA SENSITIF (respons anonim) ===');
    // Periksa beberapa halaman publik + endpoint API anonim.
    const probe = ['/', '/berita/', '/api/', '/kader/api/'];
    for (const path of probe) {
        const res = http.get(`${BASE_URL}${path}`, {
            headers: DEFAULT_HEADERS, redirects: 1, timeout: REQUEST_TIMEOUT,
        });
        const body = res.body || '';
        SENSITIVE_PATTERNS.forEach((p) => {
            const leaked = res.status === 200 && p.re.test(body);
            check(null, {
                [`[CRIT] ${path}: tidak membocorkan ${p.name}`]: () => !leaked,
            });
            if (leaked) console.log(`  [${res.status}] ${path.padEnd(40)} ⚠ bocor: ${p.name}`);
        });
        console.log(`  [${res.status}] ${path.padEnd(40)} diperiksa`);
    }

    console.log('\n  Lulus semua CRIT → data sensitif terlindungi ✓\n');
}
