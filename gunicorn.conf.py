"""Konfigurasi Gunicorn untuk PK IMM UMKO.

Strategi:
  - Worker class `gthread`: tepat untuk app I/O-bound (DB query + OpenAI API call)
    karena thread mengantri sambil worker lain tetap proses request lain.
    Sync worker = 1 request per worker = bottleneck saat banyak user.
  - workers = (2 × CPU) + 1, threads = 4. Total konkuren = workers × threads.
    Untuk VPS 2 vCPU: 5 worker × 4 thread = 20 request paralel.
  - max_requests recycle worker secara berkala: cegah memory leak menumpuk
    (sering terjadi pada app dengan PyMuPDF / OpenAI client).
  - timeout 60s: cukup untuk panggilan OpenAI lambat tapi tidak menggantung
    request bermasalah berjam-jam.

Pakai dengan: gunicorn -c gunicorn.conf.py config.wsgi:application
"""
import multiprocessing
import os


def _int_env(name: str, default: int) -> int:
    """Ambil nilai integer dari environment, fallback ke default."""
    try:
        return int(os.environ.get(name, '').strip() or default)
    except (TypeError, ValueError):
        return default


# --- Workers & threads ---------------------------------------------------
# Bisa di-override via env: GUNICORN_WORKERS, GUNICORN_THREADS.
# Default: rumus standar (2*CPU+1) untuk worker, 4 thread per worker.
_cpu = multiprocessing.cpu_count() or 2
workers = _int_env('GUNICORN_WORKERS', _cpu * 2 + 1)
threads = _int_env('GUNICORN_THREADS', 4)
worker_class = 'gthread'

# --- Network -------------------------------------------------------------
bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')

# --- Timeout -------------------------------------------------------------
# OpenAI completion bisa 5-15 detik untuk pesan panjang.
# 60s = batas atas wajar; di atas itu kemungkinan stuck → di-kill.
timeout = _int_env('GUNICORN_TIMEOUT', 60)
graceful_timeout = 30
# Keep-alive: nginx → gunicorn pakai HTTP/1.1 keep-alive, hemat handshake.
keepalive = 5

# --- Worker recycling ----------------------------------------------------
# Restart worker setelah N request supaya memory leak tidak menumpuk.
# Jitter mencegah semua worker restart bersamaan → tidak ada window down.
max_requests = 1000
max_requests_jitter = 100

# --- Logging -------------------------------------------------------------
# Stdout/stderr → di-capture oleh systemd journal (journalctl -u gunicorn-pkimm).
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
# Format access log lebih informatif: tambahkan response time (%(L)s).
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(L)s "%(f)s" "%(a)s"'

# --- Proses --------------------------------------------------------------
# Nama proses memudahkan identifikasi di htop/ps.
proc_name = 'gunicorn-pkimm'
