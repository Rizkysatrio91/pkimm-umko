"""URL conf minimal untuk unit test app penilaian.

Tidak include app yang dibuang di config.settings.test (chatbot/berita/laporan)
supaya import config/urls.py tidak crash saat Django jalankan system checks.

Route yang disertakan hanya dari app yang ter-install di settings test
(accounts, kader, pendaftaran, penilaian, notifikasi) — cukup untuk
test view panitia (interview/aktivitas) yang me-render base.html + sidebar.
"""
from django.urls import include, path

from apps.pendaftaran.urls import absensi_panitia_urlpatterns
from apps.penilaian.urls import panitia_urlpatterns

urlpatterns = [
    path('accounts/', include('apps.accounts.urls')),
    path('notifikasi/', include('apps.notifikasi.urls')),
    path('penilaian/', include('apps.penilaian.urls')),
    path('panitia/', include((panitia_urlpatterns, 'panitia'))),
    path('panitia/absensi/', include((absensi_panitia_urlpatterns, 'absensi_panitia'))),
]
