// =============================================================================
// 03 — RATE LIMIT CHATBOT (ANTI OPENAI COST-BURNING)
// =============================================================================
// Tujuan: Verifikasi endpoint /chatbot/api/send/ MENOLAK request burst
// dari user anonim. Ini adalah test paling penting untuk project ini —
// commit 7a65151 dibuat khusus untuk menutup celah ini setelah pentest k6
// pertama berhasil membakar token OpenAI.
//
// Lapisan pertahanan yang seharusnya aktif (per RateLimiter dan
// BudgetLimiter di core/):
//   1. check_min_interval — minimal 2-3 detik antar pesan per IP/user
//   2. check_chatbot_limit — N request per menit per IP (anonim lebih ketat)
//   3. BudgetLimiter.can_use_ai — cap biaya OpenAI bulanan ($1.25 default)
//
// Skenario:
//   1 VU mengirim 20 pesan ke chatbot publik secepat mungkin (no sleep).
//   Server seharusnya:
//     - Request #1-2: HTTP 200 dengan jawaban
//     - Request #3+ (terlalu cepat): HTTP 429 / pesan "tunggu N detik"
//     - Setelah quota habis: HTTP 429 / pesan "rate limit tercapai"
//
// Kalau >50% request berhasil mendapat respons OpenAI → CRITICAL,
// celah cost-burning masih ada.
//
// Severity bila gagal: CRITICAL (token OpenAI bisa dibakar habis).
//
// Cara jalan:
//   k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/03_rate_limit_chatbot.js
// =============================================================================

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE_URL, DEFAULT_HEADERS, REQUEST_TIMEOUT } from '../config.js';
import { parseCsrfToken } from '../lib/helpers.js';

export const options = {
    vus: 1,
    iterations: 20, // 20 burst tanpa sleep
    thresholds: {
        // ≥ 80% dari 20 request HARUS ditolak (rate-limited).
        // Hanya boleh ada ≤ 4 request yang sukses dapat jawaban OpenAI.
        'rate_limited_chatbot': ['count>=16'],
        'openai_call_succeeded': ['count<=4'],
    },
};

const rateLimitedChatbot = new Counter('rate_limited_chatbot');
const openaiCallSucceeded = new Counter('openai_call_succeeded');

// Pesan singkat — kalau benar-benar sampai ke OpenAI, biaya per call kecil
// (~$0.0001 dengan gpt-4o-mini). Maks total kerugian test ini < $0.001.
const PESAN_TEST = 'apa itu IMM?';

export default function () {
    const jar = http.cookieJar();

    // GET halaman chatbot dulu untuk dapatkan csrftoken
    const getRes = http.get(`${BASE_URL}/chatbot/`, {
        headers: DEFAULT_HEADERS,
        jar,
        timeout: REQUEST_TIMEOUT,
    });
    const csrf = parseCsrfToken(getRes.body);

    if (!csrf) {
        check(getRes, { 'CSRF token chatbot bisa diparse': () => false });
        return;
    }

    // POST ke API chatbot dengan minimal payload
    const apiRes = http.post(
        `${BASE_URL}/chatbot/api/send/`,
        JSON.stringify({
            pesan: PESAN_TEST,
            sesi_id: `k6-pentest-${__VU}-${__ITER}`,
            jenis: 'umum',
        }),
        {
            headers: {
                ...DEFAULT_HEADERS,
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf,
                Referer: `${BASE_URL}/chatbot/`,
            },
            jar,
            timeout: REQUEST_TIMEOUT,
        }
    );

    const body = apiRes.body || '';
    let parsed = {};
    try { parsed = JSON.parse(body); } catch (e) { /* not json */ }

    const isRateLimited =
        apiRes.status === 429 ||
        body.includes('Terlalu') ||
        body.includes('tunggu') ||
        body.includes('rate limit') ||
        body.includes('Layanan sedang') ||
        (parsed.error && /(rate|limit|tunggu|cooldown)/i.test(parsed.error)) ||
        (parsed.retry_seconds && parsed.retry_seconds > 0);

    // Heuristik "OpenAI succeeded": status 200 + jawaban panjang > 30 char
    // (karena OpenAI biasanya jawab paragraph). Kalau hanya intent_keyword
    // match dari DatasetChatbot, juga ke-count sebagai succeeded — tapi
    // itu tetap mengkonsumsi resource server, jadi fair untuk dihitung.
    const isOpenAISuccess =
        apiRes.status === 200 &&
        !isRateLimited &&
        (parsed.respon_bot || parsed.message || '').length > 30;

    if (isRateLimited) rateLimitedChatbot.add(1);
    if (isOpenAISuccess) openaiCallSucceeded.add(1);

    check(apiRes, {
        '[INFO] API merespons (bukan crash 5xx)':
            (r) => r.status !== 0 && r.status < 500,
        '[CRIT] Burst tidak boleh semua sukses (cost-burning protection)':
            () => !(isOpenAISuccess && __ITER >= 5),
    });

    // SENGAJA tidak pakai sleep — tujuannya membakar request secepat mungkin
    // untuk memicu rate limiter. Jangan tambah sleep di test ini.
}

export function teardown() {
    console.log('\n--- HASIL UJI RATE LIMIT CHATBOT (ANTI COST-BURNING) ---');
    console.log('  Target: ≥ 16 dari 20 request harus ditolak (≥ 80%)');
    console.log('  Kalau openai_call_succeeded > 4 → review BudgetLimiter');
    console.log('  Kalau openai_call_succeeded == 20 → CRITICAL: regresi ke kondisi pre-7a65151');
    console.log('---------------------------------------------------------\n');
}
