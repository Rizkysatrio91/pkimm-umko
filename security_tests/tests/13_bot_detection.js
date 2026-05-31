// =============================================================================
// 13 — DETEKSI BOT / PENGGUNA FIKTIF PADA CHATBOT PUBLIK
// =============================================================================
// Tujuan: Membuktikan chatbot publik MENOLAK pola akses otomatis (bot / skrip /
// pengguna fiktif) lewat 3 lapis pertahanan, TANPA menyentuh OpenAI sama sekali.
//
// LATAR (model keamanan dari apps/chatbot/views.py — terbaca di kode):
//   Sebelum sebuah pesan sampai ke OpenAI (LANGKAH 5), request harus lolos
//   pemeriksaan berikut, BERURUTAN. Ketiga lapis yang diuji di sini menolak
//   request JAUH SEBELUM OpenAI dipanggil:
//     Lapis 1 — Same-origin: Origin/Referer wajib domain sendiri  → 403
//     Lapis 5 — Honeypot: field 'website' wajib kosong (tak terlihat
//               manusia; bot otomatis cenderung mengisinya)        → 403
//     Lapis 8 — chat_token HMAC: bot yang langsung POST tanpa GET
//               halaman dulu tidak punya token sah                  → 403
//
// JAMINAN AMAN (penting): SEMUA request di test ini SENGAJA gagal di salah
//   satu lapis di atas, sehingga TIDAK ADA satu pun yang mencapai OpenAI.
//   Token OpenAI TIDAK terpakai. Ini dibuktikan oleh threshold
//   openai_call_succeeded == 0 (kalau sampai > 0, test GAGAL).
//
// PEMETAAN PESAN ERROR (persis dari views.py):
//   - same-origin gagal / honeypot terisi → 403 "Permintaan tidak diizinkan."
//   - chat_token invalid/absen           → 403 "Sesi chat kadaluarsa..."
//
// Severity bila gagal: CRITICAL (bot bisa menyalahgunakan chatbot).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/13_bot_detection.js
// =============================================================================

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';

const blockedBot = new Counter('bot_request_blocked');       // ditolak (target tinggi)
const openaiSuccess = new Counter('openai_call_succeeded');  // mencapai OpenAI (HARUS 0)

export const options = {
    vus: 1,
    iterations: 1,
    thresholds: {
        // JAMINAN UTAMA: test ini tidak boleh menyentuh OpenAI sama sekali.
        'openai_call_succeeded': ['count==0'],
        // Semua pengecekan harus lulus → ketiga lapis anti-bot bekerja.
        'checks': ['rate==1.0'],
    },
};

const API_URL = `${BASE_URL}/chatbot/api/send/`;

// Helper: kirim POST ke API chatbot dengan kontrol penuh atas header/payload,
// lalu klasifikasikan responnya. redirects:0 supaya status mentah terbaca.
function sendChat(payloadObj, extraHeaders) {
    const res = http.post(API_URL, JSON.stringify(payloadObj), {
        headers: { ...DEFAULT_HEADERS, 'Content-Type': 'application/json', ...extraHeaders },
        redirects: 0,
        timeout: REQUEST_TIMEOUT,
    });
    const body = res.body || '';
    const blocked = res.status === 403 || res.status === 429 || res.status === 413;
    // "Mencapai OpenAI" = dilayani penuh (200 + success:true + bukan rate-limit).
    const reachedOpenAI = res.status === 200 &&
        body.includes('"success": true') &&
        !body.includes('Terlalu') && !body.includes('batas penggunaan');
    if (reachedOpenAI) openaiSuccess.add(1);
    if (blocked) blockedBot.add(1);
    return { res, body, blocked, reachedOpenAI };
}

export default function () {
    console.log('\n=== UJI DETEKSI BOT / PENGGUNA FIKTIF (3 LAPIS) ===');
    console.log('  Semua skenario HARUS ditolak sebelum menyentuh OpenAI.\n');

    // ── LAPIS 1: SAME-ORIGIN ────────────────────────────────────────────────
    // (a) Bot/skrip/curl yang tidak mengirim Origin maupun Referer.
    {
        const { res, body } = sendChat(
            { pesan: 'apa itu IMM', sesi_id: `bot-noorigin-${Date.now()}` },
            { /* sengaja TANPA Origin & Referer */ },
        );
        const ok = res.status === 403 && body.includes('tidak diizinkan');
        check(null, {
            '[CRIT] L1 Same-origin: request tanpa Origin/Referer ditolak (403)': () => ok,
        });
        console.log(`  L1a tanpa Origin/Referer   → [${res.status}] ${ok ? '✓ ditolak' : '✗ LOLOS!'}`);
    }

    // (b) Situs jahat lain (cross-origin) memanggil endpoint kita.
    {
        const { res, body } = sendChat(
            { pesan: 'apa itu IMM', sesi_id: `bot-xorigin-${Date.now()}` },
            { 'Origin': 'https://evil.example.com', 'Referer': 'https://evil.example.com/' },
        );
        const ok = res.status === 403 && body.includes('tidak diizinkan');
        check(null, {
            '[CRIT] L1 Same-origin: request cross-origin (situs jahat) ditolak (403)': () => ok,
        });
        console.log(`  L1b cross-origin (evil)    → [${res.status}] ${ok ? '✓ ditolak' : '✗ LOLOS!'}`);
    }

    // ── LAPIS 5: HONEYPOT ───────────────────────────────────────────────────
    // Origin valid (lolos lapis 1) TAPI field jebakan 'website' terisi —
    // hanya bot otomatis yang mengisi field tak-terlihat ini.
    {
        const { res, body } = sendChat(
            {
                pesan: 'apa itu IMM',
                sesi_id: `bot-honeypot-${Date.now()}`,
                website: 'http://spam-bot.example',  // ← jebakan; manusia tak pernah isi
            },
            { 'Origin': BASE_URL, 'Referer': `${BASE_URL}/chatbot/` },
        );
        // Honeypot dicek SEBELUM verifikasi token, jadi pesannya "tidak diizinkan".
        const ok = res.status === 403 && body.includes('tidak diizinkan');
        check(null, {
            '[CRIT] L5 Honeypot: bot yang mengisi field jebakan ditolak (403)': () => ok,
        });
        console.log(`  L5  honeypot terisi        → [${res.status}] ${ok ? '✓ terdeteksi & ditolak' : '✗ LOLOS!'}`);
    }

    // ── LAPIS 8: chat_token HMAC ────────────────────────────────────────────
    // Origin valid + honeypot kosong, TAPI tanpa token sah → bot yang langsung
    // POST ke API tanpa membuka halaman chatbot lebih dulu.
    {
        // (a) Token absen sama sekali
        const r1 = sendChat(
            { pesan: 'apa itu IMM', sesi_id: `bot-notoken-${Date.now()}` },
            { 'Origin': BASE_URL, 'Referer': `${BASE_URL}/chatbot/` },
        );
        const ok1 = r1.res.status === 403 && r1.body.includes('kadaluarsa');
        check(null, {
            '[CRIT] L8 chat_token: request tanpa token sah ditolak (403)': () => ok1,
        });
        console.log(`  L8a tanpa chat_token       → [${r1.res.status}] ${ok1 ? '✓ ditolak' : '✗ LOLOS!'}`);

        // (b) Token palsu/dipalsukan
        const r2 = sendChat(
            {
                pesan: 'apa itu IMM',
                sesi_id: `bot-faketoken-${Date.now()}`,
                chat_token: 'ZmFrZQ.cGFsc3UtdGFuZGEtdGFuZ2Fu',  // token karangan
            },
            { 'Origin': BASE_URL, 'Referer': `${BASE_URL}/chatbot/` },
        );
        const ok2 = r2.res.status === 403 && r2.body.includes('kadaluarsa');
        check(null, {
            '[CRIT] L8 chat_token: token palsu/forged ditolak (403)': () => ok2,
        });
        console.log(`  L8b chat_token palsu       → [${r2.res.status}] ${ok2 ? '✓ ditolak' : '✗ LOLOS!'}`);
    }

    console.log('\n  Lulus semua → bot/pengguna fiktif ditolak, OpenAI tidak tersentuh ✓\n');
}

export function teardown() {
    console.log('--- HASIL UJI DETEKSI BOT ---');
    console.log('  openai_call_succeeded == 0  → chatbot TIDAK tersentuh (aman, hemat token) ✓');
    console.log('  Semua skenario bot ditolak di lapis same-origin / honeypot / chat_token.');
    console.log('  Catatan jujur: ini menaikkan "biaya" serangan bot, BUKAN jaminan 100%');
    console.log('  hanya-manusia (mustahil di endpoint publik). Untuk lebih ketat:');
    console.log('  Cloudflare Turnstile / wajib login — rencana setelah semhas.');
    console.log('-----------------------------');
}
