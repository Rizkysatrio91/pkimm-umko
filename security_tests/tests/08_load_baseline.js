// =============================================================================
// 08 — LOAD BASELINE (BUKAN STRESS / DOS)
// =============================================================================
// Tujuan: Ukur kapasitas server saat traffic NORMAL — supaya kalau ada
// regresi performa di masa depan, ada angka pembanding.
//
// PERINGATAN:
//   Test ini BUKAN stress test atau DoS. Beban yang dikirim disengaja
//   ringan: 5-10 VU selama 1-2 menit, hanya GET halaman publik. Tidak
//   menyentuh endpoint AI / OpenAI sama sekali.
//
//   JANGAN naikkan VU > 20 tanpa koordinasi dengan pemilik VPS.
//   VPS production biasanya dibatasi CPU/RAM, bisa OOM.
//
// Yang diukur:
//   - p50, p95, p99 response time per halaman
//   - Total throughput (req/s)
//   - Rate failure
//   - Saturation indicator (apakah p99 melonjak vs p50)
//
// Severity bila gagal:
//   HIGH    — p95 > 3 detik untuk halaman publik (UX rusak)
//   MEDIUM  — failure rate > 1% (server tidak stabil)
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/08_load_baseline.js
// =============================================================================

import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';

export const options = {
    // Ramp-up bertahap supaya server tidak kaget
    stages: [
        { duration: '15s', target: 3 },   // ramp ke 3 VU
        { duration: '30s', target: 5 },   // hold 5 VU
        { duration: '30s', target: 10 },  // hold 10 VU (peak)
        { duration: '15s', target: 0 },   // ramp down
    ],
    thresholds: {
        // Halaman publik harus < 3 detik di p95 walau saat peak load
        http_req_duration: ['p(95)<3000', 'p(99)<5000'],
        // Failure < 1%
        http_req_failed: ['rate<0.01'],
        // Min 95% checks lulus
        checks: ['rate>0.95'],
    },
};

const HALAMAN_PUBLIK = [
    '/',
    '/berita/',
    '/profil/visi-misi/',
    '/profil/sejarah/',
];

export default function () {
    // Pilih halaman acak supaya pattern tidak berurutan
    const path = HALAMAN_PUBLIK[Math.floor(Math.random() * HALAMAN_PUBLIK.length)];
    const res = http.get(`${BASE_URL}${path}`, {
        headers: DEFAULT_HEADERS,
        timeout: REQUEST_TIMEOUT,
        tags: { name: path }, // tag supaya bisa lihat metric per-URL
    });

    check(res, {
        [`${path}: status 200`]: (r) => r.status === 200,
        [`${path}: ada konten (body > 500 byte)`]:
            (r) => (r.body || '').length > 500,
    });

    // Think time: simulasi user real, bukan bot
    sleep(Math.random() * 2 + 1); // 1-3 detik
}
