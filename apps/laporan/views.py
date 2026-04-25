"""Views untuk app laporan — filter berdasarkan periode (dropdown bulan + tahun)."""
from datetime import datetime

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import TemplateView

from apps.kader.models import BiodataKader
from apps.laporan.services import NAMA_BULAN, LaporanService
from apps.pendaftaran.models import PendaftaranDAD
from apps.penilaian.models import RekapLeaderboard
from core.mixins import AdminRequiredMixin

XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _parse_periode(periode_value: str) -> tuple:
    """
    Parse string "YYYY-MM".
    Return (year_int, month_int, label_str).
    Jika kosong atau tidak valid, return (None, None, 'Semua Periode').
    """
    if not periode_value:
        return None, None, 'Semua Periode'
    try:
        year_str, month_str = periode_value.split('-')
        year, month = int(year_str), int(month_str)
        label = f'{NAMA_BULAN[month - 1]} {year}'
        return year, month, label
    except (ValueError, IndexError):
        return None, None, 'Semua Periode'


class LaporanView(AdminRequiredMixin, TemplateView):
    """Halaman pilih jenis laporan + filter periode."""

    template_name = 'laporan/laporan.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        now = datetime.now()
        choices = []
        for year in range(2025, now.year + 1):
            for month in range(1, 13):
                if year == now.year and month > now.month:
                    break
                choices.append({
                    'value': f'{year}-{month:02d}',
                    'label': f'{NAMA_BULAN[month - 1]} {year}',
                })
        ctx['bulan_tahun_choices'] = list(reversed(choices))

        # Opsi per-kader untuk unduhan detail
        ctx['kader_choices'] = list(
            BiodataKader.objects
            .exclude(jabatan_struktural='calon')
            .order_by('nama_lengkap')
            .values('id_biodata', 'nama_lengkap', 'npm')
        )
        ctx['pendaftar_choices'] = list(
            PendaftaranDAD.objects
            .select_related('id_biodata')
            .order_by('id_biodata__nama_lengkap')
            .values(
                'id_pendaftaran', 'no_registrasi',
                'id_biodata__nama_lengkap', 'id_biodata__npm',
            )
        )
        ctx['kelulusan_choices'] = list(
            RekapLeaderboard.objects
            .select_related('id_pendaftaran__id_biodata')
            .order_by('peringkat')
            .values(
                'id_rekap', 'peringkat',
                'id_pendaftaran__no_registrasi',
                'id_pendaftaran__id_biodata__nama_lengkap',
                'id_pendaftaran__id_biodata__npm',
            )
        )
        return ctx


# ═════════════════════════════════════════════════════════════════
# Rekap Data Kader
# ═════════════════════════════════════════════════════════════════

class KaderPDFView(AdminRequiredMixin, View):
    def get(self, request):
        year, month, label = _parse_periode(request.GET.get('periode', ''))
        qs = BiodataKader.objects.exclude(jabatan_struktural='calon')
        if year and month:
            qs = qs.filter(updated_at__year=year, updated_at__month=month)

        data, ctype, ext = LaporanService.generate_rekap_kader_pdf(qs, label, request.user)
        response = HttpResponse(data, content_type=ctype)
        response['Content-Disposition'] = f'attachment; filename="laporan_kader.{ext}"'
        return response


class KaderExcelView(AdminRequiredMixin, View):
    def get(self, request):
        year, month, label = _parse_periode(request.GET.get('periode', ''))
        qs = BiodataKader.objects.exclude(jabatan_struktural='calon')
        if year and month:
            qs = qs.filter(updated_at__year=year, updated_at__month=month)

        excel = LaporanService.generate_rekap_kader_excel(qs, label, request.user)
        response = HttpResponse(excel, content_type=XLSX_TYPE)
        response['Content-Disposition'] = 'attachment; filename="laporan_kader.xlsx"'
        return response


# ═════════════════════════════════════════════════════════════════
# Rekap Pendaftar DAD
# ═════════════════════════════════════════════════════════════════

class PendaftarPDFView(AdminRequiredMixin, View):
    def get(self, request):
        year, month, label = _parse_periode(request.GET.get('periode', ''))
        qs = PendaftaranDAD.objects.select_related('id_biodata').all()
        if year and month:
            qs = qs.filter(tgl_daftar__year=year, tgl_daftar__month=month)

        data, ctype, ext = LaporanService.generate_rekap_pendaftar_pdf(qs, label, request.user)
        response = HttpResponse(data, content_type=ctype)
        response['Content-Disposition'] = f'attachment; filename="laporan_pendaftar.{ext}"'
        return response


class PendaftarExcelView(AdminRequiredMixin, View):
    def get(self, request):
        year, month, label = _parse_periode(request.GET.get('periode', ''))
        qs = PendaftaranDAD.objects.select_related('id_biodata').all()
        if year and month:
            qs = qs.filter(tgl_daftar__year=year, tgl_daftar__month=month)

        excel = LaporanService.generate_rekap_pendaftar_excel(qs, label, request.user)
        response = HttpResponse(excel, content_type=XLSX_TYPE)
        response['Content-Disposition'] = 'attachment; filename="laporan_pendaftar.xlsx"'
        return response


# ═════════════════════════════════════════════════════════════════
# Rekap Kelulusan DAD
# ═════════════════════════════════════════════════════════════════

class KelulusanPDFView(AdminRequiredMixin, View):
    def get(self, request):
        year, month, label = _parse_periode(request.GET.get('periode', ''))
        qs = RekapLeaderboard.objects.select_related(
            'id_pendaftaran__id_biodata'
        ).filter(id_pendaftaran__status_kelulusan='lulus').order_by('peringkat')
        if year and month:
            qs = qs.filter(updated_at__year=year, updated_at__month=month)

        data, ctype, ext = LaporanService.generate_rekap_kelulusan_pdf(qs, label, request.user)
        response = HttpResponse(data, content_type=ctype)
        response['Content-Disposition'] = f'attachment; filename="laporan_kelulusan.{ext}"'
        return response


class KelulusanExcelView(AdminRequiredMixin, View):
    def get(self, request):
        year, month, label = _parse_periode(request.GET.get('periode', ''))
        qs = RekapLeaderboard.objects.select_related(
            'id_pendaftaran__id_biodata'
        ).filter(id_pendaftaran__status_kelulusan='lulus').order_by('peringkat')
        if year and month:
            qs = qs.filter(updated_at__year=year, updated_at__month=month)

        excel = LaporanService.generate_rekap_kelulusan_excel(qs, label, request.user)
        response = HttpResponse(excel, content_type=XLSX_TYPE)
        response['Content-Disposition'] = 'attachment; filename="laporan_kelulusan.xlsx"'
        return response


# ═════════════════════════════════════════════════════════════════
# Detail per Kader / Pendaftar / Kelulusan (PDF + Excel)
# ═════════════════════════════════════════════════════════════════

def _safe_filename(name: str) -> str:
    keep = '-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join(c if c in keep else '_' for c in (name or 'detail'))[:60]


class DetailKaderPDFView(AdminRequiredMixin, View):
    def get(self, request, pk):
        bio = get_object_or_404(
            BiodataKader.objects.select_related('id_user'), pk=pk,
        )
        data, ctype, ext = LaporanService.generate_detail_kader_pdf(bio, request.user)
        response = HttpResponse(data, content_type=ctype)
        fname = f'detail_kader_{_safe_filename(bio.nama_lengkap)}.{ext}'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response


class DetailKaderExcelView(AdminRequiredMixin, View):
    def get(self, request, pk):
        bio = get_object_or_404(
            BiodataKader.objects.select_related('id_user'), pk=pk,
        )
        excel = LaporanService.generate_detail_kader_excel(bio, request.user)
        response = HttpResponse(excel, content_type=XLSX_TYPE)
        fname = f'detail_kader_{_safe_filename(bio.nama_lengkap)}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response


class DetailPendaftarPDFView(AdminRequiredMixin, View):
    def get(self, request, pk):
        pendaftaran = get_object_or_404(
            PendaftaranDAD.objects.select_related(
                'id_biodata__id_user', 'id_periode', 'id_kelompok',
            ),
            pk=pk,
        )
        data, ctype, ext = LaporanService.generate_detail_pendaftar_pdf(pendaftaran, request.user)
        response = HttpResponse(data, content_type=ctype)
        bio = pendaftaran.id_biodata
        fname = f'detail_pendaftar_{_safe_filename(bio.nama_lengkap if bio else pendaftaran.no_registrasi)}.{ext}'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response


class DetailPendaftarExcelView(AdminRequiredMixin, View):
    def get(self, request, pk):
        pendaftaran = get_object_or_404(
            PendaftaranDAD.objects.select_related(
                'id_biodata__id_user', 'id_periode', 'id_kelompok',
            ),
            pk=pk,
        )
        excel = LaporanService.generate_detail_pendaftar_excel(pendaftaran, request.user)
        response = HttpResponse(excel, content_type=XLSX_TYPE)
        bio = pendaftaran.id_biodata
        fname = f'detail_pendaftar_{_safe_filename(bio.nama_lengkap if bio else pendaftaran.no_registrasi)}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response


class DetailKelulusanPDFView(AdminRequiredMixin, View):
    def get(self, request, pk):
        rekap = get_object_or_404(
            RekapLeaderboard.objects.select_related(
                'id_pendaftaran__id_biodata__id_user',
                'id_pendaftaran__id_periode',
                'id_pendaftaran__id_kelompok',
            ),
            pk=pk,
        )
        data, ctype, ext = LaporanService.generate_detail_kelulusan_pdf(rekap, request.user)
        response = HttpResponse(data, content_type=ctype)
        bio = rekap.id_pendaftaran.id_biodata
        fname = f'detail_kelulusan_{_safe_filename(bio.nama_lengkap if bio else "peserta")}.{ext}'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response


class DetailKelulusanExcelView(AdminRequiredMixin, View):
    def get(self, request, pk):
        rekap = get_object_or_404(
            RekapLeaderboard.objects.select_related(
                'id_pendaftaran__id_biodata__id_user',
                'id_pendaftaran__id_periode',
                'id_pendaftaran__id_kelompok',
            ),
            pk=pk,
        )
        excel = LaporanService.generate_detail_kelulusan_excel(rekap, request.user)
        response = HttpResponse(excel, content_type=XLSX_TYPE)
        bio = rekap.id_pendaftaran.id_biodata
        fname = f'detail_kelulusan_{_safe_filename(bio.nama_lengkap if bio else "peserta")}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response
