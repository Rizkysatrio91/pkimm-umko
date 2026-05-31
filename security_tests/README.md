# Security Test Suite — PK IMM FTIK UMKO

Test k6 untuk audit keamanan website [pkimm-ftik-umko.my.id](https://pkimm-ftik-umko.my.id).
Dirancang khusus berdasarkan stack project (Django 5 + PostgreSQL +
DatabaseCache + RateLimiter + BudgetLimiter + SSO UMKO + OpenAI RAG).

> **🚨 PERINGATAN — OTORISASI WAJIB**
> Suite ini HANYA boleh dijalankan terhadap server yang Anda
> miliki / kelola, dan TIDAK boleh dijalankan terhadap pihak ketiga
> tanpa izin tertulis. Penyalahgunaan dapat melanggar UU ITE Pasal
> 30, 32, dan 33.

> **🚨 PERINGATAN — OPENAI COST**
> SEBELUM jalankan suite ini terhadap production:
> 1. Set **hard limit** di https://platform.openai.com/account/limits
>    (rekomendasi $5/bulan).
> 2. Catat OpenAI spend saat ini (screenshot).
> 3. **JANGAN jalankan test paralel** — selalu serial via
>    [run_all.ps1](run_all.ps1).
> 4. **JANGAN ada user lain yang pakai chatbot/Smart Editor** saat k6 jalan
>    (atau Anda tidak bisa membedakan cost mereka vs cost test).
> 5. Setelah test selesai, tunggu 5 menit, lalu cek dashboard OpenAI.
>    Selisih dengan baseline HARUS ≤ $0.01 untuk suite ini. Kalau
>    > $0.10 → STOP, baca [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).

---

## Daftar Test

| File                                | Fokus                                  | Severity bila gagal |
|-------------------------------------|----------------------------------------|---------------------|
| `00_smoke.js`                       | Halaman publik hidup, p95 < 1.5s       | Blocker             |
| `01_security_headers.js`            | XFO, HSTS, CSP, cookie flags           | CRIT / HIGH / MED   |
| `02_rate_limit_login.js`            | Anti brute-force /accounts/login/      | CRITICAL            |
| `03_rate_limit_chatbot.js`          | Anti OpenAI cost-burning (commit 7a65151) | CRITICAL         |
| `04_rate_limit_forgot_password.js`  | Anti email bombing /accounts/forgot-password/ | HIGH         |
| `05_csrf_protection.js`             | CsrfViewMiddleware aktif di endpoint POST | CRITICAL         |
| `06_endpoint_enumeration.js`        | Admin URL ter-protect, no .env / .git leak | CRIT / HIGH    |
| `07_ip_spoofing.js`                 | XFF spoofing tidak bypass rate limit (commit 7a65151) | CRITICAL |
| `08_load_baseline.js`               | Performa baseline 10 VU / 1.5 menit    | HIGH / MEDIUM       |
| `09_open_redirect.js`               | `?next=` login tak bisa ke domain luar (phishing) | HIGH      |
| `10_rate_limit_otp.js`              | Anti brute-force kode OTP reset password (5×/15mnt) | CRITICAL |
| `11_xss_sanitization.js`            | Konten publik bersih dari `<script>`/handler (nh3) | CRITICAL |
| `12_sensitive_data_exposure.js`     | Data SSO mahasiswa & dokumen tertutup (auth/IDOR/listing) | CRITICAL |
| `13_bot_detection.js`               | Bot/pengguna fiktif ditolak (same-origin + honeypot + chat_token), OpenAI tak tersentuh | CRITICAL |

Total request maksimum yang dikirim ke server **kurang dari 1500
selama 5 menit** — beban ringan, aman untuk VPS.

### Test 09–12 (ditambahkan saat hardening Mei 2026)

Empat test ini memverifikasi perbaikan keamanan terbaru. Semua **pasif/read-only**
kecuali 10 (mengirim POST percobaan OTP yang sengaja gagal):

- **09 Open Redirect** — membuktikan `LoginView` memvalidasi parameter `next`
  (`url_has_allowed_host_and_scheme`) sehingga tidak bisa diarahkan ke domain
  attacker untuk phishing.
- **10 Rate Limit OTP** — membuktikan `RateLimiter.check_otp_verify_limit`
  (5×/15 mnt per IP) memblokir brute-force kode OTP 6 digit. Memakai email
  tak terdaftar → tidak mengubah akun siapa pun. Jalankan dari IP non-admin.
- **11 XSS Sanitization** — mengaudit halaman publik (beranda, berita,
  visi-misi, sejarah) memastikan tidak ada `<script>`, `onerror=`,
  `javascript:`, `<iframe>` yang ter-render. Membuktikan `core/sanitizer.py`
  (nh3) bekerja end-to-end.
- **12 Sensitive Data Exposure** — membuktikan data pribadi mahasiswa dari SSO
  UMKO (NPM, tanggal lahir, alamat) & dokumen pendaftaran tidak bisa diakses
  anonim, tidak rentan IDOR, dan direktori media tidak bisa di-listing.

Pemetaan OWASP Top 10: A01 Broken Access Control → 06, 09, 12 · A03 Injection
(XSS) → 11 · A04 Insecure Design → 10 · A07 Auth Failures → 02, 04, 10.

---

## Prasyarat

1. **k6 installed** (https://k6.io/docs/get-started/installation/)
   - Windows: `winget install k6 --source winget`
   - macOS: `brew install k6`
   - Linux: `sudo apt install k6` (setelah add repo Grafana)

2. **Akses ke target** — bisa via internet (production) atau lokal
   (`http://localhost:8000` untuk runserver).

3. **Browser/curl optional** — untuk verifikasi manual hasil suspicious.

---

## Quickstart

### Test cepat ke localhost (recommended dulu)

```powershell
cd d:\Downloads\PK_IMM\security_tests

# Smoke dulu — pastikan server hidup
k6 run -e BASE_URL=http://localhost:8000 tests/00_smoke.js

# Audit header
k6 run -e BASE_URL=http://localhost:8000 tests/01_security_headers.js
```

### Test ke production (HATI-HATI)

```powershell
cd d:\Downloads\PK_IMM\security_tests

# Smoke dulu
k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/00_smoke.js

# Per-test
k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/01_security_headers.js
k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/02_rate_limit_login.js
# … dst
```

### Jalankan semua test sekaligus

```powershell
# Windows PowerShell
.\run_all.ps1 -BaseUrl https://pkimm-ftik-umko.my.id

# Linux/macOS bash
./run_all.sh https://pkimm-ftik-umko.my.id
```

Hasil JSON setiap test akan disimpan di `reports/<nama_test>.json`.

---

## Cara Membaca Hasil

k6 menampilkan ringkasan di terminal setelah test selesai:

```
✓ checks ......................: 100.00%   ↑ 50  ↓ 0
✓ http_req_duration ............: avg=120ms p(95)=380ms
  http_req_failed ..............: 0.00%
  iterations ...................: 30
```

- **`checks` = 100%** → semua assertion lulus → BAIK
- **`checks` < 100%** → ada assertion gagal → cek `[CRIT]`/`[HIGH]` di log
- **`http_req_failed` > 1%** → server tidak stabil
- **`p(95)` melonjak** → ada performance issue

Setiap test punya **threshold** yang otomatis fail kalau angka tidak
masuk batasan. Exit code k6 ≠ 0 berarti test gagal.

### Severity tag dalam output check

| Tag      | Arti                                    | Aksi                       |
|----------|------------------------------------------|----------------------------|
| `[CRIT]` | Critical — bisa exploit langsung         | Fix segera, blocker deploy |
| `[HIGH]` | High — risiko serius                     | Fix dalam 1 sprint         |
| `[MED]`  | Medium — best practice tidak terpenuhi   | Fix dalam 2-4 sprint       |
| `[LOW]`  | Low — info disclosure / hygiene          | Fix saat ada kesempatan    |
| `[INFO]` | Informational — bukan kerentanan         | Untuk konteks saja         |

---

## Mengisi Laporan

Setelah semua test jalan, salin `REPORT_TEMPLATE.md` ke
`reports/REPORT_<tanggal>.md`, lalu isi tiap section dengan hasil
aktual:

```powershell
copy REPORT_TEMPLATE.md reports\REPORT_2026-05-07.md
```

Buka file itu di editor, isi field "Status", "Detail Temuan", dan
"Rekomendasi" untuk tiap test berdasarkan hasil k6.

---

## Pertimbangan Etis & Operasional

1. **Beri tahu pemilik server / oncall sebelum test**, terutama
   sebelum `08_load_baseline.js` (10 VU) supaya tidak salah dikira
   serangan oleh sistem monitoring.

2. **Jangan jalankan saat traffic puncak** (mis. saat pendaftaran
   DAD dibuka). Idealnya jalankan tengah malam atau di staging.

3. **IP Anda akan ke-block sementara** setelah test rate limit (login,
   forgot-password, chatbot). Tunggu ~10 menit atau restart cache:
   `python manage.py shell -c "from django.core.cache import cache; cache.clear()"`.

4. **Test 03 (chatbot) bisa membakar < $0.001 token OpenAI** dalam
   skenario worst-case (kalau semua 20 request lolos). Itu pun jauh
   di bawah BudgetLimiter cap $1.25/bulan.

5. **Test 02 (login) memakai username acak yang TIDAK ADA** — tidak
   mengunci akun real.

6. **Test 04 (forgot password) memakai email `@example.invalid`** —
   tidak mengirim email ke user real.

---

## Apa yang TIDAK Di-cover

k6 adalah load testing tool, bukan vulnerability scanner. Untuk
coverage lebih lengkap, kombinasikan dengan tool berikut:

| Area                          | Tool yang disarankan                       |
|-------------------------------|--------------------------------------------|
| SQL injection / XSS deep scan | **OWASP ZAP** (gratis), Burp Suite         |
| Dependency vuln (CVE)         | **pip-audit** + **Safety** (Python)         |
| Static code analysis          | **Bandit** (Python), Semgrep, Snyk         |
| Container scan                | Trivy (kalau pakai Docker)                 |
| TLS/SSL config                | **SSL Labs** (https://ssllabs.com)          |
| Subdomain enum + DNS          | Subfinder, dnsx                            |
| Secret scanning di repo       | git-secrets, TruffleHog, gitleaks          |

Untuk audit lebih dalam pada Django, jalankan juga:

```powershell
python manage.py check --deploy   # Django deploy checklist
pip install bandit && bandit -r apps/ core/ config/
pip install pip-audit && pip-audit
```

---

## Struktur Folder

```
security_tests/
├── README.md                         # File ini
├── REPORT_TEMPLATE.md                # Template laporan untuk diisi
├── config.js                         # BASE_URL, USER_AGENT, threshold global
├── lib/
│   └── helpers.js                    # parseCsrfToken, randomString, dll.
├── tests/
│   ├── 00_smoke.js
│   ├── 01_security_headers.js
│   ├── 02_rate_limit_login.js
│   ├── 03_rate_limit_chatbot.js
│   ├── 04_rate_limit_forgot_password.js
│   ├── 05_csrf_protection.js
│   ├── 06_endpoint_enumeration.js
│   ├── 07_ip_spoofing.js
│   ├── 08_load_baseline.js
│   ├── 09_open_redirect.js              # hardening Mei 2026
│   ├── 10_rate_limit_otp.js            # hardening Mei 2026
│   ├── 11_xss_sanitization.js          # hardening Mei 2026
│   ├── 12_sensitive_data_exposure.js   # hardening Mei 2026
│   └── 13_bot_detection.js             # hardening Mei 2026
├── run_all.ps1                       # Runner Windows PowerShell
├── run_all.sh                        # Runner Linux/macOS bash
└── reports/                          # Output JSON + laporan markdown
    └── (di-generate saat test jalan)
```

---

## Disclaimer

Test ini disusun untuk **uji keamanan internal** sistem milik PK
IMM FTIK UMKO oleh pengelola sistem yang berhak. Penulis tidak
bertanggung jawab atas penyalahgunaan terhadap sistem pihak ketiga.
