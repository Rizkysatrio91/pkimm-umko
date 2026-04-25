"""Konfigurasi URL untuk app kader."""
from django.urls import path

from apps.kader import views
from apps.kader.api_views import ProdiByFakultasView, SSOLookupView

app_name = 'kader'

urlpatterns = [
    # Calon Kader
    path('dashboard/', views.KaderDashboardView.as_view(), name='dashboard'),
    path('biodata/', views.BiodataView.as_view(), name='biodata'),
]

# API endpoint
api_urlpatterns = [
    path('prodi/', ProdiByFakultasView.as_view(), name='api_prodi_by_fakultas'),
    path('sso-mahasiswa/', SSOLookupView.as_view(), name='api_sso_mahasiswa'),
]

# Admin kader CRUD — akan disertakan di bawah /admin-dashboard/kader/
admin_urlpatterns = [
    path('', views.KaderListView.as_view(), name='admin_list'),
    path('tambah/', views.KaderCreateView.as_view(), name='admin_create'),
    path('upload/', views.KaderExcelUploadView.as_view(), name='admin_upload'),
    path('upload/template/', views.KaderExcelTemplateView.as_view(), name='admin_upload_template'),
    path('<int:pk>/edit/', views.KaderUpdateView.as_view(), name='admin_update'),
    path('<int:pk>/hapus/', views.KaderDeleteView.as_view(), name='admin_delete'),
    path('konfigurasi/', views.KonfigurasiFakultasView.as_view(), name='konfigurasi_fakultas'),
]
