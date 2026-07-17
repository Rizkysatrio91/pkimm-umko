"""Views untuk app laporan — filter Periode DAD + Fakultas/Prodi (sumber SSO UMKO)."""
import re

from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import TemplateView

from apps.kader.models import BiodataKader
from apps.laporan.services import LaporanService
from apps.pendaftaran.models import PendaftaranDAD, PeriodeDAD
from apps.penilaian.models import RekapLeaderboard
from core.exceptions import SSOServiceError
from core.mixins import AdminRequiredMixin
from core.services import SSOService

XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

# Daftar fakultas & prodi diambil dari SSO API UMKO dan di-cache agar halaman
# laporan tidak memanggil SSO tiap kali dibuka.
FILTER_OPTIONS_CACHE_KEY = 'laporan_filter_options_v2'
FILTER_OPTIONS_TTL = 60 * 60 * 12  # 12 jam

# Kata diabaikan saat mencocokkan nama prodi/fakultas lintas sumber (SSO ↔ lokal).
_MATCH_STOP = {
    'dan', 'atau', 'the', 'of', 'ilmu', 's1', 's2', 's3', 'd3', 'd4',
    'fakultas', 'fak', 'prodi', 'program', 'studi', 'jurusan',
}


def _match_tokens(s: str) -> set:
    bersih = re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower())
    return {w for w in bersih.split() if w not in _MATCH_STOP and len(w) > 1}


def _match_score(a: str, b: str) -> float:
    ta, tb = _match_tokens(a), _match_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _best_name(value: str, candidates, threshold: float = 0.5):
    best, score = None, 0.0
    for c in candidates:
        s = _match_score(value, c)
        if s > score:
            score, best = s, c
    return best if score >= threshold else None


def _prodi_fakultas_map(sso_fak_names, sso_prodi_names) -> dict:
    """Petakan tiap nama prodi SSO → nama fakultas SSO.

    SSO API TIDAK menyediakan relasi prodi→fakultas, jadi relasi diambil dari
    tabel master lokal ProgramStudi.fakultas (satu-satunya sumber relasi yang ada
    di sistem, dikurasi manual). Nama lokal dicocokkan ke nama SSO via irisan kata.
    Prodi tanpa padanan lokal → '' (tidak diklaim masuk fakultas mana pun).
    """
    from apps.kader.models import ProgramStudi
    locals_ = list(ProgramStudi.objects.select_related('fakultas'))
    result = {}
    for sp in sso_prodi_names:
        best_local, best_score = None, 0.0
        for lp in locals_:
            s = _match_score(sp, lp.nama_prodi)
            if s > best_score:
                best_score, best_local = s, lp
        fak = ''
        if best_local and best_score >= 0.5:
            fak = _best_name(best_local.fakultas.nama_fakultas, sso_fak_names) or ''
        result[sp] = fak
    return result


def _get_filter_options() -> dict:
    """Daftar fakultas & prodi untuk filter laporan, dari SSO API UMKO (cached 12 jam).

    Bila SSO gagal → fallback ke nilai distinct yang tersimpan di BiodataKader
    (sudah dinormalisasi ke nama SSO) agar filter tetap berfungsi. Hasil fallback
    TIDAK di-cache supaya percobaan berikutnya kembali mencoba SSO.

    Return: {'fakultas': [str, ...], 'prodi': [{'value': str, 'label': str}, ...]}
    """
    cached = cache.get(FILTER_OPTIONS_CACHE_KEY)
    if cached is not None:
        return cached
    try:
        sso = SSOService()
        faculties = sso.get_faculties()
        departments = sso.get_departments()
        fakultas = sorted({f['nama_unit'] for f in faculties if f.get('nama_unit')})
        # Dedup prodi per nama_unit (SSO punya 2 entri "Hukum" dengan kode berbeda).
        prodi_map = {}
        for d in departments:
            nama = (d.get('nama_unit') or '').strip()
            if not nama or nama in prodi_map:
                continue
            jenjang = (d.get('jenjang') or '').strip()
            prodi_map[nama] = f'{nama} ({jenjang})' if jenjang else nama
        prodi_names = sorted(prodi_map.keys())
        fak_of = _prodi_fakultas_map(fakultas, prodi_names)
        prodi = [
            {'value': k, 'label': prodi_map[k], 'fakultas': fak_of.get(k, '')}
            for k in prodi_names
        ]
        result = {'fakultas': fakultas, 'prodi': prodi}
        cache.set(FILTER_OPTIONS_CACHE_KEY, result, FILTER_OPTIONS_TTL)
        return result
    except SSOServiceError:
        fakultas = list(
            BiodataKader.objects.exclude(fakultas='')
            .order_by('fakultas').values_list('fakultas', flat=True).distinct()
        )
        prodi_names = list(
            BiodataKader.objects.exclude(program_studi='')
            .order_by('program_studi').values_list('program_studi', flat=True).distinct()
        )
        fak_of = _prodi_fakultas_map(fakultas, prodi_names)
        prodi = [
            {'value': p, 'label': p, 'fakultas': fak_of.get(p, '')}
            for p in prodi_names
        ]
        return {'fakultas': fakultas, 'prodi': prodi}


def _resolve_periode(periode_value: str) -> tuple:
    """
    Resolve nilai dropdown (id_periode) ke objek PeriodeDAD + label.
    Kosong/invalid → (None, 'Semua Periode').
    """
    if not periode_value:
        return None, 'Semua Periode'
    try:
        periode = PeriodeDAD.objects.filter(pk=int(periode_value)).first()
    except (ValueError, TypeError):
        periode = None
    if periode is None:
        return None, 'Semua Periode'
    return periode, periode.nama_periode


def _resolve_fakultas(fakultas_value: str):
    """Validasi nilai dropdown fakultas terhadap daftar SSO (cached).
    Kosong/invalid → None (tanpa filter fakultas)."""
    fakultas = (fakultas_value or '').strip()
    if not fakultas:
        return None
    valid = set(_get_filter_options()['fakultas'])
    return fakultas if fakultas in valid else None


def _resolve_prodi(prodi_value: str):
    """Validasi nilai dropdown prodi terhadap daftar SSO (cached).
    Kosong/invalid → None (tanpa filter prodi)."""
    prodi = (prodi_value or '').strip()
    if not prodi:
        return None
    valid = {p['value'] for p in _get_filter_options()['prodi']}
    return prodi if prodi in valid else None


def _combined_label(periode_label: str, fakultas, prodi) -> str:
    """Gabungkan label periode + fakultas + prodi untuk ditampilkan di dokumen/Excel."""
    parts = [periode_label]
    if fakultas:
        parts.append(f'Fakultas: {fakultas}')
    if prodi:
        parts.append(f'Prodi: {prodi}')
    return ' — '.join(parts)


class LaporanView(AdminRequiredMixin, TemplateView):
    """Halaman pilih jenis laporan + filter periode."""

    template_name = 'laporan/laporan.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Dropdown periode diisi dari Periode DAD yang benar-benar terdaftar
        # (urutan terbaru dulu mengikuti Meta.ordering = ['-created_at']).
        ctx['periode_choices'] = [
            {
                'value': p.id_periode,
                'label': f'{p.nama_periode} — Aktif' if p.is_active else p.nama_periode,
            }
            for p in PeriodeDAD.objects.all()
        ]

        # Dropdown fakultas & prodi diambil dari SSO API UMKO (cached) agar
        # konsisten dengan Pengaturan Fakultas dan mencakup seluruh unit resmi,
        # bukan hanya yang kebetulan ada datanya.
        filter_options = _get_filter_options()
        ctx['fakultas_choices'] = filter_options['fakultas']
        ctx['prodi_choices'] = filter_options['prodi']

        # Opsi per-kader/pendaftar/peserta untuk unduhan detail.
        # Dinormalisasi ke bentuk seragam {id, label, search} supaya filter
        # pencarian (nama/NPM/registrasi) di sisi klien sederhana & andal.
        ctx['kader_choices'] = [
            {
                'id': k['id_biodata'],
                'label': f"{k['nama_lengkap']} — {k['npm'] or '-'}",
                'search': f"{k['nama_lengkap'] or ''} {k['npm'] or ''}".lower(),
            }
            for k in BiodataKader.objects
            .exclude(jabatan_struktural='calon')
            .order_by('nama_lengkap')
            .values('id_biodata', 'nama_lengkap', 'npm')
        ]
        ctx['pendaftar_choices'] = [
            {
                'id': p['id_pendaftaran'],
                'label': f"{p['id_biodata__nama_lengkap']} — {p['no_registrasi']}",
                'search': (
                    f"{p['id_biodata__nama_lengkap'] or ''} "
                    f"{p['id_biodata__npm'] or ''} "
                    f"{p['no_registrasi'] or ''}"
                ).lower(),
            }
            for p in PendaftaranDAD.objects
            .select_related('id_biodata')
            .order_by('id_biodata__nama_lengkap')
            .values(
                'id_pendaftaran', 'no_registrasi',
                'id_biodata__nama_lengkap', 'id_biodata__npm',
            )
        ]
        ctx['kelulusan_choices'] = [
            {
                'id': r['id_rekap'],
                'label': (
                    f"#{r['peringkat'] if r['peringkat'] is not None else '-'} "
                    f"{r['id_pendaftaran__id_biodata__nama_lengkap']} — "
                    f"{r['id_pendaftaran__id_biodata__npm'] or '-'}"
                ),
                'search': (
                    f"{r['id_pendaftaran__id_biodata__nama_lengkap'] or ''} "
                    f"{r['id_pendaftaran__id_biodata__npm'] or ''} "
                    f"{r['id_pendaftaran__no_registrasi'] or ''}"
                ).lower(),
            }
            for r in RekapLeaderboard.objects
            .select_related('id_pendaftaran__id_biodata')
            .order_by('peringkat')
            .values(
                'id_rekap', 'peringkat',
                'id_pendaftaran__no_registrasi',
                'id_pendaftaran__id_biodata__nama_lengkap',
                'id_pendaftaran__id_biodata__npm',
            )
        ]
        return ctx


# ═════════════════════════════════════════════════════════════════
# Rekap Data Kader
# ═════════════════════════════════════════════════════════════════

class KaderPDFView(AdminRequiredMixin, View):
    def get(self, request):
        periode, periode_label = _resolve_periode(request.GET.get('periode', ''))
        fakultas = _resolve_fakultas(request.GET.get('fakultas', ''))
        prodi = _resolve_prodi(request.GET.get('prodi', ''))
        label = _combined_label(periode_label, fakultas, prodi)
        qs = BiodataKader.objects.exclude(jabatan_struktural='calon')
        if periode:
            qs = qs.filter(pendaftaran__id_periode=periode)
        if fakultas:
            qs = qs.filter(fakultas=fakultas)
        if prodi:
            qs = qs.filter(program_studi=prodi)

        data, ctype, ext = LaporanService.generate_rekap_kader_pdf(qs, label, request.user)
        response = HttpResponse(data, content_type=ctype)
        response['Content-Disposition'] = f'attachment; filename="laporan_kader.{ext}"'
        return response


class KaderExcelView(AdminRequiredMixin, View):
    def get(self, request):
        periode, periode_label = _resolve_periode(request.GET.get('periode', ''))
        fakultas = _resolve_fakultas(request.GET.get('fakultas', ''))
        prodi = _resolve_prodi(request.GET.get('prodi', ''))
        label = _combined_label(periode_label, fakultas, prodi)
        qs = BiodataKader.objects.exclude(jabatan_struktural='calon')
        if periode:
            qs = qs.filter(pendaftaran__id_periode=periode)
        if fakultas:
            qs = qs.filter(fakultas=fakultas)
        if prodi:
            qs = qs.filter(program_studi=prodi)

        excel = LaporanService.generate_rekap_kader_excel(qs, label, request.user)
        response = HttpResponse(excel, content_type=XLSX_TYPE)
        response['Content-Disposition'] = 'attachment; filename="laporan_kader.xlsx"'
        return response


# ═════════════════════════════════════════════════════════════════
# Rekap Pendaftar DAD
# ═════════════════════════════════════════════════════════════════

class PendaftarPDFView(AdminRequiredMixin, View):
    def get(self, request):
        periode, periode_label = _resolve_periode(request.GET.get('periode', ''))
        fakultas = _resolve_fakultas(request.GET.get('fakultas', ''))
        prodi = _resolve_prodi(request.GET.get('prodi', ''))
        label = _combined_label(periode_label, fakultas, prodi)
        qs = PendaftaranDAD.objects.select_related('id_biodata').all()
        if periode:
            qs = qs.filter(id_periode=periode)
        if fakultas:
            qs = qs.filter(id_biodata__fakultas=fakultas)
        if prodi:
            qs = qs.filter(id_biodata__program_studi=prodi)

        data, ctype, ext = LaporanService.generate_rekap_pendaftar_pdf(qs, label, request.user)
        response = HttpResponse(data, content_type=ctype)
        response['Content-Disposition'] = f'attachment; filename="laporan_pendaftar.{ext}"'
        return response


class PendaftarExcelView(AdminRequiredMixin, View):
    def get(self, request):
        periode, periode_label = _resolve_periode(request.GET.get('periode', ''))
        fakultas = _resolve_fakultas(request.GET.get('fakultas', ''))
        prodi = _resolve_prodi(request.GET.get('prodi', ''))
        label = _combined_label(periode_label, fakultas, prodi)
        qs = PendaftaranDAD.objects.select_related('id_biodata').all()
        if periode:
            qs = qs.filter(id_periode=periode)
        if fakultas:
            qs = qs.filter(id_biodata__fakultas=fakultas)
        if prodi:
            qs = qs.filter(id_biodata__program_studi=prodi)

        excel = LaporanService.generate_rekap_pendaftar_excel(qs, label, request.user)
        response = HttpResponse(excel, content_type=XLSX_TYPE)
        response['Content-Disposition'] = 'attachment; filename="laporan_pendaftar.xlsx"'
        return response


# ═════════════════════════════════════════════════════════════════
# Rekap Kelulusan DAD
# ═════════════════════════════════════════════════════════════════

class KelulusanPDFView(AdminRequiredMixin, View):
    def get(self, request):
        periode, periode_label = _resolve_periode(request.GET.get('periode', ''))
        fakultas = _resolve_fakultas(request.GET.get('fakultas', ''))
        prodi = _resolve_prodi(request.GET.get('prodi', ''))
        label = _combined_label(periode_label, fakultas, prodi)
        qs = RekapLeaderboard.objects.select_related(
            'id_pendaftaran__id_biodata'
        ).filter(id_pendaftaran__status_kelulusan='lulus').order_by('peringkat')
        if periode:
            qs = qs.filter(id_pendaftaran__id_periode=periode)
        if fakultas:
            qs = qs.filter(id_pendaftaran__id_biodata__fakultas=fakultas)
        if prodi:
            qs = qs.filter(id_pendaftaran__id_biodata__program_studi=prodi)

        data, ctype, ext = LaporanService.generate_rekap_kelulusan_pdf(qs, label, request.user)
        response = HttpResponse(data, content_type=ctype)
        response['Content-Disposition'] = f'attachment; filename="laporan_kelulusan.{ext}"'
        return response


class KelulusanExcelView(AdminRequiredMixin, View):
    def get(self, request):
        periode, periode_label = _resolve_periode(request.GET.get('periode', ''))
        fakultas = _resolve_fakultas(request.GET.get('fakultas', ''))
        prodi = _resolve_prodi(request.GET.get('prodi', ''))
        label = _combined_label(periode_label, fakultas, prodi)
        qs = RekapLeaderboard.objects.select_related(
            'id_pendaftaran__id_biodata'
        ).filter(id_pendaftaran__status_kelulusan='lulus').order_by('peringkat')
        if periode:
            qs = qs.filter(id_pendaftaran__id_periode=periode)
        if fakultas:
            qs = qs.filter(id_pendaftaran__id_biodata__fakultas=fakultas)
        if prodi:
            qs = qs.filter(id_pendaftaran__id_biodata__program_studi=prodi)

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
