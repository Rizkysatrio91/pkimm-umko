"""View untuk app kader — semua menggunakan CBV."""
from datetime import datetime

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.kader.forms import BiodataForm, KaderAdminForm
from apps.kader.models import BiodataKader, KonfigurasiSistem
from apps.kader.services import KaderExcelService
from apps.pendaftaran.models import PendaftaranDAD, PeriodeDAD
from core.exceptions import SSOServiceError
from core.mixins import AdminRequiredMixin, CalonKaderRequiredMixin
from core.services import SSOService


# ─── Admin: CRUD Data Kader ──────────────────────────────────────────────────

class KaderListView(AdminRequiredMixin, ListView):
    """Admin: tampilkan daftar semua kader dengan pencarian dan pagination."""

    model = BiodataKader
    template_name = 'kader/kader_list.html'
    context_object_name = 'kader_list'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().exclude(jabatan_struktural='calon')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nama_lengkap__icontains=q) | Q(npm__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class KaderCreateView(AdminRequiredMixin, CreateView):
    """Admin: buat kader baru."""

    model = BiodataKader
    form_class = KaderAdminForm
    template_name = 'kader/kader_form.html'
    success_url = reverse_lazy('kader_admin:admin_list')

    def form_valid(self, form):
        messages.success(self.request, 'Data kader berhasil ditambahkan.')
        return super().form_valid(form)


class KaderUpdateView(AdminRequiredMixin, UpdateView):
    """Admin: edit data kader."""

    model = BiodataKader
    form_class = KaderAdminForm
    template_name = 'kader/kader_form.html'
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('kader_admin:admin_list')

    def form_valid(self, form):
        messages.success(self.request, 'Data kader berhasil diperbarui.')
        return super().form_valid(form)


class KaderDeleteView(AdminRequiredMixin, DeleteView):
    """Admin: hapus kader."""

    model = BiodataKader
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('kader_admin:admin_list')

    def delete(self, request, *args, **kwargs):
        biodata = self.get_object()
        if biodata.id_user_id:
            # Hapus User dulu; signal pre_delete akan otomatis hapus BiodataKader
            biodata.id_user.delete()
        else:
            # Kader tanpa akun user — hapus langsung
            biodata.delete()
        messages.success(request, 'Data kader berhasil dihapus.')
        return redirect(self.success_url)

    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)


# ─── Admin: Bulk Upload Data Kader via Excel ────────────────────────────────

class KaderExcelTemplateView(AdminRequiredMixin, View):
    """Admin: download template Excel untuk bulk-import data kader."""

    def get(self, request):
        content = KaderExcelService.generate_template()
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="template_data_kader.xlsx"'
        return response


class KaderExcelUploadView(AdminRequiredMixin, View):
    """Admin: upload file Excel untuk bulk-import data kader."""

    template_name = 'kader/kader_upload.html'

    def get(self, request):
        return render(request, self.template_name, {})

    def post(self, request):
        upload = request.FILES.get('file_excel')
        if not upload:
            messages.error(request, 'Silakan pilih file Excel terlebih dahulu.')
            return render(request, self.template_name, {})

        if not upload.name.lower().endswith(('.xlsx', '.xlsm')):
            messages.error(request, 'File harus berformat .xlsx atau .xlsm.')
            return render(request, self.template_name, {})

        result = KaderExcelService.import_from_file(upload)

        if result.created or result.updated:
            messages.success(
                request,
                f'Import selesai: {result.created} baru dibuat, {result.updated} diperbarui.',
            )
        if result.has_error:
            messages.warning(
                request,
                f'{result.total_error} baris gagal diimpor (lihat rincian di bawah).',
            )
        elif not result.created and not result.updated:
            messages.info(request, 'Tidak ada data yang diimpor.')

        return render(request, self.template_name, {'result': result})


# ─── Calon Kader: Biodata & Dashboard ───────────────────────────────────────

class KaderDashboardView(CalonKaderRequiredMixin, View):
    """Dashboard untuk calon kader."""

    template_name = 'kader/dashboard.html'

    def get(self, request):
        biodata = getattr(request.user, 'biodata', None)
        pendaftaran = None
        has_interview = False
        interview_passed = False
        interview = None
        has_aktivitas = False
        aktivitas_count = 0

        if biodata:
            pendaftaran = (
                PendaftaranDAD.objects
                .filter(id_biodata=biodata)
                .select_related('id_kelompok__id_pj__biodata')
                .first()
            )
            if pendaftaran:
                has_interview = pendaftaran.nilai_interview_set.exists()
                if has_interview:
                    interview = pendaftaran.nilai_interview_set.first()
                    interview_passed = interview.status_interview == 'lulus_interview'
                has_aktivitas = pendaftaran.nilai_aktivitas_set.exists()
                aktivitas_count = pendaftaran.nilai_aktivitas_set.count()

        periode = PeriodeDAD.get_active_period()

        kelompok = pendaftaran.id_kelompok if pendaftaran else None
        pj_panitia = kelompok.id_pj if kelompok else None

        return render(request, self.template_name, {
            'biodata': biodata,
            'pendaftaran': pendaftaran,
            'periode_aktif': periode,
            'has_interview': has_interview,
            'interview_passed': interview_passed,
            'interview': interview,
            'has_aktivitas': has_aktivitas,
            'aktivitas_count': aktivitas_count,
            'kelompok': kelompok,
            'pj_panitia': pj_panitia,
        })


class BiodataView(CalonKaderRequiredMixin, View):
    """Calon kader: lihat dan lengkapi biodata."""

    template_name = 'kader/biodata_form.html'

    def _sync_from_sso(self, biodata):
        """Backfill field yang kosong dari SSO UMKO (sekali saat GET)."""
        if not biodata.npm:
            return
        missing = (
            not biodata.program_studi or not biodata.fakultas
            or not biodata.tgl_lahir or not biodata.tempat_lahir
            or not biodata.jenis_kelamin
        )
        if not missing:
            return
        try:
            mhs = SSOService().get_mahasiswa_by_nim(biodata.npm)
        except SSOServiceError:
            return
        if not mhs:
            return
        konfig = KonfigurasiSistem.get_instance()
        changed = False
        if not biodata.program_studi and mhs.get('program_studi'):
            biodata.program_studi = mhs['program_studi'][:50]
            changed = True
        if not biodata.fakultas and konfig.sso_nama_fakultas:
            biodata.fakultas = konfig.sso_nama_fakultas[:50]
            changed = True
        if not biodata.tempat_lahir and mhs.get('tempat_lahir'):
            biodata.tempat_lahir = mhs['tempat_lahir'][:50]
            changed = True
        if not biodata.tgl_lahir and (mhs.get('tanggal_lahir') or mhs.get('tgl_lahir')):
            raw = str(mhs.get('tanggal_lahir') or mhs.get('tgl_lahir'))[:10]
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    biodata.tgl_lahir = datetime.strptime(raw, fmt).date()
                    changed = True
                    break
                except ValueError:
                    continue
        if not biodata.jenis_kelamin and mhs.get('jenis_kelamin'):
            biodata.jenis_kelamin = mhs['jenis_kelamin'][:1]
            changed = True
        if not biodata.no_hp and mhs.get('hp'):
            biodata.no_hp = mhs['hp'][:15]
            changed = True
        if not biodata.alamat_domisili and (mhs.get('alamat_domisili') or mhs.get('alamat')):
            biodata.alamat_domisili = mhs.get('alamat_domisili') or mhs.get('alamat', '')
            changed = True
        if changed:
            biodata.save()

    def get(self, request):
        biodata = getattr(request.user, 'biodata', None)
        if not biodata:
            messages.error(request, 'Data biodata tidak ditemukan. Hubungi admin.')
            return redirect('kader:dashboard')
        self._sync_from_sso(biodata)
        form = BiodataForm(instance=biodata)
        return render(request, self.template_name, {'form': form, 'biodata': biodata})

    def post(self, request):
        biodata = getattr(request.user, 'biodata', None)
        if not biodata:
            messages.error(request, 'Data biodata tidak ditemukan.')
            return redirect('kader:dashboard')
        form = BiodataForm(request.POST, request.FILES, instance=biodata)
        if form.is_valid():
            form.save()
            biodata.check_completeness()
            if biodata.is_biodata_complete:
                messages.success(request, 'Biodata berhasil dilengkapi!')
            else:
                messages.warning(request, 'Biodata tersimpan, namun masih ada data yang belum lengkap.')
            return redirect('kader:dashboard')
        return render(request, self.template_name, {'form': form, 'biodata': biodata})


# ─── Admin: Konfigurasi Fakultas Pendaftaran ─────────────────────────────────

class KonfigurasiFakultasView(AdminRequiredMixin, View):
    """Admin: atur fakultas & prodi yang diizinkan mendaftar (singleton)."""

    template_name = 'kader/konfigurasi_fakultas.html'

    def _context(self, konfig):
        """Muat daftar fakultas & prodi dari SSO API."""
        faculties, departments, api_error = [], [], None
        try:
            sso = SSOService()
            faculties = sso.get_faculties()
            departments = sso.get_departments()
        except SSOServiceError as e:
            api_error = str(e)
        return {
            'konfig': konfig,
            'faculties': faculties,
            'departments': departments,
            'api_error': api_error,
            'allowed_codes_set': set(str(x) for x in (konfig.allowed_prodi_codes or [])),
        }

    def get(self, request):
        konfig = KonfigurasiSistem.get_instance()
        return render(request, self.template_name, self._context(konfig))

    def post(self, request):
        konfig = KonfigurasiSistem.get_instance()
        fakultas_id = request.POST.get('sso_id_fakultas', '').strip()
        prodi_codes = request.POST.getlist('allowed_prodi_codes')

        if not fakultas_id:
            messages.error(request, 'Silakan pilih fakultas.')
            return render(request, self.template_name, self._context(konfig))
        if not prodi_codes:
            messages.error(request, 'Silakan centang minimal satu program studi.')
            return render(request, self.template_name, self._context(konfig))

        # Ambil detail fakultas terpilih agar cache nama/kode akurat
        try:
            sso = SSOService()
            faculties = sso.get_faculties()
        except SSOServiceError as e:
            messages.error(request, f'Gagal mengambil data SSO: {e}')
            return render(request, self.template_name, self._context(konfig))

        fakultas = next((f for f in faculties if str(f.get('id')) == fakultas_id), None)
        if not fakultas:
            messages.error(request, 'Fakultas tidak ditemukan di SSO.')
            return render(request, self.template_name, self._context(konfig))

        konfig.sso_id_fakultas = int(fakultas_id)
        konfig.sso_kode_fakultas = fakultas.get('kode_unit', '')
        konfig.sso_nama_fakultas = fakultas.get('nama_unit', '')
        konfig.allowed_prodi_codes = [str(x) for x in prodi_codes]
        konfig.save()

        messages.success(
            request,
            f'Konfigurasi disimpan. Fakultas "{konfig.sso_nama_fakultas}" '
            f'dengan {len(prodi_codes)} program studi diizinkan mendaftar.'
        )
        return redirect('kader_admin:konfigurasi_fakultas')
