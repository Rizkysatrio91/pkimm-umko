"""Pengaturan dasar untuk proyek PK IMM FTIK UMKO."""
import os
from pathlib import Path

import environ

# Path dasar proyek
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Variabel environment
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# Keamanan
SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

# Definisi aplikasi
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Library pihak ketiga
    'django_ckeditor_5',
    # Aplikasi lokal
    'apps.accounts',
    'apps.kader',
    'apps.pendaftaran',
    'apps.penilaian',
    'apps.berita',
    'apps.chatbot',
    'apps.notifikasi',
    'apps.laporan',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.global_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3')
}

# Autentikasi
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/accounts/redirect/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Validasi password — min_length eksplisit 8 supaya Django admin / createsuperuser
# juga mematuhi kebijakan panjang minimum (form login/register sudah validate
# ini + upper/lower/digit/special; validator ini menutup celah bypass via admin).
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Batas ukuran upload — melindungi dari user upload file besar
# (mis. foto 50 MB atau attachment polyglot yang sangat besar).
# DATA_UPLOAD_MAX_MEMORY_SIZE: batas total body POST (form multipart + field text)
# FILE_UPLOAD_MAX_MEMORY_SIZE: batas ukuran per-file; di atas itu → temp file di disk
# Naik ke 12 MB untuk akomodasi upload PDF dokumen pengetahuan RAG (max 10 MB
# per file + overhead form).
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# Internasionalisasi
LANGUAGE_CODE = 'id'
TIME_ZONE = 'Asia/Jakarta'
USE_I18N = True
USE_TZ = True

# File statis
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# File media
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Tipe field primary key default
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Konfigurasi CKEditor 5
CKEDITOR_5_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
CKEDITOR_5_UPLOAD_PATH = "ckeditor/"

CKEDITOR_5_CONFIGS = {
    'default': {
        # Catatan: tombol 'sourceEditing' SENGAJA DIHAPUS. Tombol itu memberi
        # admin/penulis kemampuan mengetik HTML mentah (termasuk <script>/<iframe>)
        # yang kemudian di-render ke halaman publik via {{ ...|safe }}.
        # Tanpa sourceEditing, konten hanya bisa dibentuk via tombol toolbar
        # yang sanitize otomatis — fungsi edit WYSIWYG tetap utuh.
        'toolbar': [
            'heading', '|',
            'bold', 'italic', 'underline', 'strikethrough', '|',
            'fontSize', 'fontColor', 'fontBackgroundColor', '|',
            'alignment', '|',
            'bulletedList', 'numberedList', 'todoList', '|',
            'outdent', 'indent', '|',
            'blockQuote', 'insertTable', 'link', '|',
            'imageUpload', 'mediaEmbed', '|',
            'undo', 'redo', '|',
            'removeFormat',
        ],
        'image': {
            'toolbar': [
                'imageTextAlternative', 'imageStyle:inline',
                'imageStyle:block', 'imageStyle:side',
            ],
        },
        'table': {
            'contentToolbar': [
                'tableColumn', 'tableRow', 'mergeTableCells',
                'tableProperties', 'tableCellProperties',
            ],
        },
        'heading': {
            'options': [
                {'model': 'paragraph', 'title': 'Paragraph', 'class': 'ck-heading_paragraph'},
                {'model': 'heading1', 'view': 'h1', 'title': 'Heading 1', 'class': 'ck-heading_heading1'},
                {'model': 'heading2', 'view': 'h2', 'title': 'Heading 2', 'class': 'ck-heading_heading2'},
                {'model': 'heading3', 'view': 'h3', 'title': 'Heading 3', 'class': 'ck-heading_heading3'},
            ],
        },
        'language': 'id',
        'height': '400px',
        'width': '100%',
    },
}

# Konfigurasi Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'pk-imm-cache',
    }
}

# Konfigurasi OpenAI
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
OPENAI_MODEL = env('OPENAI_MODEL', default='gpt-4o-mini')
# Admin API key (sk-admin-...) untuk endpoint billing/usage (opsional).
# Jika kosong, dashboard admin tetap jalan pakai tracking lokal (BudgetLimiter).
OPENAI_ADMIN_API_KEY = env('OPENAI_ADMIN_API_KEY', default='')

# Konfigurasi SSO UMKO API
SSO_API_BASE_URL = env('SSO_API_BASE_URL', default='https://sso.umko.ac.id/api/v1')
SSO_API_KEY = env('SSO_API_KEY', default='')
SSO_SECRET_KEY = env('SSO_SECRET_KEY', default='')

# Konfigurasi Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@pk-imm-umko.com')
