# Deploy: Aktivasi Cloudflare di depan VPS

Dokumen ini langkah-langkah men-deploy perubahan rate limiter yang sudah CF-aware
dan memasang Cloudflare sebagai proxy di depan VPS.

## Ringkasan perubahan

| File | Perubahan |
|------|-----------|
| [core/cloudflare_ips.py](../core/cloudflare_ips.py) | **Baru.** Daftar IP edge CF resmi + helper `is_cloudflare_ip()`. |
| [core/rate_limiter.py](../core/rate_limiter.py) | `get_client_ip` sekarang percaya `CF-Connecting-IP` **hanya** bila XFF rightmost ada di range CF. |
| [core/tests/test_rate_limiter.py](../core/tests/test_rate_limiter.py) | **Baru.** 17 test — termasuk skenario spoofing `CF-Connecting-IP`. |
| [deploy/nginx_cloudflare.conf](nginx_cloudflare.conf) | **Baru.** Snippet nginx `set_real_ip_from` + `real_ip_header CF-Connecting-IP`. |

## Prasyarat (di sisi Cloudflare)

1. Tambahkan domain `pkimm-ftik-umko.my.id` ke akun Cloudflare.
2. Ubah nameserver di registrar ke nameserver Cloudflare.
3. Tunggu status zona **Active** di dashboard CF (umumnya 1–2 jam).
4. Set DNS A record:
   - **Name:** `@` (atau subdomain yang dipakai)
   - **Content:** IP publik VPS
   - **Proxy status:** **Proxied (orange cloud)** — wajib agar CF jadi reverse proxy.
5. SSL/TLS mode di CF dashboard → **Full (strict)** setelah Let's Encrypt aktif
   di origin (atau **Full** sementara, sebelum Let's Encrypt). Jangan pakai
   **Flexible** (XSS-safe CSRF rusak karena origin tetap di-HTTP).

> **Jangan deploy ke VPS sebelum CF "Active"** — request ke domain belum melewati edge CF, jadi nginx akan melihat IP user langsung (REMOTE_ADDR publik), bukan IP edge CF. Konfigurasi `set_real_ip_from` baru bermakna setelah lalu lintas masuk via CF.

## Langkah deploy di VPS (sesudah CF Active)

```bash
# 1. SSH ke VPS, masuk ke direktori proyek
ssh user@vps.example.com
cd /var/www/pk-imm-umko

# 2. Pull perubahan
git pull origin main

# 3. Pasang snippet nginx CF
sudo cp deploy/nginx_cloudflare.conf /etc/nginx/conf.d/cloudflare.conf

# 4. Test nginx config
sudo nginx -t

# 5. Reload nginx
sudo systemctl reload nginx

# 6. Restart Gunicorn (perubahan core/* perlu reload Python)
sudo systemctl restart gunicorn  # atau: sudo systemctl restart pk-imm
```

## Verifikasi pasca-deploy

### 1. Cek IP user terlihat benar di Django logs

Setelah deploy, akses situs dari browser pribadi. Di log nginx (`/var/log/nginx/access.log`)
seharusnya muncul IP rumah Anda — **bukan** IP edge CF (`104.x` / `172.x`).

```bash
sudo tail -f /var/log/nginx/access.log
```

Kalau yang muncul IP `104.x` / `172.x` / `162.x`, berarti `set_real_ip_from`
belum aktif. Cek bahwa file snippet ter-include:

```bash
sudo nginx -T 2>/dev/null | grep -i "set_real_ip_from"
```

### 2. Smoke test rate limiter via curl

Dari browser/curl pribadi:

```bash
# Kirim 6 percobaan login dengan kredensial salah (limit 5/15 menit)
for i in {1..6}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://pkimm-ftik-umko.my.id/accounts/login/ \
    -d "username=spam&password=wrong"
done
```

Request ke-6 seharusnya `429` atau halaman login dengan pesan rate-limit
**dari IP Anda saja** (orang lain tetap bisa login). Kalau request ke-6 lolos
dan tidak ada limit, berarti `get_client_ip` masih lihat IP CF (semua user
dianggap satu IP, atau worse: bypass).

### 3. Jalankan suite k6 (anti-regresi)

```bash
cd security_tests
k6 run -e BASE_URL=https://pkimm-ftik-umko.my.id tests/07_ip_spoofing.js
```

Suite `07_ip_spoofing.js` harus tetap menunjukkan ≥21 dari 30 request
ditolak (threshold `spoof_blocked >= 21`).

### 4. Pastikan origin tidak bisa diakses langsung via IP (opsional, defense-in-depth)

Setelah CF aktif, idealnya VPS firewall hanya menerima port 80/443 dari
range CF (lihat https://www.cloudflare.com/ips-v4/). Contoh ufw:

```bash
# Allow SSH (jangan diblok!)
sudo ufw allow 22/tcp

# Drop akses 80/443 dari semua, kecuali range CF
sudo ufw default deny incoming
for cidr in 173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 \
            103.31.4.0/22 141.101.64.0/18 108.162.192.0/18 \
            190.93.240.0/20 188.114.96.0/20 197.234.240.0/22 \
            198.41.128.0/17 162.158.0.0/15 104.16.0.0/13 \
            104.24.0.0/14 172.64.0.0/13 131.0.72.0/22; do
  sudo ufw allow from $cidr to any port 80,443 proto tcp
done
sudo ufw enable
```

Tanpa langkah ini, penyerang yang tahu IP origin masih bisa lewati CF
(tapi `get_client_ip` sudah tidak akan percaya `CF-Connecting-IP` palsu —
itu lapis pertahanan kedua di kode).

## Rollback bila ada masalah

```bash
# Hapus snippet CF
sudo rm /etc/nginx/conf.d/cloudflare.conf
sudo nginx -t && sudo systemctl reload nginx

# Revert kode di VPS
cd /var/www/pk-imm-umko
git log --oneline -5            # cari commit sebelum CF
git revert <commit-cf-fix>      # atau git reset --hard <commit-lama>
sudo systemctl restart gunicorn

# Di dashboard CF: ubah proxy status DNS dari orange (proxied) ke
# grey (DNS only) — lalu lintas langsung ke origin tanpa CF.
```

## Update daftar IP CF

CF jarang mengubah range, tapi pantau https://www.cloudflare.com/ips/.
Saat ada perubahan, update **dua tempat**:

1. [core/cloudflare_ips.py](../core/cloudflare_ips.py) — list `_CF_IPV4_RANGES` / `_CF_IPV6_RANGES`.
2. [deploy/nginx_cloudflare.conf](nginx_cloudflare.conf) — direktif `set_real_ip_from`.

Lalu jalankan test + reload nginx + restart gunicorn.
