"""Konfigurasi URL untuk app penilaian."""
from django.urls import path

from apps.penilaian import views

app_name = 'penilaian'

urlpatterns = [
    # Leaderboard (semua user yang sudah login)
    path('leaderboard/', views.LeaderboardView.as_view(), name='leaderboard'),
]

# Route panitia — disertakan di bawah /panitia/
panitia_urlpatterns = [
    path('dashboard/', views.PanitiaDashboardView.as_view(), name='panitia_dashboard'),
    path('interview/', views.InterviewListView.as_view(), name='interview_list'),
    path('interview/<int:pendaftaran_id>/nilai/', views.InterviewCreateView.as_view(), name='interview_create'),
    path('interview/detail/<int:pk>/', views.InterviewDetailView.as_view(), name='interview_detail'),
    path('aktivitas/', views.AktivitasListView.as_view(), name='aktivitas_list'),
    path('aktivitas/<int:pendaftaran_id>/hari/<int:hari_ke>/', views.AktivitasCreateView.as_view(), name='aktivitas_create'),
]

# Admin kelulusan — disertakan di bawah /admin-dashboard/
admin_urlpatterns = [
    path('kelulusan/', views.PenetapanKelulusanView.as_view(), name='penetapan_kelulusan'),
]
