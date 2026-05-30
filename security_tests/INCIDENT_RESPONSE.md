# Incident Response — OpenAI Token Burn ~$1 saat Pentest

| Field          | Nilai                                                          |
|----------------|----------------------------------------------------------------|
| Tanggal kejadian | 2026-05-07                                                   |
| Pelapor        | Rizky Satrio Wibowo                                            |
| Estimasi kerugian | ~$1 USD (dari OpenAI billing)                              |
| Konteks        | Setelah jalankan suite k6 di [security_tests/](.)              |
| Status         | Investigasi + tindakan pencegahan                              |

---

## 1. Pengakuan Jujur (Anti-Halusinasi)

Saya **tidak bisa memastikan** sumber pasti $1 itu tanpa data dari **OpenAI
Usage dashboard** (yang punya breakdown per-jam + per-model + per-API-key).
Berikut yang saya **bisa konfirmasi** dari audit kode dan hasil test JSON:

### Yang DIKONFIRMASI dari [reports/](reports/):

| Test                          | Endpoint OpenAI dihit | Cost real |
|-------------------------------|------------------------|-----------|
| 00 smoke                      | 0× (hanya GET halaman) | $0        |
| 01 security_headers           | 0× (1 GET /)           | $0        |
| 02 rate_limit_login           | 0× (login Django, no AI) | $0      |
| **03 rate_limit_chatbot**     | **0×** (CSRF parse fail, early return) | **$0** |
| 04 rate_limit_forgot_password | 0× (forgot pwd Django, no AI) | $0  |
| 05 csrf_protection            | 0× (semua POST → 403)  | $0        |
| 06 endpoint_enumeration       | 0× (semua GET → 302/403/404) | $0  |
| **07 ip_spoofing**            | **0×** (CSRF parse fail, early return) | **$0** |
| 08 load_baseline              | 0× (GET halaman publik tanpa AI render) | $0 |

**Bukti dari JSON:**
- `reports/03_rate_limit_chatbot.json` — `openai_call_succeeded: 0`,
  `rate_limited_chatbot: 0`, semua 20 iterasi gagal di check
  `"CSRF token chatbot bisa diparse"` dengan `passes: 0, fails: 20`.
  Artinya semua iterasi early-return SEBELUM POST ke
  `/chatbot/api/send/`.
- `reports/07_ip_spoofing.json` — sama, 30 iterasi early-return.

### Yang DIKONFIRMASI dari audit kode `apps/`:

- [apps/berita/views.py:25-75](apps/berita/views.py#L25-L75) —
  `BerandaView`, `BeritaListView`, `BeritaDetailView`: query DB biasa,
  **tidak ada call OpenAI**.
- [apps/berita/views.py:254-310](apps/berita/views.py#L254-L310) —
  `StrukturOrganisasiView`, `VisiMisiPublikView`, `SejarahPublikView`:
  query DB biasa, **tidak ada call OpenAI**.
- [apps/chatbot/views.py:46-84](apps/chatbot/views.py#L46-L84) —
  `ChatbotPublikView` & `ChatbotKaderView`: hanya render template +
  issue chat token, **tidak ada call OpenAI**.
- Endpoint `/chatbot/api/send/` ([apps/chatbot/views.py:511-635](apps/chatbot/views.py#L511-L635))
  baru call OpenAI **setelah** lolos 7 lapis defense:
  1. `_is_same_origin` (line 513)
  2. Body size limit
  3. Honeypot field
  4. Pesan length limit
  5. `verify_chat_token` ← **k6 tidak punya token ini** (line 561)
  6. MIN_INTERVAL per IP & per session
  7. `RateLimiter.check_chatbot_limit`

  Karena k6 tidak punya `chat_token` (signed token yang di-issue saat
  GET `/chatbot/`), seandainya CSRF parse berhasil pun, request POST
  akan **ditolak di lapisan 5 dengan status 403**.

### Kesimpulan investigasi:

**Test k6 saya secara matematis tidak bisa membakar OpenAI token.** Jadi
$1 yang habis kemungkinan datang dari sumber lain selama window waktu
yang sama:

| Hipotesis                                                                  | Cara verifikasi                              |
|----------------------------------------------------------------------------|----------------------------------------------|
| (A) User lain pakai chatbot publik saat k6 jalan                          | OpenAI dashboard → filter timestamp + count  |
| (B) Anda sendiri test chatbot manual via browser sambil k6 jalan          | Cek riwayat browser + RiwayatChat di DB     |
| (C) Smart Editor AI dipakai (butuh login penulis)                         | Cek RiwayatChat & Berita.tgl_dibuat         |
| (D) PDF embedding saat upload Dokumen Pengetahuan beberapa hari lalu       | OpenAI dashboard → cek model `text-embedding`|
| (E) API key bocor / dipakai pihak luar                                    | OpenAI dashboard → cek IP / origin request   |
| (F) Bot/scanner eksternal random hit chatbot publik                       | Nginx access log → cari POST /chatbot/api/send/ |

**Langkah verifikasi WAJIB sebelum lanjut** (bagian 3 di bawah).

---

## 2. Mengapa $1 Itu Khawatir (Worst-Case Forecast)

`BudgetLimiter` di [core/budget_limiter.py:14-15](core/budget_limiter.py#L14-L15):
```python
MONTHLY_BUDGET = 1.25  # USD per bulan
```

Kalau dalam 1 sesi pentest **$1 sudah habis**, artinya BudgetLimiter
**hanya tersisa $0.25 untuk sisa bulan ini**. Dan kalau sumber
pengeluaran tidak teridentifikasi, hal yang sama bisa terulang **dari
sumber lain di luar k6** yang Anda tidak kontrol (bot, user, dll).

Default OpenAI account juga **tidak punya hard cap per bulan** kecuali
Anda set sendiri di dashboard. Tanpa hard cap, satu bug bisa burn
ratusan dolar dalam jam.

---

## 3. Verifikasi Dulu — Sebelum Apa Pun

### 3.1 Buka OpenAI Usage Dashboard

```
https://platform.openai.com/usage
```

Filter:
- **Date range**: hari ketika k6 dijalankan (gunakan jam menit yang spesifik)
- **Group by**: API key + Model
- **Group by**: Time (per-jam)

Yang dicari:
1. **Berapa request per model?** Kalau `gpt-4o-mini`: kemungkinan dari
   chatbot/Smart Editor. Kalau `text-embedding-3-small`: kemungkinan
   dari PDF ingest atau embed_text RAG.
2. **Pola spike**: apakah burst di satu menit (= bot/k6) atau merata
   (= user normal)?
3. **API key mana**: kalau ada lebih dari 1 key dan yang burn bukan
   key utama, itu indikasi kebocoran.

### 3.2 Cek Nginx Access Log di VPS

```bash
ssh user@server
sudo grep '/chatbot/api/send/' /var/log/nginx/access.log | tail -200
sudo grep '/api/berita/koreksi-ai/' /var/log/nginx/access.log | tail -100

# Cari IP dengan request paling banyak
sudo grep '/chatbot/api/send/' /var/log/nginx/access.log | \
  awk '{print $1}' | sort | uniq -c | sort -rn | head -20
```

Yang dicari:
- IP yang hit endpoint mahal berkali-kali
- User-Agent yang mencurigakan
- Korelasi waktu dengan saat k6 dijalankan

### 3.3 Cek Database `riwayat_chat`

```bash
# Di server, masuk Django shell
python manage.py shell
```
```python
from apps.chatbot.models import RiwayatChat
from django.utils import timezone
from datetime import timedelta

# Hitung chat dalam 24 jam terakhir
cutoff = timezone.now() - timedelta(hours=24)
print(RiwayatChat.objects.filter(waktu_chat__gte=cutoff).count())

# Per jam
from django.db.models.functions import TruncHour
from django.db.models import Count
RiwayatChat.objects.filter(waktu_chat__gte=cutoff) \
    .annotate(jam=TruncHour('waktu_chat')) \
    .values('jam').annotate(c=Count('id_chat')).order_by('jam')
```

Kalau sumber chatbot, di sini akan ada banyak entry dengan
`pesan_user` yang aneh / berulang.

### 3.4 Cek BudgetLimiter Saat Ini

```python
from core.budget_limiter import BudgetLimiter
print('Spent bulan ini:', BudgetLimiter.get_month_spent())
print('Sisa budget   :', BudgetLimiter.get_remaining_budget())
print('Spent hari ini:', BudgetLimiter.get_today_spent())
```

Bandingkan dengan angka di OpenAI dashboard:
- **Selisih kecil** (< 20%) → tracking BudgetLimiter akurat, sumber
  via chatbot/koreksi.
- **Selisih besar** (> 50%) → ada call OpenAI di luar tracker
  (mis. PDF embedding atau API key bocor).

---

## 4. Tindakan Pencegahan Berlapis

Lapisan diurut dari **paling penting** ke paling defensif. **Kerjakan
lapisan 1 sekarang juga**, sebelum yang lain.

### 🚨 Lapisan 1 — HARD CAP DI DASHBOARD OPENAI (paling penting!)

Ini adalah **satu-satunya pertahanan yang OpenAI sendiri yang enforce**.
Bahkan kalau seluruh kode Django Anda buggy, OpenAI akan menolak
request setelah cap tercapai.

1. Buka https://platform.openai.com/account/limits
2. Set **Hard limit (Monthly)**: `$5` (atau lebih ketat misalnya `$2`)
3. Set **Soft limit (Email warning)**: `$1` (dapat email saat tercapai)

Setelah hard limit tercapai, semua request OpenAI di akun Anda akan
return error → BudgetLimiter di-bypass tidak masalah.

> **Catatan**: hard limit di OpenAI **tidak otomatis ada** untuk akun
> baru. Wajib di-set manual.

### 🚨 Lapisan 2 — ROTATE API KEY (kalau curiga bocor)

Kalau Anda menemukan request OpenAI dari IP yang bukan VPS Anda di
dashboard, **API key sudah bocor**:

1. Buka https://platform.openai.com/api-keys
2. Klik **Revoke** pada key yang aktif
3. Buat key baru
4. Update `.env` di VPS:
   ```bash
   ssh user@server
   nano /path/to/PK_IMM/.env
   # Ganti OPENAI_API_KEY=sk-...
   sudo systemctl restart gunicorn
   ```

### Lapisan 3 — Patch Django: Embedding setelah Budget Check

**Bug yang saya temukan**: di
[apps/chatbot/views.py:609-612](apps/chatbot/views.py#L609-L612),
embedding RAG dipanggil **sebelum** cek budget:

```python
# LANGKAH 3: cari dataset + chunk RAG
matching_chunks = self._find_matching_chunks(pesan, jenis)  # ← embed_text di sini

# LANGKAH 4: cek budget
has_budget = BudgetLimiter.can_use_ai(BudgetLimiter.COST_CHATBOT)
```

`_find_matching_chunks()` memanggil `OpenAIService().embed_text(pesan)`
yang real-cost ~$0.000001 per call (sangat kecil, tapi
**tidak ditrack** di `BudgetLimiter`). Walau costnya kecil, ini
melanggar prinsip "tidak boleh ada API call kalau budget habis".

**Patch**:

```python
# apps/chatbot/views.py — di method post() ChatbotAPIView

# === LANGKAH 3: SAPAAN dulu (gratis) ===
if self._is_sapaan(pesan):
    ...
    return JsonResponse(...)

# === LANGKAH 3.5: CARI DATASET MANUAL (gratis, no API) ===
matching_datasets = self._find_matching_datasets(pesan, jenis, sesi_id)
first_match = matching_datasets[0] if matching_datasets else None

# === LANGKAH 4: CEK BUDGET DULU sebelum API call apapun ===
if not BudgetLimiter.can_use_ai(BudgetLimiter.COST_CHATBOT):
    if first_match and first_match.respon_jawaban.strip():
        respon = first_match.respon_jawaban
        self._save_chat(user, first_match, sesi_id, pesan, respon, True)
    else:
        respon = "Mohon maaf, layanan AI sedang maintenance..."
        self._save_chat(user, None, sesi_id, pesan, respon, False)
    return JsonResponse({'success': True, 'respon': respon})

# === LANGKAH 5: BARU embedding RAG (kena cost) ===
matching_chunks = self._find_matching_chunks(pesan, jenis)

# === LANGKAH 6: BARU chat completion (kena cost terbesar) ===
service = OpenAIService()
respon = service.chatbot_response(...)
BudgetLimiter.add_cost(BudgetLimiter.COST_CHATBOT)
```

**Tambahan**: track juga embedding cost. Embedding ~$0.02 per 1M token,
input rata-rata 50 token = $0.000001. Tambahkan konstanta:

```python
# core/budget_limiter.py
COST_EMBEDDING = 0.000001  # text-embedding-3-small per call
```

Dan di view:
```python
matching_chunks = self._find_matching_chunks(pesan, jenis)
BudgetLimiter.add_cost(BudgetLimiter.COST_EMBEDDING)
```

### Lapisan 4 — Turunkan MONTHLY_BUDGET ke $0.50

Kalau project sebenarnya hanya pakai $0.10–0.30 per bulan untuk normal
traffic, $1.25 terlalu longgar. Turunkan ke $0.50 supaya margin lebih
besar untuk anomali.

```python
# core/budget_limiter.py
MONTHLY_BUDGET = 0.50  # turun dari 1.25
```

### Lapisan 5 — Nginx Rate Limit (Network Layer)

Lebih cepat dari Django middleware karena reject request **sebelum**
masuk ke Python sama sekali. Tambahkan ke `/etc/nginx/sites-available/pkimm.conf`:

```nginx
# Di block http {}
limit_req_zone $binary_remote_addr zone=chatbot:10m rate=6r/m;
limit_req_zone $binary_remote_addr zone=koreksi:10m rate=10r/h;
limit_req_zone $binary_remote_addr zone=login:10m rate=20r/m;
limit_req_zone $binary_remote_addr zone=general:10m rate=120r/m;

server {
    server_name pkimm-ftik-umko.my.id;

    # Endpoint mahal — sangat ketat
    location /chatbot/api/send/ {
        limit_req zone=chatbot burst=3 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }

    location /api/berita/koreksi-ai/ {
        limit_req zone=koreksi burst=2 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }

    # Auth — lindungi dari brute force di network layer
    location /accounts/login/ {
        limit_req zone=login burst=5 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }

    # Default untuk semua endpoint lain
    location / {
        limit_req zone=general burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }
}
```

Lalu:
```bash
sudo nginx -t          # test config
sudo systemctl reload nginx
```

**Efek**: bot/k6 yang spam akan ditolak di Nginx dengan 429 sebelum
Django sempat dimuat. Jauh lebih efisien.

### Lapisan 6 — Audit Log Per-Request OpenAI

Tambahkan logging eksplisit setiap call OpenAI ke file log + DB,
supaya bisa trace anomali di masa depan:

```python
# apps/chatbot/views.py — di sebelum service.chatbot_response()
logger.warning(
    'OPENAI_CALL chatbot user=%s ip=%s sesi=%s msg_len=%d',
    user.id_user if user else 'anon',
    RateLimiter.get_client_ip(request),
    sesi_id,
    len(pesan),
)
```

Lalu di Nginx, jangan log query string yang berisi key:
```nginx
log_format security_audit '$time_iso8601 $remote_addr $request_method $uri $status';
access_log /var/log/nginx/pkimm-audit.log security_audit;
```

Saat anomali, `grep OPENAI_CALL /var/log/gunicorn.log | head -100` →
lihat IP, user, jam.

### Lapisan 7 — Kill-Switch Chatbot Publik

Tambah env variable untuk **disable chatbot publik sepenuhnya** kalau
ada insiden, tanpa redeploy:

```python
# config/settings/base.py
CHATBOT_PUBLIC_ENABLED = env.bool('CHATBOT_PUBLIC_ENABLED', default=True)
```

```python
# apps/chatbot/views.py — di awal ChatbotAPIView.post()
from django.conf import settings

def post(self, request):
    if not settings.CHATBOT_PUBLIC_ENABLED:
        return JsonResponse(
            {'success': False, 'error': 'Layanan chatbot sedang nonaktif sementara.'},
            status=503,
        )
    # ... lanjutkan defense lainnya
```

Aktifkan saat insiden:
```bash
ssh user@server
nano .env
# Tambah baris: CHATBOT_PUBLIC_ENABLED=False
sudo systemctl restart gunicorn
```

### Lapisan 8 — Strong Disclaimer di Suite Pentest

Update [README.md](README.md) dengan peringatan keras agar test
**tidak dijalankan paralel**, dan agar user verify OpenAI dashboard
sebelum dan sesudah.

---

## 5. Quick Action Checklist (Eksekusi Sekarang)

Diurutkan dari paling kritis:

- [ ] **A**. Buka https://platform.openai.com/usage — verifikasi
  total spend bulan ini, identifikasi sumber (model + jam).
- [ ] **B**. Kalau spend > expected → buka
  https://platform.openai.com/account/limits → set **hard limit
  monthly = $5**.
- [ ] **C**. Buka https://platform.openai.com/api-keys → cek **Last
  used** kapan. Kalau ada akses dari lokasi/IP aneh → revoke +
  rotate.
- [ ] **D**. SSH ke VPS → cek nginx log untuk
  `/chatbot/api/send/` dan `/api/berita/koreksi-ai/` dalam 24 jam
  terakhir. Cari pola burst.
- [ ] **E**. Aktifkan **CHATBOT_PUBLIC_ENABLED=False** sementara
  kalau spend masih bertambah cepat (Lapisan 7 di atas).
- [ ] **F**. Apply patch Lapisan 3 (embedding setelah budget check)
  → commit + deploy.
- [ ] **G**. Apply Lapisan 5 (Nginx rate limit) → reload nginx.
- [ ] **H**. Turunkan `MONTHLY_BUDGET` ke `0.50` (Lapisan 4).
- [ ] **I**. Hapus laporan keuangan / rotasi (perpanjangan billing
  awal bulan supaya $1 tidak menumpuk lagi).

---

## 6. Untuk Pentest di Masa Depan

1. **Sebelum jalankan k6**:
   - Catat OpenAI spend saat ini (screenshot dashboard).
   - Catat `BudgetLimiter.get_month_spent()`.
   - Notify oncall (kalau ada).
2. **Saat menjalankan k6**:
   - Jangan run paralel (gunakan [run_all.ps1](run_all.ps1) yang serial).
   - Pause antar test (3 menit cukup untuk reset rate limit).
   - Monitor live OpenAI usage di dashboard.
3. **Setelah jalankan k6**:
   - Tunggu 5 menit (delay billing OpenAI).
   - Refresh dashboard → bandingkan dengan baseline pre-test.
   - **Selisih HARUS ≤ $0.01** untuk suite saya. Kalau > $0.10 →
     stop, investigate sebelum lanjut.
4. **Buat staging environment**:
   - Clone PK_IMM ke subdomain `staging.pkimm-ftik-umko.my.id`.
   - Pakai OpenAI API key TERPISAH dengan hard limit $1/bulan.
   - Run k6 selalu di staging dulu, baru ke production.

---

## 7. Yang Saya BELUM Tahu

Saya jujurkan keterbatasan:

1. **Tidak tahu sumber pasti $1** tanpa data dashboard OpenAI Anda.
2. **Tidak tahu apakah ada kebocoran API key** — perlu cek dashboard.
3. **Tidak tahu apakah ada bot eksternal yang scan chatbot publik**
   selama window k6 — perlu nginx log.
4. **Test 03 dan 07 saya invalid** (CSRF parse fail) sehingga tidak
   bisa konfirmasi/dis-konfirmasi rate limit chatbot via k6. Patch
   test ada di Lapisan 8 atau saya bisa rewrite kalau diminta.

Tapi solusi berlapis 1-7 bekerja **terlepas dari sumbernya** — kalau
diterapkan, kerugian maksimum di masa depan terbatas pada hard limit
yang Anda set di OpenAI dashboard.
