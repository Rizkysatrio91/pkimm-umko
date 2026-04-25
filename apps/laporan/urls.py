"""Konfigurasi URL untuk app laporan."""
from django.urls import path

from apps.laporan.views import (
    DetailKaderExcelView,
    DetailKaderPDFView,
    DetailKelulusanExcelView,
    DetailKelulusanPDFView,
    DetailPendaftarExcelView,
    DetailPendaftarPDFView,
    KaderExcelView,
    KaderPDFView,
    KelulusanExcelView,
    KelulusanPDFView,
    LaporanView,
    PendaftarExcelView,
    PendaftarPDFView,
)

app_name = 'laporan'

urlpatterns = [
    path('', LaporanView.as_view(), name='index'),

    # PDF (Word → docx2pdf, fallback ke docx)
    path('kader/pdf/',        KaderPDFView.as_view(),      name='kader_pdf'),
    path('pendaftar/pdf/',    PendaftarPDFView.as_view(),  name='pendaftar_pdf'),
    path('kelulusan/pdf/',    KelulusanPDFView.as_view(),  name='kelulusan_pdf'),

    # Excel
    path('kader/excel/',      KaderExcelView.as_view(),     name='kader_excel'),
    path('pendaftar/excel/',  PendaftarExcelView.as_view(), name='pendaftar_excel'),
    path('kelulusan/excel/',  KelulusanExcelView.as_view(), name='kelulusan_excel'),

    # Detail per kader/pendaftar/kelulusan
    path('kader/<int:pk>/detail/pdf/',        DetailKaderPDFView.as_view(),       name='kader_detail_pdf'),
    path('kader/<int:pk>/detail/excel/',      DetailKaderExcelView.as_view(),     name='kader_detail_excel'),
    path('pendaftar/<int:pk>/detail/pdf/',    DetailPendaftarPDFView.as_view(),   name='pendaftar_detail_pdf'),
    path('pendaftar/<int:pk>/detail/excel/',  DetailPendaftarExcelView.as_view(), name='pendaftar_detail_excel'),
    path('kelulusan/<int:pk>/detail/pdf/',    DetailKelulusanPDFView.as_view(),   name='kelulusan_detail_pdf'),
    path('kelulusan/<int:pk>/detail/excel/',  DetailKelulusanExcelView.as_view(), name='kelulusan_detail_excel'),
]
