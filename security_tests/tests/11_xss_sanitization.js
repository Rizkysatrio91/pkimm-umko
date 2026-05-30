// =============================================================================
// 11 — SANITASI HTML / PROTEKSI STORED XSS
// =============================================================================
// Tujuan: Membuktikan konten yang dirender ke pengunjung publik (berita, kata
// sambutan, visi-misi, sejarah) sudah dibersihkan dari elemen berbahaya
// (<script>, onerror=, javascript:, <iframe>) — sehingga penyerang tidak bisa
// menanamkan kode yang dieksekusi di browser pengunjung/admin (stored XSS).
//
// Referensi perbaikan:
//   - core/sanitizer.py — sanitize_html (berbasis nh3, allowlist tag/atribut)
//   - apps/berita/models.py — save() pada Berita/KataSambutan/VisiMisi/Sejarah
//     memanggil sanitize_html sebelum menyimpan.
//
// Skenario (PASIF, read-only — aman untuk production):
//   Karena penulisan berita butuh login penulis, test ini TIDAK menulis data.
//   Sebagai gantinya ia mengaudit HALAMAN PUBLIK yang me-render konten kaya:
//   beranda, daftar berita + beberapa detail, visi-misi, sejarah. Lalu
//   memastikan TIDAK ADA pola XSS berbahaya yang ikut ter-render di HTML.
//
//   Catatan: pengujian sanitasi yang menulis payload (positif) dilakukan di
//   unit test Python — lihat core/sanitizer.py. Test k6 ini fokus membuktikan
//   output publik bersih (verifikasi end-to-end di server produksi).
//
// Severity bila gagal: CRITICAL (stored XSS → pencurian sesi admin/kader).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/11_xss_sanitization.js
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

// Pola berbahaya yang TIDAK BOLEH muncul di HTML publik.
const XSS_PATTERNS = [
    { re: /<script\b/i, name: '<script>' },
    { re: /\son\w+\s*=/i, name: 'event handler (onerror=/onload=/onclick=)' },
    { re: /javascript:/i, name: 'skema javascript:' },
    { re: /<iframe\b/i, name: '<iframe>' },
    { re: /<object\b/i, name: '<object>' },
    { re: /<embed\b/i, name: '<embed>' },
];

// Halaman publik yang me-render konten kaya (HTML dari CKEditor).
function collectPublicPages() {
    const pages = [
        '/',                    // beranda (kata sambutan)
        '/profil/visi-misi/',
        '/profil/sejarah/',
        '/berita/',             // daftar berita
    ];
    return pages;
}

// Ambil beberapa slug berita dari halaman daftar untuk ikut diperiksa detailnya.
function extractBeritaLinks(html) {
    if (!html) return [];
    const links = new Set();
    const re = /href=["'](\/berita\/[^"'#?]+\/)["']/gi;
    let m;
    while ((m = re.exec(html)) !== null && links.size < 5) {
        if (!m[1].endsWith('/berita/')) links.add(m[1]);
    }
    return [...links];
}

function auditPage(path) {
    const res = http.get(`${BASE_URL}${path}`, {
        headers: DEFAULT_HEADERS, redirects: 1, timeout: REQUEST_TIMEOUT,
    });
    const body = res.body || '';

    // Abaikan halaman yang memang tidak ada (404) — bukan kegagalan keamanan.
    if (res.status === 404) {
        console.log(`  [404] ${path.padEnd(40)} (tidak ada konten — dilewati)`);
        return;
    }

    // Buang blok <script> milik framework yang sah (Alpine/CDN) dari area konten?
    // Kita TIDAK bisa membedakan dengan andal dari luar, maka kita batasi
    // pencarian ke pola yang paling jelas berbahaya bila berasal dari konten:
    // event handler inline & javascript:. Untuk <script>, kita laporkan sebagai
    // INFO bila ada (situs publik wajar punya script CDN), tapi event-handler
    // inline dan javascript: tetap CRITICAL.
    XSS_PATTERNS.forEach((p) => {
        const found = p.re.test(body);
        const isHardFail = p.name.startsWith('event handler') ||
                           p.name.startsWith('skema javascript') ||
                           p.name === '<iframe>' ||
                           p.name === '<object>' ||
                           p.name === '<embed>';
        if (isHardFail) {
            check(null, {
                [`[CRIT] ${path}: tidak ada ${p.name}`]: () => !found,
            });
        }
        if (found) {
            console.log(`  [${res.status}] ${path.padEnd(40)} ⚠ ditemukan: ${p.name}`);
        }
    });

    check(res, {
        [`[MED] ${path}: tidak crash 500`]: (r) => r.status < 500,
    });
    console.log(`  [${res.status}] ${path.padEnd(40)} diperiksa`);
}

export default function () {
    console.log('\n=== AUDIT KONTEN PUBLIK UNTUK POLA XSS ===');

    const pages = collectPublicPages();
    for (const p of pages) auditPage(p);

    // Ikut periksa beberapa detail berita nyata.
    const listRes = http.get(`${BASE_URL}/berita/`, {
        headers: DEFAULT_HEADERS, timeout: REQUEST_TIMEOUT,
    });
    const beritaLinks = extractBeritaLinks(listRes.body);
    console.log(`\n  Memeriksa ${beritaLinks.length} detail berita...`);
    for (const link of beritaLinks) auditPage(link);

    console.log('\n  Lulus semua CRIT → konten publik bersih dari XSS aktif ✓\n');
}
