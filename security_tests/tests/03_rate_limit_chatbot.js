// =============================================================================
// 03 — RATE LIMIT & PROTEKSI CHATBOT (ANTI OPENAI COST-BURNING)
// =============================================================================
// Tujuan: Verifikasi endpoint chatbot publik /chatbot/api/send/ punya
// proteksi berlapis yang mencegah penyerang membakar budget OpenAI lewat
// flooding.
//
// MODEL KEAMANAN CHATBOT (dari apps/chatbot/views.py — PENTING):
//   Endpoint ini SENGAJA @csrf_exempt (AJAX publik tanpa CSRF Django).
//   Sebagai gantinya, proteksi berlapis dijalankan BERURUTAN:
//     1. Same-origin check (Origin/Referer wajib domain sendiri) → 403
//     2. chat_token HMAC terikat IP+UA (core/security.py)         → 403
//     3. Rate limit: min-interval 1 dtk/IP + 4/menit (anonim)     → 429
//   Request hanya membakar OpenAI bila LOLOS ketiga lapis. Jadi proteksi
//   "cukup" selama request flooding ditolak di lapis MANA PUN (403 atau 429).
//
// CATATAN: versi test lama keliru memeriksa csrfmiddlewaretoken (mekanisme
//   form Django) yang TIDAK dipakai chatbot. Versi ini diperbaiki: parse
//   chat_token yang benar (data-chat-token), dan mencatat status tiap
//   request agar terlihat di lapis mana request ditolak.
//
// METRIK KEAMANAN UTAMA:
//   - openai_call_succeeded <= 4  → budget OpenAI aman (yang paling penting)
//   - blocked_total >= 16         → mayoritas flooding ditolak (403 ATAU 429)
//
// Severity bila gagal: CRITICAL (cost-burning → tagihan OpenAI membengkak).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/03_rate_limit_chatbot.js
// =============================================================================

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';

const blockedTotal = new Counter('blocked_total');             // ditolak (403/429/4xx)
const rateLimited429 = new Counter('rate_limited_429');        // ditolak rate limit
const tokenOriginBlocked = new Counter('token_or_origin_403'); // ditolak token/same-origin
const openaiSuccess = new Counter('openai_call_succeeded');    // jawaban AI sungguhan (mahal)

export const options = {
    vus: 1,
    iterations: 20,
    thresholds: {
        // METRIK UTAMA: budget OpenAI tidak boleh terbakar masif.
        'openai_call_succeeded': ['count<=4'],
        // Mayoritas flooding harus ditolak di lapis mana pun (403 atau 429).
        'blocked_total': ['count>=16'],
    },
};

// Ambil chat_token dari halaman chatbot. Template merender:
//   data-chat-token="{{ chat_token }}"  dan  chatbotPublik('{{ chat_token }}')
function getChatToken() {
    const res = http.get(`${BASE_URL}/chatbot/`, {
        headers: DEFAULT_HEADERS, timeout: REQUEST_TIMEOUT,
    });
    const body = res.body || '';
    let token = null;
    const m1 = body.match(/data-chat-token=["']([^"']+)["']/);
    const m2 = body.match(/chatbotPublik\(['"]([^'"]+)['"]\)/);
    const m3 = body.match(/chat_token["']?\s*[:=]\s*["']([^"']+)["']/);
    if (m1) token = m1[1];
    else if (m2) token = m2[1];
    else if (m3) token = m3[1];
    return token;
}

export default function () {
    const chatToken = getChatToken();

    // Bukan kegagalan keamanan kalau token ada — ini info kesiapan test.
    check(null, {
        '[INFO] chat_token bisa diparse dari halaman': () => chatToken !== null,
    });

    const payload = JSON.stringify({
        pesan: `test rate limit ${Date.now()}`,
        sesi_id: `k6-session-${__VU}-${__ITER}`,
        chat_token: chatToken,
    });

    const res = http.post(`${BASE_URL}/chatbot/api/send/`, payload, {
        headers: {
            ...DEFAULT_HEADERS,
            'Content-Type': 'application/json',
            'Referer': `${BASE_URL}/chatbot/`,
            'Origin': BASE_URL,
        },
        timeout: REQUEST_TIMEOUT,
    });

    const body = res.body || '';
    // Ditolak rate-limit: status 429, ATAU 200 dengan pesan batas/terlalu cepat
    // (server kadang balas 200 + rate_limited:true, lihat views.py LANGKAH 1).
    const is429 = res.status === 429 ||
        body.includes('Terlalu') || body.includes('batas penggunaan') ||
        body.includes('"rate_limited": true') || body.includes('"rate_limited":true');
    const is403 = res.status === 403;
    // "Mencapai OpenAI" = status 200, success:true, dan BUKAN respon rate-limit.
    // Termasuk template "belum memiliki informasi" — itu TETAP panggilan OpenAI
    // yang mengonsumsi token, jadi jujur dihitung sebagai succeeded.
    const reachedOpenAI = res.status === 200 &&
        body.includes('"success": true') && !is429;

    if (is429) { rateLimited429.add(1); blockedTotal.add(1); }
    else if (is403) { tokenOriginBlocked.add(1); blockedTotal.add(1); }
    else if (res.status >= 400) { blockedTotal.add(1); }
    if (reachedOpenAI) openaiSuccess.add(1);

    // Catat status tiap request supaya terlihat di lapis mana ditolak.
    let tag;
    if (reachedOpenAI) tag = '→ mencapai OpenAI (pakai token — sesuai limit 4/mnt)';
    else if (is429) tag = '■ 429 rate-limit (diblokir)';
    else if (is403) tag = '◧ 403 token/same-origin (diblokir)';
    else tag = `· status ${res.status}`;
    // potong body agar log ringkas
    const snippet = body.replace(/\s+/g, ' ').slice(0, 80);
    console.log(`  Req ${String(__ITER + 1).padStart(2)} [${res.status}] ${tag}  ${snippet}`);

    check(res, { '[INFO] Server merespons (bukan timeout)': () => res.status !== 0 });

    sleep(0.1);
}

export function teardown() {
    console.log('\n--- HASIL UJI PROTEKSI CHATBOT (ANTI COST-BURNING) ---');
    console.log('  openai_call_succeeded <= 4  → budget OpenAI AMAN (utama) ✓');
    console.log('  blocked_total >= 16         → mayoritas flooding ditolak ✓');
    console.log('  Ditolak via 403 (token/origin) ATAU 429 (rate-limit) sama-sama melindungi.');
    console.log('  Jika openai_call_succeeded == 20 → CRITICAL: proteksi jebol.');
    console.log('------------------------------------------------------');
}
