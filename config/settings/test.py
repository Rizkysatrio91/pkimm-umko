"""Settings khusus untuk menjalankan unit test.

Tujuan: isolasi penuh dari DB production. Pakai SQLite in-memory dan
buang app yang membutuhkan ekstensi DB khusus (pgvector) atau library
berat yang tidak relevan untuk test unit service/model.

Aktivasi:
    python manage.py test --settings=config.settings.test apps.penilaian.tests
"""
from config.settings.base import *  # noqa: F401, F403
from config.settings.base import INSTALLED_APPS

# DB in-memory: super cepat, tidak ada side-effect ke DB development/production.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

# Buang app yang memakai pgvector (chatbot) dan app lain yang tidak diperlukan
# untuk unit test penilaian/pendaftaran. Mengurangi waktu migrasi & menghindari
# error ekstensi DB yang tidak tersedia di SQLite.
_SKIP_APPS = {'apps.chatbot', 'apps.berita', 'apps.laporan'}
INSTALLED_APPS = [a for a in INSTALLED_APPS if a not in _SKIP_APPS]

# Password hasher cepat → test setup user jauh lebih cepat.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Matikan email backend supaya tidak ada side-effect SMTP saat test
# (kalau ada kode signal yang kirim email).
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Storage in-memory untuk media (foto profil) supaya tidak menulis ke disk.
DEFAULT_FILE_STORAGE = 'django.core.files.storage.InMemoryStorage'

# Pakai URL conf minimal — config/urls.py mengimpor view dari berita/chatbot/
# laporan yang kita buang dari INSTALLED_APPS untuk test ini.
ROOT_URLCONF = 'apps.penilaian.tests.test_urls'
