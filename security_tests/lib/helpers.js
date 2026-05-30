// =============================================================================
// Helper bersama untuk test k6 keamanan.
//   - parseCsrfToken: ambil csrfmiddlewaretoken dari form HTML Django
//   - randomString:   string acak untuk username/email saat test register
//   - extractCookie:  baca cookie dari response (csrftoken / sessionid)
// =============================================================================

import { check } from 'k6';

/**
 * Ekstrak nilai csrfmiddlewaretoken dari body HTML Django.
 * Django menyimpan token di hidden input:
 *   <input type="hidden" name="csrfmiddlewaretoken" value="ABCDEF...">
 *
 * @param {string} body - HTML body response
 * @returns {string|null} - token CSRF, atau null kalau tidak ditemukan
 */
export function parseCsrfToken(body) {
    if (!body) return null;
    const match = body.match(
        /name=["']csrfmiddlewaretoken["']\s+value=["']([^"']+)["']/
    );
    return match ? match[1] : null;
}

/**
 * Ambil cookie dengan nama tertentu dari response k6.
 * Berguna untuk csrftoken & sessionid.
 *
 * @param {object} res - response k6
 * @param {string} name - nama cookie
 * @returns {string|null}
 */
export function extractCookie(res, name) {
    if (!res || !res.cookies || !res.cookies[name]) return null;
    const arr = res.cookies[name];
    return arr.length > 0 ? arr[0].value : null;
}

/**
 * Generate string acak alfanumerik (default 8 karakter).
 * Dipakai untuk username/email saat register test.
 */
export function randomString(len = 8) {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    let out = '';
    for (let i = 0; i < len; i++) {
        out += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return out;
}

/**
 * Reusable check: response status sesuai harapan.
 * Tambah info URL untuk memudahkan debugging di summary.
 */
export function checkStatus(res, expected, label) {
    return check(res, {
        [`${label}: status ${expected}`]: (r) => r.status === expected,
    });
}

/**
 * Cek bahwa server merespons (bukan timeout / connection refused).
 * Status 0 di k6 = network error / timeout.
 */
export function checkAlive(res, label) {
    return check(res, {
        [`${label}: server merespons (bukan timeout)`]: (r) => r.status !== 0,
    });
}

/**
 * Login Django dan kembalikan jar+csrftoken yang siap dipakai untuk
 * request berikutnya. Throw error kalau login gagal.
 *
 * @param {object} http - module 'k6/http'
 * @param {string} baseUrl
 * @param {string} username
 * @param {string} password
 * @returns {{csrf: string, jar: object}}
 */
export function djangoLogin(http, baseUrl, username, password) {
    const jar = http.cookieJar();
    const loginUrl = `${baseUrl}/accounts/login/`;

    // GET dulu untuk dapatkan csrftoken cookie + token di form
    const getRes = http.get(loginUrl, { jar });
    const csrfFromForm = parseCsrfToken(getRes.body);
    if (!csrfFromForm) {
        throw new Error(`Gagal parse csrfmiddlewaretoken dari ${loginUrl}`);
    }

    // POST credentials
    const postRes = http.post(
        loginUrl,
        {
            csrfmiddlewaretoken: csrfFromForm,
            username,
            password,
        },
        {
            jar,
            redirects: 0, // jangan auto-follow supaya bisa cek status 302
            headers: { Referer: loginUrl },
        }
    );

    if (postRes.status !== 302) {
        throw new Error(
            `Login gagal (status=${postRes.status}). Cek kredensial atau rate limit.`
        );
    }

    return { jar, csrf: csrfFromForm };
}
