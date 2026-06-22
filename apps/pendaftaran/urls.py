"""Konfigurasi URL untuk app pendaftaran."""
from django.urls import path

from apps.pendaftaran import views

app_name = 'pendaftaran'

urlpatterns = [
    # Calon Kader
    path('daftar/', views.PendaftaranCreateView.as_view(), name='daftar'),
    path('status/', views.StatusPendaftaranView.as_view(), name='status'),
    path('retry-verifikasi/', views.RetryVerifikasiView.as_view(), name='retry_verifikasi'),
    path('kelulusan/', views.CekKelulusanView.as_view(), name='kelulusan'),
    # Calon Kader: Rundown & Absensi
    path('rundown/', views.RundownPublicView.as_view(), name='rundown_public'),
    path('absensi/', views.AbsensiScanView.as_view(), name='absensi_scan'),
    path('absensi/validate/', views.AbsensiValidateView.as_view(), name='absensi_validate'),
    path('absensi/riwayat/', views.AbsensiRiwayatView.as_view(), name='absensi_riwayat'),
    path('absensi/scan/<uuid:token>/', views.AbsensiScanDirectView.as_view(), name='absensi_scan_direct'),
]

# Admin pendaftaran — akan disertakan di bawah /admin-dashboard/pendaftaran/
admin_urlpatterns = [
    path('', views.AdminPendaftaranListView.as_view(), name='admin_list'),
    path('<int:pk>/', views.AdminPendaftaranDetailView.as_view(), name='admin_detail'),
    path('<int:pk>/retry-verifikasi/', views.AdminRetryVerifikasiView.as_view(), name='admin_retry_verifikasi'),
]

# Admin periode DAD — akan disertakan di bawah /admin-dashboard/periode-dad/
periode_urlpatterns = [
    path('', views.PeriodeListView.as_view(), name='periode_list'),
    path('tambah/', views.PeriodeCreateView.as_view(), name='periode_create'),
    path('<int:pk>/edit/', views.PeriodeUpdateView.as_view(), name='periode_update'),
    path('<int:pk>/hapus/', views.PeriodeDeleteView.as_view(), name='periode_delete'),
    path('<int:pk>/toggle/', views.PeriodeToggleActiveView.as_view(), name='periode_toggle'),
]

# Admin kelompok DAD — akan disertakan di bawah /admin-dashboard/kelompok/
kelompok_admin_urlpatterns = [
    path('', views.KelompokListView.as_view(), name='kelompok_list'),
    path('assign-otomatis/', views.KelompokAssignOtomatisView.as_view(), name='assign_otomatis'),
    path('<int:pk>/set-pj/', views.KelompokSetPJView.as_view(), name='set_pj'),
    path('<int:pk>/pindah/', views.KelompokPindahAnggotaView.as_view(), name='pindah_anggota'),
]

# Admin rundown DAD — akan disertakan di bawah /admin-dashboard/rundown/
rundown_admin_urlpatterns = [
    path('', views.RundownListView.as_view(), name='rundown_list'),
    path('tambah/', views.RundownCreateView.as_view(), name='rundown_create'),
    path('<int:pk>/edit/', views.RundownUpdateView.as_view(), name='rundown_update'),
    path('ubah-tanggal/', views.RundownTanggalUpdateView.as_view(), name='rundown_tanggal_update'),
    path('<int:pk>/hapus/', views.RundownDeleteView.as_view(), name='rundown_delete'),
    path('generate-qr/', views.GenerateAllQRView.as_view(), name='generate_qr'),
]

# Panitia absensi — akan disertakan di bawah /panitia/absensi/
absensi_panitia_urlpatterns = [
    path('', views.PanitiaAbsensiListView.as_view(), name='absensi_list'),
    path('<int:qr_id>/activate/', views.PanitiaQRActivateView.as_view(), name='qr_activate'),
    path('<int:qr_id>/deactivate/', views.PanitiaQRDeactivateView.as_view(), name='qr_deactivate'),
    path('<int:qr_id>/show/', views.PanitiaQRShowView.as_view(), name='qr_show'),
    path('<int:qr_id>/download/', views.PanitiaQRDownloadView.as_view(), name='qr_download'),
    path('<int:qr_id>/status/', views.PanitiaAbsensiStatusView.as_view(), name='qr_status'),
    path('rekap/', views.PanitiaRekapAbsensiView.as_view(), name='rekap_absensi'),
]
