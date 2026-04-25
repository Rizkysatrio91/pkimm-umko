# Sistem Manajemen PK IMM UMKO

Sistem manajemen Pimpinan Komisariat Ikatan Mahasiswa Muhammadiyah (PK IMM) Universitas Muhammadiyah Kotabumi (UMKO) berbasis Web Mobile dengan integrasi **Artificial Intelligence**.

Fitur utama:
- Manajemen anggota dan pendaftaran DAD (Darul Arqom Dasar) end-to-end
- Verifikasi NPM otomatis via SSO UMKO
- Asisten Virtual (Chatbot) berbasis OpenAI untuk layanan informasi
- Smart Editor untuk publikasi berita dengan koreksi AI
- QR Absensi dengan rekap kehadiran
- Penilaian interview & aktivitas harian + leaderboard
- Penetapan kelulusan dengan passing grade dinamis
- Laporan PDF/Excel rekapitulasi

## Teknologi

| Layer | Stack |
|---|---|
| Backend | Python 3.12, Django 5.x |
| Database | PostgreSQL 16 |
| Frontend | Tailwind CSS (CDN) + Alpine.js |
| AI | OpenAI API (GPT) |
| Editor | CKEditor 5 |
| Image | Pillow + PyMuPDF |
| Report | xhtml2pdf, openpyxl, python-docx |

## Persyaratan Sistem

- Python **3.12** atau lebih baru
- PostgreSQL **14** atau lebih baru
- Akun OpenAI dengan API key (untuk fitur chatbot & smart editor)
- Akun email Gmail dengan App Password (untuk OTP)

## Instalasi (Pengembangan Lokal)

### 1. Clone repository

```bash
git clone https://github.com/USERNAME/REPO_NAME.git
cd REPO_NAME
```

### 2. Buat virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 3. Install dependensi

```bash
pip install -r requirements.txt
```

### 4. Siapkan PostgreSQL

Login ke psql lalu jalankan:

```sql
CREATE DATABASE db_pk_imm;
CREATE USER pk_imm_user WITH PASSWORD 'password_aman_anda';
GRANT ALL PRIVILEGES ON DATABASE db_pk_imm TO pk_imm_user;
```

### 5. Konfigurasi environment

```bash
# Salin template
cp .env.example .env

# Edit .env dan isi nilai sesuai environment Anda
# (SECRET_KEY, DATABASE_URL, OPENAI_API_KEY, dll.)
```

Generate `SECRET_KEY` baru:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 6. Migrasi database

```bash
python manage.py migrate
```

### 7. Buat superuser

```bash
python manage.py createsuperuser
```

### 8. Jalankan server

```bash
python manage.py runserver
```

Akses di: `http://127.0.0.1:8000`

## Deploy ke VPS Production

### Ringkasan langkah

1. Setup server (Ubuntu 22.04+, install Python, PostgreSQL, Nginx, Gunicorn)
2. Clone repository ke VPS via `git clone`
3. Buat virtual environment & install requirements
4. Buat file `.env` dengan kredensial production (DEBUG=False, SECRET_KEY baru)
5. Migrasi database & collect static files
6. Setup Gunicorn sebagai service (systemd)
7. Setup Nginx sebagai reverse proxy
8. Aktifkan HTTPS via Let's Encrypt (certbot)

### Variabel environment kritis untuk production

```env
DEBUG=False
ALLOWED_HOSTS=domainanda.com,www.domainanda.com
SECRET_KEY=<generate-baru-untuk-production>
DATABASE_URL=postgres://user:pass@127.0.0.1:5432/DB_PK_IMM
```

### Perintah esensial setelah deploy

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

## Struktur Proyek

```
PK_IMM/
├── apps/                       # Django apps
│   ├── accounts/               # Autentikasi, User multi-role, OTP
│   ├── kader/                  # Biodata kader, fakultas, prodi
│   ├── pendaftaran/            # Pendaftaran DAD, periode, kelompok
│   ├── penilaian/              # Interview, aktivitas, QR absensi, leaderboard
│   ├── berita/                 # Publikasi berita dengan AI
│   ├── chatbot/                # Asisten virtual + dataset
│   ├── notifikasi/             # Sistem notifikasi
│   └── laporan/                # Generator PDF/Excel
├── config/
│   ├── settings/
│   │   ├── base.py             # Settings dasar
│   │   ├── development.py      # Override untuk development
│   │   └── production.py       # Override untuk production
│   ├── urls.py
│   └── wsgi.py
├── core/                       # Service layer, validators, constants
├── static/                     # CSS, JS, images
├── templates/                  # HTML templates
├── manage.py
├── requirements.txt
├── .env.example                # Template environment variables
└── .gitignore
```

## Keamanan

Sebelum production, pastikan:

- [ ] `DEBUG=False` di file `.env` production
- [ ] `SECRET_KEY` di-generate baru, tidak pakai dari development
- [ ] `ALLOWED_HOSTS` hanya berisi domain/IP yang sah
- [ ] Password database PostgreSQL kuat (minimal 16 karakter, mix huruf+angka+simbol)
- [ ] Password user `postgres` di-rotate setelah setup awal
- [ ] HTTPS aktif (certbot Let's Encrypt)
- [ ] Firewall (ufw) hanya buka port 22 (SSH), 80, 443
- [ ] File `.env` permission 600 (`chmod 600 .env`)

## Lisensi

Proyek ini dibuat untuk keperluan tugas akhir/skripsi di Universitas Muhammadiyah Kotabumi.
