"""Konfigurasi URL untuk app berita."""
from django.urls import path

from apps.berita import views

app_name = 'berita'

urlpatterns = [
    path('', views.BeritaListView.as_view(), name='list'),
    path('<slug:slug>/', views.BeritaDetailView.as_view(), name='detail'),
]

penulis_urlpatterns = [
    path('dashboard/', views.PenulisDashboardView.as_view(), name='penulis_dashboard'),
    path('berita/tulis/', views.BeritaCreateView.as_view(), name='berita_create'),
    path('berita/<int:pk>/edit/', views.BeritaUpdateView.as_view(), name='berita_update'),
    path('berita/<int:pk>/hapus/', views.BeritaDeleteView.as_view(), name='berita_delete'),
]

api_urlpatterns = [
    path('berita/koreksi-ai/', views.KoreksiAIView.as_view(), name='koreksi_ai'),
]

# Profil Organisasi (publik)
profil_urlpatterns = [
    path('struktur-organisasi/', views.StrukturOrganisasiView.as_view(), name='struktur'),
    path('visi-misi/', views.VisiMisiPublikView.as_view(), name='visi_misi'),
    path('sejarah/', views.SejarahPublikView.as_view(), name='sejarah'),
]

# Admin CRUD: Kata Sambutan, Visi Misi, Sejarah
profil_admin_urlpatterns = [
    path('sambutan/', views.SambutanListView.as_view(), name='sambutan_list'),
    path('sambutan/tambah/', views.SambutanCreateView.as_view(), name='sambutan_create'),
    path('sambutan/<int:pk>/edit/', views.SambutanUpdateView.as_view(), name='sambutan_update'),
    path('sambutan/<int:pk>/hapus/', views.SambutanDeleteView.as_view(), name='sambutan_delete'),
    path('visi-misi/', views.VisiMisiListView.as_view(), name='visimisi_list'),
    path('visi-misi/tambah/', views.VisiMisiCreateView.as_view(), name='visimisi_create'),
    path('visi-misi/<int:pk>/edit/', views.VisiMisiUpdateView.as_view(), name='visimisi_update'),
    path('visi-misi/<int:pk>/hapus/', views.VisiMisiDeleteView.as_view(), name='visimisi_delete'),
    path('sejarah/', views.SejarahListView.as_view(), name='sejarah_list'),
    path('sejarah/tambah/', views.SejarahCreateView.as_view(), name='sejarah_create'),
    path('sejarah/<int:pk>/edit/', views.SejarahUpdateView.as_view(), name='sejarah_update'),
    path('sejarah/<int:pk>/hapus/', views.SejarahDeleteView.as_view(), name='sejarah_delete'),
]
