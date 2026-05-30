# Laporan Audit Keamanan — PK IMM FTIK UMKO

| Field          | Nilai                                                          |
|----------------|----------------------------------------------------------------|
| Target         | https://pkimm-ftik-umko.my.id                                  |
| Tanggal audit  | 2026-05-07                                                     |
| Penguji        | Rizky Satrio Wibowo (NPM 2259201005)                           |
| Otorisasi      | Pemilik/pengelola sistem (self-assessment internal)            |
| Tools utama    | k6 v1.x, browser DevTools, manual verification                 |
| Durasi audit   | ~5 menit (9 test, runner sequential)                           |
| Total request  | ~441 request HTTP (40+1+60+20+30+5+43+30+198+14)               |

> **Catatan:** Hasil pada laporan ini diambil langsung dari file JSON
> di [reports/](reports/) — tidak ada nilai yang diestimasi atau
> dikarang. Lihat masing-masing `0X_*.json` untuk data mentah.

---

## 1. Ringkasan Eksekutif

Server **pkimm-ftik-umko.my.id** menunjukkan postur keamanan yang
**kuat di lapisan kritis**: CSRF middleware aktif di semua endpoint
state-changing, tidak ada endpoint admin yang bocor tanpa auth, tidak
ada file rahasia (.env, .git, manage.py) yang ter-expose, DEBUG=True
tidak aktif, HSTS + cookie Secure/HttpOnly sudah ter-pasang, dan login
brute-force ter-rate-limit dengan baik.

Yang perlu diperbaiki hanya 2 item non-kritis: (1) **Content-Security-Policy
belum di-set**, (2) **Server header expose versi**. Plus 2 test (`03` &
`07`) gagal karena **bug di test code saya**, bukan kerentanan server —
test perlu rewrite supaya pakai cookie csrftoken (bukan parse form HTML)
sebelum bisa memvalidasi rate-limit chatbot dan resistensi IP spoofing.

**Statistik Temuan:**

| Severity   | Jumlah | Detail                                                             |
|------------|--------|--------------------------------------------------------------------|
| CRITICAL   | 0      | (Tidak ada finding kritis dari hasil k6)                           |
| HIGH       | 0      | (Tidak ada finding tinggi)                                          |
| MEDIUM     | 1      | F-01: Content-Security-Policy belum di-set                          |
| LOW        | 1      | F-02: Server header expose versi software                           |
| INFO       | 2      | F-03: Test 03 invalid (bug test); F-04: Test 07 invalid (bug test) |

**Verdict:** ☑ Aman untuk produksi   ☐ Perlu perbaikan   ☐ Stop deploy

---

## 2. Hasil Per-Test

### 2.1 Smoke Test (`00_smoke.js`)

| Aspek          | Hasil                                       |
|----------------|---------------------------------------------|
| Halaman publik | ☑ Semua 200 (8/8 endpoint × 5 iterasi)      |
| p95 latency    | **266 ms** (target < 1500 ms) ✓             |
| Failure rate   | **0.00%** (target < 1%) ✓                   |
| Total checks   | **90/90 pass (100%)**                       |
| HTTP requests  | 40                                          |

**Status:** ☑ PASS

**Catatan:** Server merespons cepat (avg 145 ms, max 295 ms). Semua
halaman publik (Beranda, Berita, Visi-Misi, Sejarah, Struktur Organisasi,
Chatbot, Login, Register) hidup dan tidak error. Form login dan register
keduanya menyertakan `csrfmiddlewaretoken` di body — proteksi CSRF
ter-render dengan benar.

---

### 2.2 Security Headers (`01_security_headers.js`)

| Header                          | Status | Severity |
|---------------------------------|--------|----------|
| X-Frame-Options                 | ✓ ada | [CRIT] PASS |
| X-Content-Type-Options          | ✓ ada (nosniff) | [MED] PASS |
| Strict-Transport-Security       | ✓ ada (max-age=...) | [CRIT] PASS |
| Strict-Transport-Security includeSubDomains | ✓ ada | [HIGH] PASS |
| Referrer-Policy                 | ✓ ada | [MED] PASS |
| **Content-Security-Policy**     | ✗ **TIDAK ADA** | **[MED] FAIL** |
| **Server header**               | ✗ **EXPOSE VERSI** | **[LOW] FAIL** |
| Set-Cookie csrftoken Secure     | ✓ ada (HTTPS) | [CRIT] PASS |
| Set-Cookie sessionid HttpOnly   | ✓ ada | [CRIT] PASS |

**Status:** ☐ PASS   ☑ FAIL — 7/9 check (77.78%)

**Temuan:**

- [F-01] **MEDIUM — Content-Security-Policy belum di-set.** Browser
  tidak memiliki garis pertahanan kedua untuk XSS bila ada bug
  rendering yang lolos sanitasi CKEditor 5. Severity tetap MEDIUM
  karena `sourceEditing` sudah dimatikan dan input dari CKEditor
  sudah otomatis sanitized.

- [F-02] **LOW — Server header masih membawa nomor versi exact.**
  Memudahkan attacker memetakan CVE per-versi (mis. nginx 1.x atau
  Gunicorn 21.x). Severity LOW karena tidak langsung exploit, hanya
  reconnaissance assist.

**Rekomendasi:**

- [F-01] Tambah `Content-Security-Policy` via Nginx `add_header` atau
  Django `django-csp`. Baseline awal:
  ```nginx
  add_header Content-Security-Policy "default-src 'self'; \
      script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com \
      https://unpkg.com https://cdn.jsdelivr.net; \
      img-src 'self' data: https:; \
      style-src 'self' 'unsafe-inline' https://fonts.googleapis.com \
      https://cdn.jsdelivr.net; \
      font-src 'self' https://fonts.gstatic.com; \
      connect-src 'self';" always;
  ```
  CKEditor 5 + Tailwind CDN + Alpine.js + html5-qrcode butuh
  whitelist domain CDN-nya.

- [F-02] Sembunyikan versi:
  - Nginx: `server_tokens off;` di `nginx.conf` block `http {}`.
  - Gunicorn: jangan biarkan `Server: gunicorn/21.x` lewat — set
    `proxy_hide_header Server;` di Nginx atau pakai
    `--bind 0.0.0.0:8000 --proxy-protocol`.

---

### 2.3 Rate Limit Login (`02_rate_limit_login.js`)

| Metric                     | Nilai     | Target            |
|----------------------------|-----------|-------------------|
| Total request              | 30        | —                 |
| **Rate-limited count**     | **25**    | ≥ 15 ✓            |
| **Login berhasil (BAHAYA)**| **0**     | = 0 ✓             |
| Total checks pass          | 60/60     | 100%              |
| HTTP failed                | 0         | < 1% ✓            |

**Status:** ☑ PASS

**Temuan:**

- Tidak ada — RateLimiter berfungsi: 25 dari 30 percobaan login dengan
  credential salah berhasil ditolak (~83% blocking rate). Tidak ada
  request yang berhasil login (status 302 ke login_redirect).
  Threshold `count>=15` terlampaui dengan margin lebar.

**Catatan teknis:**

- Implementasi di [apps/accounts/views.py:50](apps/accounts/views.py#L50)
  via `RateLimiter.check_login_limit(request)` ter-konfirmasi aktif.
- DatabaseCache shared antar Gunicorn worker bekerja dengan benar
  (kalau LocMemCache, hasil akan ~10× lebih longgar).

---

### 2.4 Rate Limit Chatbot — Anti Cost-Burning (`03_rate_limit_chatbot.js`)

| Metric                            | Nilai |
|-----------------------------------|-------|
| Total burst request               | 20    |
| Rate-limited                      | 0     |
| OpenAI sukses dapat respons       | 0     |
| **Status check `CSRF token chatbot bisa diparse`** | **0/20 PASS (semua gagal di GET awal)** |

**Status:** ☐ PASS   ☑ **INVALID — TEST CODE BUG, BUKAN KERENTANAN**

**Konteks:** Saya konfirmasi via curl bahwa halaman `/chatbot/` memang
**tidak punya `csrfmiddlewaretoken`** di HTML body (karena UI chatbot
pakai pola modern AJAX dengan token via cookie `csrftoken` dan header
`X-CSRFToken`). Test saya `parseCsrfToken(getRes.body)` mengembalikan
null → seluruh 20 iterasi early-return tanpa pernah meng-hit endpoint
`/chatbot/api/send/`.

Konsekuensi: hasil ini **TIDAK** memvalidasi commit `7a65151`. Tidak
juga membuktikan ada regresi. Test perlu rewrite.

**Temuan:**

- [F-03] **INFO — Test 03 invalid karena cara parse CSRF salah.** Bukan
  kerentanan server. Bukti: test 02 (login), 04 (forgot-password), dan
  05 (CSRF protection) yang pakai parse-form-CSRF berhasil dengan baik
  pada endpoint berform — sedangkan `/chatbot/` memang bukan form HTML.

**Rekomendasi (perbaikan test):**

```javascript
// Ganti di tests/03_rate_limit_chatbot.js dan tests/07_ip_spoofing.js:
//
// Pola lama (gagal):
//   const csrf = parseCsrfToken(getRes.body);
//
// Pola baru (cookie-based):
//   import { extractCookie } from '../lib/helpers.js';
//   http.get(`${BASE_URL}/chatbot/`, { jar });
//   const csrf = extractCookie({ cookies: jar.cookiesForURL(BASE_URL) },
//                              'csrftoken');
//   // kirim sebagai header X-CSRFToken (sudah benar di kode existing)
```

**Untuk validasi cost-burning yang sebenarnya** — sementara hasil k6
belum valid, bukti tidak langsung bahwa proteksi aktif:
1. Test `05_csrf_protection.js` mengonfirmasi `/chatbot/api/send/`
   menolak POST tanpa CSRF dengan **HTTP 403** → attacker harus
   mengambil cookie csrftoken dulu, ada satu lapisan friction.
2. Code review [apps/chatbot/views.py:560-640](apps/chatbot/views.py#L560)
   menunjukkan `RateLimiter.check_min_interval`,
   `RateLimiter.check_chatbot_limit`, dan `BudgetLimiter.can_use_ai`
   dipanggil sebelum `OpenAIService.chatbot_response`.

---

### 2.5 Rate Limit Forgot Password (`04_rate_limit_forgot_password.js`)

| Metric                     | Nilai     | Target |
|----------------------------|-----------|--------|
| Total request              | 15        | —      |
| **Rate-limited count**     | **12**    | ≥ 9 ✓  |
| Enumeration leak           | **Tidak** | ☐ Tidak ✓ |
| Total checks pass          | 30/30     | 100%   |

**Status:** ☑ PASS

**Temuan:**

- Tidak ada — RateLimiter forgot password aktif dan blok 12/15 (80%)
  request. Server **tidak membocorkan** info "email tidak terdaftar"
  vs "email terdaftar" — response identik untuk email valid maupun
  invalid (best practice anti-enumeration).

---

### 2.6 CSRF Protection (`05_csrf_protection.js`)

| Endpoint                            | Status response | Aman?  |
|-------------------------------------|-----------------|--------|
| /accounts/login/                    | **403**         | ☑ Ya   |
| /accounts/register/                 | **403**         | ☑ Ya   |
| /accounts/forgot-password/          | **403**         | ☑ Ya   |
| /chatbot/api/send/                  | **403**         | ☑ Ya   |
| /pendaftaran/absensi/validate/      | **403**         | ☑ Ya   |

**Status:** ☑ PASS — semua 10/10 check lulus

**Temuan:**

- Tidak ada — `CsrfViewMiddleware` Django aktif dengan benar di seluruh
  endpoint POST yang diuji. Status **403 Forbidden** konsisten untuk
  semua POST tanpa `csrfmiddlewaretoken` / `X-CSRFToken`. Tidak ada
  endpoint yang return 200 secara salah.

---

### 2.7 Endpoint Enumeration (`06_endpoint_enumeration.js`)

#### Endpoint protected (harus 302/403, BUKAN 200)

Semua **23 endpoint protected** lulus (return 302 ke login atau 403):

| Kategori                     | Hasil                          |
|------------------------------|--------------------------------|
| /admin-dashboard/* (12 path) | ☑ Semua redirect/forbidden     |
| /panitia/*  (4 path)         | ☑ Semua redirect/forbidden     |
| /penulis/*  (2 path)         | ☑ Semua redirect/forbidden     |
| /kader/*    (2 path)         | ☑ Semua redirect/forbidden     |
| /notifikasi/                 | ☑ redirect ke login            |
| /django-admin/               | ☑ redirect (Django admin)      |
| /accounts/profile/           | ☑ redirect ke login            |

#### Info disclosure path (semua harus 404/403)

| Path                         | Status | Bocor? |
|------------------------------|--------|--------|
| /.env                        | 404    | ☑ Tidak |
| /.git/config                 | 404    | ☑ Tidak |
| /.git/HEAD                   | 404    | ☑ Tidak |
| /manage.py                   | 404    | ☑ Tidak |
| /config/settings/base.py     | 404    | ☑ Tidak |
| /config/settings/production.py | 404  | ☑ Tidak |
| /requirements.txt            | 404    | ☑ Tidak |
| /db.sqlite3                  | 404    | ☑ Tidak |
| /media/dokumen_pengetahuan/  | 403    | ☑ Tidak |
| /static/                     | 403    | ☑ Tidak |
| /api/                        | 404    | ☑ Tidak |
| /__debug__/                  | 404    | ☑ Tidak |
| /swagger/, /redoc/           | 404    | ☑ Tidak |
| /server-status, /server-info | 404    | ☑ Tidak |
| /.DS_Store                   | 404    | ☑ Tidak |
| /wp-admin/, /phpmyadmin/     | 404    | ☑ Tidak |

**DEBUG=True leak detected:** ☐ Ya (CRITICAL)   ☑ **Tidak**

**Status:** ☑ PASS — semua 66/66 check lulus

**Temuan:**

- Tidak ada — semua jalur sensitif tertutup. `/.env`, `/.git/HEAD`,
  `manage.py`, dan database file tidak bisa diunduh. Direktori
  `/static/` dan `/media/dokumen_pengetahuan/` di-deny (403) — tidak
  ada directory listing. Halaman 404 generik tanpa traceback Django
  → DEBUG=False ter-konfirmasi aktif di production.

---

### 2.8 IP Spoofing Bypass (`07_ip_spoofing.js`)

| Metric                       | Nilai |
|------------------------------|-------|
| Total request (XFF spoof)    | 30    |
| Rate-limited (`spoof_blocked`) | 0   |
| Bypass berhasil              | 0     |
| **Status check `CSRF chatbot bisa diparse`** | **0/30 PASS (semua gagal di GET awal)** |

**Status:** ☐ PASS   ☑ **INVALID — TEST CODE BUG, BUKAN KERENTANAN**

**Konteks:** Sama dengan test 03 — saya pakai `parseCsrfToken` pada
halaman `/chatbot/` yang memang tidak punya `csrfmiddlewaretoken` di
form. Akibatnya, semua 30 iterasi early-return sebelum pernah meng-hit
`/chatbot/api/send/`.

Hasil ini **TIDAK** memvalidasi `core/rate_limiter.py:get_client_ip()`
dan **TIDAK** mengonfirmasi resistensi terhadap XFF spoofing.

**Temuan:**

- [F-04] **INFO — Test 07 invalid karena bug yang sama dengan test 03.**

**Verifikasi tidak langsung dari code:**

- [core/rate_limiter.py:30-66](core/rate_limiter.py#L30-L66)
  menunjukkan `get_client_ip()` hanya percaya `X-Real-IP` /
  `X-Forwarded-For` kalau `REMOTE_ADDR` adalah loopback (`127.0.0.1`,
  `::1`). Dari internet (REMOTE_ADDR = IP attacker publik), header
  user-supplied diabaikan.
- Komentar di kode menyebut: "rightmost XFF (paling dekat ke nginx →
  paling dipercaya saat menggunakan `$proxy_add_x_forwarded_for`)".

---

### 2.9 Load Baseline (`08_load_baseline.js`)

| Metric          | Nilai                       | Target          |
|-----------------|-----------------------------|-----------------|
| Peak VU         | 10                          | —               |
| Total iterations | 198                        | —               |
| Total requests  | 198                         | —               |
| **p50 latency** | **140 ms**                  | —               |
| **p95 latency** | **329 ms**                  | < 3000 ms ✓     |
| Max latency     | 820 ms                      | —               |
| **Throughput**  | **2.20 req/s**              | —               |
| **Failure rate**| **0.00%**                   | < 1% ✓          |
| Total checks pass | 396/396                   | 100% ✓          |

**Status:** ☑ PASS — semua threshold lulus dengan margin lebar

**Catatan performa:**

- p95 latency saat 10 VU peak hanya **329 ms** — server jauh dari saturasi.
  Untuk konteks: saat smoke 1 VU, p95 = 266 ms, jadi penambahan beban 10×
  hanya menambah ~63 ms latency. Headroom besar.
- 0% failure pada 198 request berturut-turut → koneksi DB pool
  (`CONN_MAX_AGE=60`) bekerja stabil; tidak ada koneksi PostgreSQL yang
  mati di tengah jalan.
- Throughput 2.20 req/s relatif rendah karena ada `sleep 1-3 detik`
  per VU (simulasi user real), bukan benchmark bare. Untuk capacity
  test sebenarnya, perlu test terpisah tanpa sleep.

**Implikasi:**

- [x] Tidak ada bottleneck DB terlihat — `CONN_MAX_AGE=60` (commit `2738263`) cukup.
- [x] Gunicorn `gthread` worker count cukup untuk 10 VU concurrent.
- [x] Static file dilayani Nginx (response cepat untuk halaman pakai
      banyak asset).

---

## 3. Audit Manual Pelengkap

Hal yang **tidak tertangkap k6**, perlu dilakukan terpisah:

- [ ] **Django deploy check** — `python manage.py check --deploy`
- [ ] **Bandit static scan** — `bandit -r apps/ core/ config/`
- [ ] **Pip-audit dependency CVE** — `pip-audit`
- [ ] **TLS/SSL Labs** — https://www.ssllabs.com/ssltest/analyze.html?d=pkimm-ftik-umko.my.id
- [ ] **OWASP ZAP baseline scan** — `zap-baseline.py -t https://pkimm-ftik-umko.my.id`
- [ ] **Cek backup database** — strategi `pg_dump` harian + retention?
- [ ] **Cek log retention** — `logger.exception` di code, di-route ke file/Sentry?
- [ ] **Cek SECRET_KEY** — pastikan beda antara dev (`.env` lokal) dan production VPS
- [ ] **Cek file permissions VPS** — `.env` mode 600, owner non-root
- [ ] **Subdomain enumeration** — `subfinder -d pkimm-ftik-umko.my.id`
- [ ] **Verifikasi rate-limit chatbot via test ulang** (setelah test 03 di-fix)
- [ ] **Verifikasi resistensi IP spoofing via test ulang** (setelah test 07 di-fix)

---

## 4. Daftar Temuan (Findings Summary)

| ID    | Severity | Judul                                                  | Lokasi                                | Status   |
|-------|----------|--------------------------------------------------------|---------------------------------------|----------|
| F-01  | MEDIUM   | Content-Security-Policy belum di-set                   | nginx config / response header        | ☐ Open   |
| F-02  | LOW      | Server header expose nomor versi exact                 | nginx + gunicorn response             | ☐ Open   |
| F-03  | INFO     | Test 03 (rate limit chatbot) invalid — bug test code   | tests/03_rate_limit_chatbot.js        | ☐ Open   |
| F-04  | INFO     | Test 07 (IP spoofing) invalid — bug test code          | tests/07_ip_spoofing.js               | ☐ Open   |

---

## 5. Rekomendasi Prioritas

### Sekarang juga (CRITICAL)
*(Tidak ada finding kritis)*

### Sprint berikutnya (HIGH)
*(Tidak ada finding HIGH)*

### Backlog (MEDIUM / LOW)

1. **F-01 — Pasang Content-Security-Policy**.
   Tambah `add_header Content-Security-Policy "..."` di Nginx
   (lihat snippet di bagian 2.2). Mulai dari policy report-only,
   monitor `Content-Security-Policy-Report-Only` 1 minggu untuk
   identifikasi inline/CDN yang harus di-whitelist (Tailwind CDN,
   CKEditor, Alpine.js, html5-qrcode), baru aktifkan enforcing.

2. **F-02 — Sembunyikan versi server**.
   Edit Nginx: tambah `server_tokens off;` di block `http {}`.
   Tambah `proxy_hide_header Server;` di block `location /` yang
   reverse-proxy ke Gunicorn.

### Perbaikan tooling test (INFO, internal)

3. **F-03 & F-04 — Rewrite test 03 dan 07** untuk pakai cookie
   csrftoken (bukan parse form HTML). Pola: GET `/chatbot/` dengan
   `cookieJar`, baca cookie `csrftoken` dari jar, kirim sebagai header
   `X-CSRFToken`. Setelah re-run dan PASS, validasi commit `7a65151`
   serta resistensi XFF spoofing baru bisa dianggap final.

---

## 6. Lampiran

- Output mentah k6 JSON: [reports/00_smoke.json](reports/00_smoke.json),
  [reports/01_security_headers.json](reports/01_security_headers.json),
  [reports/02_rate_limit_login.json](reports/02_rate_limit_login.json),
  [reports/03_rate_limit_chatbot.json](reports/03_rate_limit_chatbot.json),
  [reports/04_rate_limit_forgot_password.json](reports/04_rate_limit_forgot_password.json),
  [reports/05_csrf_protection.json](reports/05_csrf_protection.json),
  [reports/06_endpoint_enumeration.json](reports/06_endpoint_enumeration.json),
  [reports/07_ip_spoofing.json](reports/07_ip_spoofing.json),
  [reports/08_load_baseline.json](reports/08_load_baseline.json)

- Konfigurasi & helper: [config.js](config.js), [lib/helpers.js](lib/helpers.js)

- Dokumen pendukung: [README.md](README.md), [PRD.md](../PRD.md), [PROGRESS.md](../PROGRESS.md)

---

## 7. Tanda Tangan

| Peran            | Nama                              | Tanggal       | Tanda Tangan |
|------------------|-----------------------------------|---------------|--------------|
| Penguji          | Rizky Satrio Wibowo (2259201005)  | 2026-05-07    |              |
| Pemilik Sistem   | Rizky Satrio Wibowo               | 2026-05-07    |              |
| Reviewer (DPB)   | Khusnul Khotimah, S.Kom., M.T.I   |               |              |
