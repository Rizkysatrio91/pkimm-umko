// =============================================================================
// Konfigurasi bersama untuk seluruh test k6 keamanan PK IMM FTIK UMKO.
// Ubah BASE_URL via environment variable, jangan hard-code:
//
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/00_smoke.js
//
// Default sengaja diarahkan ke localhost supaya kalau lupa set env, tidak
// langsung menghantam production.
// =============================================================================

export const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

// User-Agent yang jelas menyebut "k6-pentest-internal" agar di server log
// terlihat traffic ini berasal dari uji keamanan internal — bukan attacker.
// Jangan gunakan UA browser asli; itu menyamarkan asal traffic.
export const USER_AGENT = `k6-pentest-internal/1.0 (PK-IMM-FTIK-UMKO; +rizkysatrio)`;

// Header default untuk semua request
export const DEFAULT_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/json',
    'Accept-Language': 'id-ID,id;q=0.9,en;q=0.8',
};

// Timeout per request (detik). Production VPS kadang lambat saat OpenAI
// nge-call upstream, jadi 30 detik aman.
export const REQUEST_TIMEOUT = '30s';

// Batas threshold p95 response time (ms) untuk halaman publik biasa.
// Kalau lebih lambat dari ini saat baseline → ada masalah performa.
export const P95_THRESHOLD_MS = 1500;

// Kredensial demo yang HANYA boleh dipakai di environment dev/staging.
// Di production semua password ini WAJIB sudah diganti (lihat PRD §8).
// Test yang butuh login akan skip kalau BASE_URL berisi domain produksi.
export const DEMO_CREDS = {
    admin: { username: 'admin', password: 'admin123' },
    panitia: { username: 'panitia', password: 'panitia123' },
    penulis: { username: 'penulis', password: 'penulis123' },
};

// Daftar host yang dianggap PRODUCTION — test destruktif (login brute,
// upload besar, dll) akan otomatis di-abort saat BASE_URL match salah satu.
export const PROD_HOSTS = [
    'pkimm-ftik-umko.my.id',
    'www.pkimm-ftik-umko.my.id',
];

export function isProduction() {
    try {
        const u = new URL(BASE_URL);
        return PROD_HOSTS.includes(u.hostname);
    } catch (e) {
        return false;
    }
}
