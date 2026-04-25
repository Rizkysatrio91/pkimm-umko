"""Konfigurasi URL root untuk proyek PK IMM FTIK UMKO."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts.admin_urls import urlpatterns as user_admin_urls
from apps.berita.urls import api_urlpatterns as berita_api_urls
from apps.berita.urls import penulis_urlpatterns as penulis_urls
from apps.berita.urls import profil_admin_urlpatterns as profil_admin_urls
from apps.berita.urls import profil_urlpatterns as profil_urls
from apps.berita.views import BerandaView
from apps.chatbot.urls import admin_urlpatterns as chatbot_admin_urls
from apps.chatbot.views import ChatbotKaderView
from apps.kader.urls import admin_urlpatterns as kader_admin_urls
from apps.kader.urls import api_urlpatterns as kader_api_urls
from apps.pendaftaran.urls import absensi_panitia_urlpatterns as absensi_panitia_urls
from apps.pendaftaran.urls import admin_urlpatterns as pendaftaran_admin_urls
from apps.pendaftaran.urls import kelompok_admin_urlpatterns as kelompok_admin_urls
from apps.pendaftaran.urls import periode_urlpatterns as periode_admin_urls
from apps.pendaftaran.urls import rundown_admin_urlpatterns as rundown_admin_urls
from apps.pendaftaran.views import AdminDashboardView
from apps.penilaian.urls import admin_urlpatterns as penilaian_admin_urls
from apps.penilaian.urls import panitia_urlpatterns as panitia_urls

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('ckeditor5/', include('django_ckeditor_5.urls')),
    # Halaman beranda publik
    path('', BerandaView.as_view(), name='beranda'),
    # Profil organisasi (publik)
    path('profil/', include((profil_urls, 'profil'))),
    # Include URL tiap app
    path('accounts/', include('apps.accounts.urls')),
    path('kader/', include('apps.kader.urls')),
    path('pendaftaran/', include('apps.pendaftaran.urls')),
    path('penilaian/', include('apps.penilaian.urls')),
    path('berita/', include('apps.berita.urls')),
    path('chatbot/', include('apps.chatbot.urls')),
    path('notifikasi/', include('apps.notifikasi.urls')),
    path('admin-dashboard/laporan/', include('apps.laporan.urls')),
    # Endpoint API
    path('api/', include((berita_api_urls, 'api'))),
    path('api/', include((kader_api_urls, 'kader_api'))),
    # Route CRUD admin
    path('admin-dashboard/users/', include((user_admin_urls, 'user_admin'))),
    path('admin-dashboard/kader/', include((kader_admin_urls, 'kader_admin'))),
    path('admin-dashboard/pendaftaran/', include((pendaftaran_admin_urls, 'pendaftaran_admin'))),
    path('admin-dashboard/periode-dad/', include((periode_admin_urls, 'periode_admin'))),
    path('admin-dashboard/kelompok/', include((kelompok_admin_urls, 'kelompok_admin'))),
    path('admin-dashboard/rundown/', include((rundown_admin_urls, 'rundown_admin'))),
    path('admin-dashboard/chatbot/', include((chatbot_admin_urls, 'chatbot_admin'))),
    path('admin-dashboard/profil/', include((profil_admin_urls, 'profil_admin'))),
    path('admin-dashboard/', include((penilaian_admin_urls, 'penilaian_admin'))),
    # Route panitia
    path('panitia/', include((panitia_urls, 'panitia'))),
    path('panitia/absensi/', include((absensi_panitia_urls, 'absensi_panitia'))),
    # Route penulis
    path('penulis/', include((penulis_urls, 'penulis'))),
    # Route dashboard
    path('admin-dashboard/', AdminDashboardView.as_view(), name='admin_dashboard'),
    # Chatbot kader
    path('kader/chatbot/', ChatbotKaderView.as_view(), name='kader_chatbot'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
