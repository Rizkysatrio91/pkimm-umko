"""Konfigurasi URL untuk app notifikasi."""
from django.urls import path

from apps.notifikasi.views import (
    NotifikasiListView,
    NotifikasiMarkAllReadView,
    NotifikasiMarkReadView,
)

app_name = 'notifikasi'

urlpatterns = [
    path('', NotifikasiListView.as_view(), name='list'),
    path('<int:pk>/read/', NotifikasiMarkReadView.as_view(), name='mark_read'),
    path('read-all/', NotifikasiMarkAllReadView.as_view(), name='mark_all_read'),
]
