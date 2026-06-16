"""View untuk app pendaftaran — semua menggunakan CBV."""
import json

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from django.db.models import Avg

from apps.accounts.models import User
from apps.kader.models import BiodataKader
from apps.pendaftaran.forms import (
    KelompokPindahForm,
    KelompokPJForm,
    PendaftaranForm,
    PeriodeDADForm,
    RundownDADForm,
)
from apps.pendaftaran.models import (
    AbsensiDAD,
    KelompokDAD,
    PendaftaranDAD,
    PeriodeDAD,
    QRAbsensi,
    RundownDAD,
)
from apps.pendaftaran.services import AbsensiService, KelompokService
from apps.penilaian.models import NilaiAktivitas, NilaiInterview
from core.budget_limiter import BudgetLimiter
from core.constants import StatusAbsensi, StatusKelulusan, StatusInterview, StatusVerifikasi, TipeNotifikasi, UserRole
from core.exceptions import SSOServiceError
from core.mixins import (
    AdminRequiredMixin,
    CalonKaderRequiredMixin,
    PanitiaRequiredMixin,
    TahapRequiredMixin,
)
from core.services import OpenAIBillingService, SSOService


# ─── Calon Kader Views ──────────────────────────────────────────────────────

class PendaftaranCreateView(CalonKaderRequiredMixin, View):
    """Calon kader: daftar DAD dengan verifikasi data via API SSO UMKO."""

    template_name = 'pendaftaran/daftar.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        # Guard: biodata harus sudah lengkap
        biodata = getattr(request.user, 'biodata', None)
        if not biodata or not biodata.is_biodata_complete:
            messages.warning(request, 'Lengkapi biodata terlebih dahulu sebelum mendaftar DAD.')
            return redirect('kader:biodata')
        # Guard: hanya boleh mendaftar satu kali
        if PendaftaranDAD.objects.filter(id_biodata=biodata).exists():
            messages.info(request, 'Anda sudah terdaftar. Lihat status pendaftaran Anda.')
            return redirect('pendaftaran:status')
        # Guard: periode aktif harus berada di tahap administrasi
        periode = PeriodeDAD.get_active_period()
        if not periode or not periode.is_open:
            tahap_info = periode.info_tahap['label'] if periode else 'Tidak ada periode aktif'
            messages.warning(
                request,
                f'Pendaftaran DAD belum dibuka atau sudah ditutup. Tahap saat ini: {tahap_info}.',
            )
            return redirect('kader:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = PendaftaranForm()
        biodata = request.user.biodata
        return render(request, self.template_name, {
            'form': form,
            'biodata': biodata,
            'periode_aktif': PeriodeDAD.get_active_period(),
        })

    def post(self, request):
        form = PendaftaranForm(request.POST)
        if form.is_valid():
            biodata = request.user.biodata
            pendaftaran = PendaftaranDAD(
                id_biodata=biodata,
                id_periode=PeriodeDAD.get_active_period(),
            )
            pendaftaran.save()  # triggers auto no_registrasi

            # Validasi via API SSO
            try:
                sso = SSOService()
                hasil = sso.validasi_mahasiswa(
                    nim=biodata.npm,
                    nama_lengkap=biodata.nama_lengkap
                )

                if hasil['is_found']:
                    mhs = hasil['mahasiswa_sso']
                    pendaftaran.api_nama_sso = mhs.get('nama', '')
                    pendaftaran.api_status_mahasiswa = mhs.get('status_mahasiswa', '')
                    pendaftaran.api_program_studi = mhs.get('program_studi', '')

                pendaftaran.validasi_identitas()
                pendaftaran.tgl_verifikasi = timezone.now()
                pendaftaran.save()

                # Buat notifikasi
                from apps.notifikasi.models import Notifikasi
                if pendaftaran.is_identic:
                    judul = 'Pendaftaran DAD: Lolos Administrasi'
                    pesan = (
                        f'Selamat! Pendaftaran Anda ({pendaftaran.no_registrasi}) lolos verifikasi administrasi. '
                        f'Data Anda terverifikasi sebagai mahasiswa UMKO.'
                    )
                else:
                    judul = 'Pendaftaran DAD: Ditolak'
                    pesan = f'Pendaftaran Anda ({pendaftaran.no_registrasi}) ditolak. {hasil["pesan"]}'

                Notifikasi.objects.create(
                    id_user=request.user,
                    judul=judul,
                    pesan=pesan,
                    tipe=TipeNotifikasi.STATUS_VERIFIKASI,
                )

                messages.success(request, hasil['pesan'])

            except SSOServiceError as e:
                pendaftaran.status_verifikasi = StatusVerifikasi.MENUNGGU
                pendaftaran.save()
                messages.warning(
                    request,
                    f'Pendaftaran tersimpan, namun verifikasi gagal: {str(e)} '
                    f'Silakan hubungi admin atau coba lagi nanti.'
                )

            return redirect('pendaftaran:status')

        biodata = request.user.biodata
        return render(request, self.template_name, {
            'form': form,
            'biodata': biodata,
            'periode_aktif': PeriodeDAD.get_active_period(),
        })


class StatusPendaftaranView(CalonKaderRequiredMixin, View):
    """Calon kader: lihat timeline status pendaftaran."""

    template_name = 'pendaftaran/status.html'

    def get(self, request):
        biodata = getattr(request.user, 'biodata', None)
        pendaftaran = None
        if biodata:
            pendaftaran = PendaftaranDAD.objects.filter(id_biodata=biodata).first()

        if not pendaftaran:
            messages.info(request, 'Anda belum mendaftar DAD.')
            return redirect('pendaftaran:daftar')

        # Periksa status interview dan aktivitas
        has_interview = pendaftaran.nilai_interview_set.exists()
        interview_passed = False
        interview = None
        if has_interview:
            interview = pendaftaran.nilai_interview_set.first()
            interview_passed = interview.status_interview == 'lulus_interview'

        has_aktivitas = pendaftaran.nilai_aktivitas_set.exists()
        aktivitas_list = pendaftaran.nilai_aktivitas_set.order_by('hari_ke')

        return render(request, self.template_name, {
            'pendaftaran': pendaftaran,
            'has_interview': has_interview,
            'interview_passed': interview_passed,
            'interview': interview,
            'has_aktivitas': has_aktivitas,
            'aktivitas_list': aktivitas_list,
        })


class RetryVerifikasiView(CalonKaderRequiredMixin, View):
    """Calon kader: ulangi proses verifikasi SSO untuk pendaftaran yang gagal/terhenti."""

    def post(self, request):
        biodata = getattr(request.user, 'biodata', None)
        if not biodata:
            return redirect('pendaftaran:daftar')

        pendaftaran = PendaftaranDAD.objects.filter(id_biodata=biodata).first()
        if not pendaftaran:
            return redirect('pendaftaran:daftar')

        # Hanya izinkan retry untuk status menunggu atau ditolak
        if pendaftaran.status_verifikasi not in (
            StatusVerifikasi.MENUNGGU,
            StatusVerifikasi.DITOLAK,
        ):
            messages.info(request, 'Verifikasi sudah berhasil, tidak perlu diulang.')
            return redirect('pendaftaran:status')

        # Reset dan proses ulang via SSO
        try:
            sso = SSOService()
            hasil = sso.validasi_mahasiswa(
                nim=biodata.npm,
                nama_lengkap=biodata.nama_lengkap
            )

            if hasil['is_found']:
                mhs = hasil['mahasiswa_sso']
                pendaftaran.api_nama_sso = mhs.get('nama', '')
                pendaftaran.api_status_mahasiswa = mhs.get('status_mahasiswa', '')
                pendaftaran.api_program_studi = mhs.get('program_studi', '')
            else:
                pendaftaran.api_nama_sso = None
                pendaftaran.api_status_mahasiswa = None
                pendaftaran.api_program_studi = None

            pendaftaran.validasi_identitas()
            pendaftaran.tgl_verifikasi = timezone.now()
            pendaftaran.save()

            if pendaftaran.is_identic:
                kelompok = KelompokService.assign_one_least_full(pendaftaran)
                extra = f' Anda masuk ke Kelas {kelompok.nama_kelompok}.' if kelompok else ''
                messages.success(
                    request,
                    f'Verifikasi ulang berhasil! Data Anda cocok dengan database UMKO.{extra}',
                )
            else:
                messages.warning(request, f'Verifikasi ulang selesai. {hasil["pesan"]}')

        except SSOServiceError as e:
            pendaftaran.status_verifikasi = StatusVerifikasi.MENUNGGU
            pendaftaran.save()
            messages.error(request, f'Proses verifikasi gagal: {str(e)} Silakan coba lagi nanti.')

        return redirect('pendaftaran:status')


class CekKelulusanView(CalonKaderRequiredMixin, View):
    """Calon kader: cek status kelulusan.

    Hasil kelulusan hanya visible setelah tgl_pengumuman_kelulusan tiba.
    Sebelumnya, tampilkan "Menunggu Keputusan" meski status sudah ditentukan.
    """

    template_name = 'pendaftaran/kelulusan.html'

    def get(self, request):
        from django.utils import timezone

        biodata = getattr(request.user, 'biodata', None)
        pendaftaran = None
        if biodata:
            pendaftaran = PendaftaranDAD.objects.filter(id_biodata=biodata).first()

        # Jika status kelulusan sudah ditentukan (LULUS/TIDAK_LULUS),
        # tetapi pengumuman belum waktunya, tampilkan "Menunggu Keputusan".
        if pendaftaran and pendaftaran.status_kelulusan != StatusKelulusan.BELUM:
            periode = pendaftaran.id_periode
            if periode and periode.tgl_pengumuman_kelulusan:
                if timezone.now() < periode.tgl_pengumuman_kelulusan:
                    # Belum saatnya pengumuman: sembunyikan hasil dengan set status BELUM
                    pendaftaran.status_kelulusan = StatusKelulusan.BELUM

        return render(request, self.template_name, {
            'pendaftaran': pendaftaran,
        })


# ─── Admin Views ─────────────────────────────────────────────────────────────

class AdminDashboardView(AdminRequiredMixin, View):
    """Dashboard admin dengan statistik."""

    template_name = 'dashboard/admin.html'

    def get(self, request):
        # 1. Kader resmi — sudah lulus DAD, jabatan bukan 'calon'
        total_kader = BiodataKader.objects.exclude(jabatan_struktural='calon').count()

        # 2. Calon kader terdaftar — akun User aktif dengan role calon_kader
        total_calon = User.objects.filter(role=UserRole.CALON_KADER).count()

        # 3. Pendaftar DAD aktif — hanya yang belum ditentukan kelulusannya
        total_pendaftar = PendaftaranDAD.objects.filter(
            status_kelulusan=StatusKelulusan.BELUM,
        ).count()

        # 4. Lolos administrasi — terverifikasi SSO dan belum ditentukan kelulusannya
        lolos = PendaftaranDAD.objects.filter(
            status_verifikasi=StatusVerifikasi.LOLOS,
            status_kelulusan=StatusKelulusan.BELUM,
        ).count()

        # 5. Menunggu interview — lolos administrasi, belum ditentukan, belum ada NilaiInterview
        sudah_interview_ids = NilaiInterview.objects.values_list('id_pendaftaran', flat=True)
        menunggu = PendaftaranDAD.objects.filter(
            status_verifikasi=StatusVerifikasi.LOLOS,
            status_kelulusan=StatusKelulusan.BELUM,
        ).exclude(id_pendaftaran__in=sudah_interview_ids).count()

        # 6. Lolos interview — calon yang sudah dinilai LULUS interview dan belum ditentukan kelulusan DAD-nya
        lolos_interview = NilaiInterview.objects.filter(
            status_interview=StatusInterview.LULUS,
            id_pendaftaran__status_kelulusan=StatusKelulusan.BELUM,
        ).count()

        # 7. Lulus DAD sepanjang waktu — untuk informasi historis
        lulus_dad = PendaftaranDAD.objects.filter(
            status_kelulusan=StatusKelulusan.LULUS,
        ).count()

        month_spent = BudgetLimiter.get_month_spent()
        monthly_budget = BudgetLimiter.MONTHLY_BUDGET

        # Data billing OpenAI realtime (jika OPENAI_ADMIN_API_KEY diset di .env)
        openai_configured = OpenAIBillingService.is_configured()
        openai_spend_api = OpenAIBillingService.get_month_spend() if openai_configured else None
        openai_usage = OpenAIBillingService.get_month_usage() if openai_configured else None

        return render(request, self.template_name, {
            'total_kader': total_kader,
            'total_calon': total_calon,
            'total_pendaftar': total_pendaftar,
            'lolos': lolos,
            'menunggu': menunggu,
            'lolos_interview': lolos_interview,
            'lulus_dad': lulus_dad,
            'budget_month_spent': round(month_spent, 4),
            'budget_month_remaining': round(BudgetLimiter.get_remaining_budget(), 4),
            'budget_monthly_limit': monthly_budget,
            'budget_today_spent': round(BudgetLimiter.get_today_spent(), 4),
            'budget_month_percentage': min(100, round(
                (month_spent / monthly_budget) * 100
            )) if monthly_budget > 0 else 0,
            'openai_configured': openai_configured,
            'openai_spend_api': round(openai_spend_api, 4) if openai_spend_api is not None else None,
            'openai_usage': openai_usage,
        })


class AdminPendaftaranListView(AdminRequiredMixin, ListView):
    """Admin: pantau semua pendaftaran DAD."""

    model = PendaftaranDAD
    template_name = 'pendaftaran/admin_list.html'
    context_object_name = 'pendaftaran_list'
    paginate_by = 10

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related('id_biodata')
            .prefetch_related('nilai_interview_set', 'nilai_aktivitas_set')
        )
        q = self.request.GET.get('q', '').strip()
        tahap = self.request.GET.get('tahap', '').strip()

        if q:
            qs = qs.filter(
                Q(id_biodata__nama_lengkap__icontains=q) |
                Q(id_biodata__npm__icontains=q) |
                Q(no_registrasi__icontains=q)
            )

        # Filter berdasarkan tahap — mapping ke kondisi ORM agar pagination tetap benar
        if tahap == 'menunggu_verifikasi':
            qs = qs.filter(status_verifikasi=StatusVerifikasi.MENUNGGU)
        elif tahap == 'ditolak_administrasi':
            qs = qs.filter(status_verifikasi=StatusVerifikasi.DITOLAK)
        elif tahap == 'lolos_administrasi':
            qs = qs.filter(
                status_verifikasi=StatusVerifikasi.LOLOS,
                status_kelulusan=StatusKelulusan.BELUM,
                nilai_interview_set__isnull=True,
                nilai_aktivitas_set__isnull=True,
            )
        elif tahap == 'lolos_interview':
            qs = qs.filter(
                status_kelulusan=StatusKelulusan.BELUM,
                nilai_interview_set__status_interview=StatusInterview.LULUS,
                nilai_aktivitas_set__isnull=True,
            )
        elif tahap == 'gagal_interview':
            qs = qs.filter(
                status_kelulusan=StatusKelulusan.BELUM,
                nilai_interview_set__status_interview=StatusInterview.GAGAL,
            )
        elif tahap == 'aktivitas_dad':
            qs = qs.filter(
                status_kelulusan=StatusKelulusan.BELUM,
                nilai_aktivitas_set__isnull=False,
            )
        elif tahap == 'lulus_dad':
            qs = qs.filter(status_kelulusan=StatusKelulusan.LULUS)
        elif tahap == 'tidak_lulus_dad':
            qs = qs.filter(status_kelulusan=StatusKelulusan.TIDAK_LULUS)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['tahap_filter'] = self.request.GET.get('tahap', '')
        ctx['tahap_choices'] = PendaftaranDAD.TAHAP_CODES
        return ctx


class AdminPendaftaranDetailView(AdminRequiredMixin, DetailView):
    """Admin: tampilan detail pendaftaran dengan hasil verifikasi SSO."""

    model = PendaftaranDAD
    template_name = 'pendaftaran/admin_detail.html'
    context_object_name = 'pendaftaran'
    pk_url_kwarg = 'pk'


class AdminRetryVerifikasiView(AdminRequiredMixin, View):
    """Admin: retry verifikasi SSO untuk pendaftaran yang masih menunggu."""

    def post(self, request, pk):
        pendaftaran = get_object_or_404(PendaftaranDAD, pk=pk)

        if pendaftaran.status_verifikasi != StatusVerifikasi.MENUNGGU:
            messages.info(request, 'Pendaftaran ini sudah diverifikasi.')
            return redirect('pendaftaran_admin:admin_detail', pk=pk)

        biodata = pendaftaran.id_biodata
        try:
            sso = SSOService()
            hasil = sso.validasi_mahasiswa(
                nim=biodata.npm,
                nama_lengkap=biodata.nama_lengkap
            )

            if hasil['is_found']:
                mhs = hasil['mahasiswa_sso']
                pendaftaran.api_nama_sso = mhs.get('nama', '')
                pendaftaran.api_status_mahasiswa = mhs.get('status_mahasiswa', '')
                pendaftaran.api_program_studi = mhs.get('program_studi', '')
            else:
                pendaftaran.api_nama_sso = None
                pendaftaran.api_status_mahasiswa = None
                pendaftaran.api_program_studi = None

            pendaftaran.validasi_identitas()
            pendaftaran.tgl_verifikasi = timezone.now()
            pendaftaran.save()

            # Auto-assign ke kelompok saat peserta LOLOS administrasi
            kelompok_assigned = None
            if pendaftaran.is_identic:
                kelompok_assigned = KelompokService.assign_one_least_full(pendaftaran)

            # Buat notifikasi ke calon kader
            from apps.notifikasi.models import Notifikasi
            user = biodata.id_user
            if user:
                if pendaftaran.is_identic:
                    info_kel = f' Anda masuk ke Kelas {kelompok_assigned.nama_kelompok}.' if kelompok_assigned else ''
                    judul = 'Pendaftaran DAD: Lolos Administrasi'
                    pesan = (
                        f'Selamat! Pendaftaran Anda ({pendaftaran.no_registrasi}) lolos verifikasi administrasi. '
                        f'Data Anda terverifikasi sebagai mahasiswa UMKO.{info_kel}'
                    )
                else:
                    judul = 'Pendaftaran DAD: Ditolak'
                    pesan = f'Pendaftaran Anda ({pendaftaran.no_registrasi}) ditolak. {hasil["pesan"]}'

                Notifikasi.objects.create(
                    id_user=user,
                    judul=judul,
                    pesan=pesan,
                    tipe=TipeNotifikasi.STATUS_VERIFIKASI,
                )

            messages.success(request, f'Retry verifikasi berhasil. Hasil: {hasil["pesan"]}')

        except SSOServiceError as e:
            messages.error(request, f'Retry verifikasi gagal: {str(e)}')

        return redirect('pendaftaran_admin:admin_detail', pk=pk)


# ─── Admin: Manajemen Periode DAD ─────────────────────────────────────────

class PeriodeListView(AdminRequiredMixin, ListView):
    """Admin: tampilkan daftar semua periode pendaftaran DAD."""

    model = PeriodeDAD
    template_name = 'pendaftaran/periode_list.html'
    context_object_name = 'periode_list'


class PeriodeCreateView(AdminRequiredMixin, CreateView):
    """Admin: buat periode pendaftaran DAD baru."""

    model = PeriodeDAD
    form_class = PeriodeDADForm
    template_name = 'pendaftaran/periode_form.html'
    success_url = reverse_lazy('periode_admin:periode_list')

    def form_valid(self, form):
        messages.success(self.request, 'Periode pendaftaran berhasil ditambahkan.')
        return super().form_valid(form)


class PeriodeUpdateView(AdminRequiredMixin, UpdateView):
    """Admin: edit periode pendaftaran DAD."""

    model = PeriodeDAD
    form_class = PeriodeDADForm
    template_name = 'pendaftaran/periode_form.html'
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('periode_admin:periode_list')

    def form_valid(self, form):
        messages.success(self.request, 'Periode pendaftaran berhasil diperbarui.')
        return super().form_valid(form)


class PeriodeDeleteView(AdminRequiredMixin, DeleteView):
    """Admin: hapus periode pendaftaran DAD."""

    model = PeriodeDAD
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('periode_admin:periode_list')

    def post(self, request, *args, **kwargs):
        messages.success(request, 'Periode pendaftaran berhasil dihapus.')
        return super().post(request, *args, **kwargs)


class PeriodeToggleActiveView(AdminRequiredMixin, View):
    """Admin: toggle status aktif suatu periode."""

    def post(self, request, pk):
        periode = get_object_or_404(PeriodeDAD, pk=pk)
        if not periode.is_active:
            # Nonaktifkan semua periode lain terlebih dahulu
            PeriodeDAD.objects.filter(is_active=True).update(is_active=False)
            periode.is_active = True
            periode.save(update_fields=['is_active'])
            messages.success(request, f'Periode "{periode.nama_periode}" diaktifkan.')
        else:
            periode.is_active = False
            periode.save(update_fields=['is_active'])
            messages.success(request, f'Periode "{periode.nama_periode}" dinonaktifkan.')
        return redirect('periode_admin:periode_list')


# ═══════════════════════════════════════════════════════════════════════════════
# Admin: Manajemen Kelompok DAD
# ═══════════════════════════════════════════════════════════════════════════════

class KelompokListView(AdminRequiredMixin, View):
    """Admin: lihat 3 kelompok (A/B/C) beserta anggota dan PJ."""

    template_name = 'pendaftaran/kelompok_list.html'

    def get(self, request):
        periode = PeriodeDAD.get_active_period()
        kelompok_list = []
        total_belum_kelompok = 0

        if periode:
            KelompokService.init_kelompok(periode)
            kelompok_list = KelompokDAD.objects.filter(
                id_periode=periode,
            ).select_related('id_pj').prefetch_related(
                'anggota_set__id_biodata',
            )
            total_belum_kelompok = PendaftaranDAD.objects.filter(
                id_periode=periode,
                status_verifikasi=StatusVerifikasi.LOLOS,
                id_kelompok__isnull=True,
            ).count()

        return render(request, self.template_name, {
            'periode': periode,
            'kelompok_list': kelompok_list,
            'total_belum_kelompok': total_belum_kelompok,
        })


class KelompokAssignOtomatisView(AdminRequiredMixin, View):
    """Admin: distribusi otomatis peserta LOLOS ke kelompok A/B/C."""

    def post(self, request):
        periode = PeriodeDAD.get_active_period()
        if not periode:
            messages.error(request, 'Tidak ada periode aktif.')
            return redirect('kelompok_admin:kelompok_list')

        counts = KelompokService.assign_kelompok_otomatis(periode)
        total = sum(counts.values())
        if total == 0:
            messages.info(request, 'Tidak ada peserta baru yang perlu dibagi.')
        else:
            detail = ', '.join(f"Kelas {k}: {v}" for k, v in counts.items())
            messages.success(request, f'{total} peserta berhasil dibagi. {detail}')
        return redirect('kelompok_admin:kelompok_list')


class KelompokSetPJView(AdminRequiredMixin, View):
    """Admin: set PJ panitia untuk kelompok."""

    template_name = 'pendaftaran/kelompok_set_pj.html'

    def get(self, request, pk):
        kelompok = get_object_or_404(KelompokDAD, pk=pk)
        form = KelompokPJForm(initial={'id_pj': kelompok.id_pj})
        return render(request, self.template_name, {
            'kelompok': kelompok,
            'form': form,
        })

    def post(self, request, pk):
        kelompok = get_object_or_404(KelompokDAD, pk=pk)
        form = KelompokPJForm(request.POST)
        if form.is_valid():
            kelompok.id_pj = form.cleaned_data['id_pj']
            kelompok.save(update_fields=['id_pj'])
            messages.success(request, f'PJ Kelas {kelompok.nama_kelompok} berhasil diubah.')
            return redirect('kelompok_admin:kelompok_list')
        return render(request, self.template_name, {
            'kelompok': kelompok,
            'form': form,
        })


class KelompokPindahAnggotaView(AdminRequiredMixin, View):
    """Admin: pindah peserta ke kelompok lain."""

    template_name = 'pendaftaran/kelompok_pindah.html'

    def get(self, request, pk):
        pendaftaran = get_object_or_404(PendaftaranDAD, pk=pk)
        form = KelompokPindahForm(
            periode=pendaftaran.id_periode,
            exclude_kelompok=pendaftaran.id_kelompok,
        )
        return render(request, self.template_name, {
            'pendaftaran': pendaftaran,
            'form': form,
        })

    def post(self, request, pk):
        pendaftaran = get_object_or_404(PendaftaranDAD, pk=pk)
        form = KelompokPindahForm(
            request.POST,
            periode=pendaftaran.id_periode,
            exclude_kelompok=pendaftaran.id_kelompok,
        )
        if form.is_valid():
            kelompok_baru = form.cleaned_data['id_kelompok']
            KelompokService.pindah_anggota(pendaftaran, kelompok_baru)
            messages.success(
                request,
                f'{pendaftaran.id_biodata.nama_lengkap} dipindah ke Kelas {kelompok_baru.nama_kelompok}.',
            )
            return redirect('kelompok_admin:kelompok_list')
        return render(request, self.template_name, {
            'pendaftaran': pendaftaran,
            'form': form,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# Admin: Manajemen Rundown DAD
# ═══════════════════════════════════════════════════════════════════════════════

class RundownListView(AdminRequiredMixin, View):
    """Admin: lihat semua sesi rundown per hari."""

    template_name = 'pendaftaran/rundown_list.html'

    def get(self, request):
        periode = PeriodeDAD.get_active_period()
        rundown_list = []
        hari_groups = {}

        if periode:
            rundown_list = RundownDAD.objects.filter(id_periode=periode)
            for r in rundown_list:
                hari_groups.setdefault(r.hari_ke, []).append(r)

        # Tanpa sorted(): ikuti urutan queryset (kronologis by tanggal).
        # sorted() alfabetis menempatkan "Kedatangan" setelah "Hari 3".
        return render(request, self.template_name, {
            'periode': periode,
            'hari_groups': hari_groups,
            'total_sesi': len(rundown_list),
        })


class RundownCreateView(AdminRequiredMixin, View):
    """Admin: tambah sesi rundown baru."""

    template_name = 'pendaftaran/rundown_form.html'

    def get(self, request):
        form = RundownDADForm()
        return render(request, self.template_name, {'form': form, 'is_edit': False})

    def post(self, request):
        form = RundownDADForm(request.POST)
        if form.is_valid():
            rundown = form.save(commit=False)
            periode = PeriodeDAD.get_active_period()
            if not periode:
                messages.error(request, 'Tidak ada periode aktif.')
                return redirect('rundown_admin:rundown_list')
            rundown.id_periode = periode
            rundown.save()

            # Auto-generate QR untuk sesi is_absensi (1 QR per kelompok A/B/C)
            qr_msg = ''
            if rundown.is_absensi:
                kelompok_list = KelompokService.init_kelompok(periode)
                for kel in kelompok_list:
                    QRAbsensi.objects.get_or_create(id_rundown=rundown, id_kelompok=kel)
                qr_msg = ' QR absensi otomatis dibuat untuk 3 kelompok.'

            messages.success(request, f'Sesi "{rundown.materi}" berhasil ditambahkan.{qr_msg}')
            return redirect('rundown_admin:rundown_list')
        return render(request, self.template_name, {'form': form, 'is_edit': False})


class RundownUpdateView(AdminRequiredMixin, View):
    """Admin: edit sesi rundown."""

    template_name = 'pendaftaran/rundown_form.html'

    def get(self, request, pk):
        rundown = get_object_or_404(RundownDAD, pk=pk)
        form = RundownDADForm(instance=rundown)
        return render(request, self.template_name, {'form': form, 'is_edit': True, 'rundown': rundown})

    def post(self, request, pk):
        rundown = get_object_or_404(RundownDAD, pk=pk)
        form = RundownDADForm(request.POST, instance=rundown)
        if form.is_valid():
            form.save()

            qr_msg = ''
            if rundown.is_absensi and rundown.id_periode:
                # Pastikan QR ada untuk setiap kelompok (buat jika belum ada)
                kelompok_list = KelompokService.init_kelompok(rundown.id_periode)
                created = 0
                for kel in kelompok_list:
                    _, is_new = QRAbsensi.objects.get_or_create(
                        id_rundown=rundown, id_kelompok=kel,
                    )
                    if is_new:
                        created += 1
                if created:
                    qr_msg = f' {created} QR absensi baru dibuat.'
            elif not rundown.is_absensi:
                # Absensi dimatikan: bersihkan QR sesi ini agar tidak tetap muncul
                # di dashboard panitia. Lindungi QR yang sudah punya data scan
                # (hapus QR akan cascade-delete catatan kehadiran).
                qr_sesi = QRAbsensi.objects.filter(id_rundown=rundown)
                qr_kosong = qr_sesi.filter(absensi_set__isnull=True)
                deleted = qr_kosong.count()
                qr_kosong.delete()
                tersisa = qr_sesi.count()
                if deleted:
                    qr_msg = f' {deleted} QR absensi dihapus.'
                if tersisa:
                    qr_msg += (
                        f' {tersisa} QR tidak dihapus karena sudah memiliki data scan'
                        ' — hapus manual bila perlu.'
                    )

            messages.success(request, f'Sesi "{rundown.materi}" berhasil diperbarui.{qr_msg}')
            return redirect('rundown_admin:rundown_list')
        return render(request, self.template_name, {'form': form, 'is_edit': True, 'rundown': rundown})


class RundownDeleteView(AdminRequiredMixin, View):
    """Admin: hapus sesi rundown."""

    def post(self, request, pk):
        rundown = get_object_or_404(RundownDAD, pk=pk)
        materi = rundown.materi
        rundown.delete()
        messages.success(request, f'Sesi "{materi}" berhasil dihapus.')
        return redirect('rundown_admin:rundown_list')


class GenerateAllQRView(AdminRequiredMixin, View):
    """Admin: batch generate QR token untuk semua sesi is_absensi × kelompok."""

    def post(self, request):
        periode = PeriodeDAD.get_active_period()
        if not periode:
            messages.error(request, 'Tidak ada periode aktif.')
            return redirect('rundown_admin:rundown_list')

        created = AbsensiService.generate_all_qr(periode)
        if created == 0:
            messages.info(request, 'Semua QR sudah ter-generate atau belum ada sesi yang memerlukan absensi.')
        else:
            messages.success(request, f'{created} QR Code berhasil di-generate.')
        return redirect('rundown_admin:rundown_list')


# ═══════════════════════════════════════════════════════════════════════════════
# Panitia: Manajemen Absensi QR
# ═══════════════════════════════════════════════════════════════════════════════

class PanitiaAbsensiListView(PanitiaRequiredMixin, TahapRequiredMixin, View):
    """Panitia: lihat sesi rundown dan kontrol QR untuk kelompok mereka."""

    allowed_tahap = ['kegiatan_dad']
    template_name = 'pendaftaran/absensi_panitia_list.html'

    def get(self, request):
        periode = PeriodeDAD.get_active_period()
        qr_list = []
        kelompok_pj = None

        if periode:
            if request.user.role == UserRole.ADMIN:
                qr_list = QRAbsensi.objects.filter(
                    id_rundown__id_periode=periode,
                    id_rundown__is_absensi=True,
                ).select_related('id_rundown', 'id_kelompok').order_by(
                    'id_rundown__tanggal', 'id_rundown__urutan', 'id_rundown__jam_mulai',
                )
            else:
                kelompok_pj = KelompokDAD.objects.filter(
                    id_periode=periode, id_pj=request.user,
                ).first()
                if kelompok_pj:
                    qr_list = QRAbsensi.objects.filter(
                        id_kelompok=kelompok_pj,
                        id_rundown__is_absensi=True,
                    ).select_related('id_rundown', 'id_kelompok').order_by(
                        'id_rundown__tanggal', 'id_rundown__urutan', 'id_rundown__jam_mulai',
                    )

        # Group by hari_ke, urut kronologis mengikuti queryset (tanggal),
        # bukan sorted() alfabetis yang menempatkan "Kedatangan" terakhir.
        hari_groups = {}
        for qr in qr_list:
            hari = qr.id_rundown.hari_ke
            hari_groups.setdefault(hari, []).append(qr)

        return render(request, self.template_name, {
            'periode': periode,
            'kelompok_pj': kelompok_pj,
            'hari_groups': hari_groups,
        })


class PanitiaQRActivateView(PanitiaRequiredMixin, TahapRequiredMixin, View):
    """Panitia: aktifkan QR code (regenerate token)."""

    allowed_tahap = ['kegiatan_dad']

    def post(self, request, qr_id):
        qr = get_object_or_404(QRAbsensi, pk=qr_id)
        qr.activate()
        messages.success(request, f'QR untuk sesi "{qr.id_rundown.materi}" diaktifkan.')
        return redirect('absensi_panitia:absensi_list')


class PanitiaQRDeactivateView(PanitiaRequiredMixin, TahapRequiredMixin, View):
    """Panitia: nonaktifkan QR code."""

    allowed_tahap = ['kegiatan_dad']

    def post(self, request, qr_id):
        qr = get_object_or_404(QRAbsensi, pk=qr_id)
        qr.deactivate()
        messages.success(request, f'QR untuk sesi "{qr.id_rundown.materi}" dinonaktifkan.')
        return redirect('absensi_panitia:absensi_list')


class PanitiaQRShowView(PanitiaRequiredMixin, TahapRequiredMixin, View):
    """Panitia: tampilkan QR code full-screen untuk proyektor."""

    allowed_tahap = ['kegiatan_dad']
    template_name = 'pendaftaran/absensi_qr_show.html'

    def get(self, request, qr_id):
        qr = get_object_or_404(
            QRAbsensi.objects.select_related('id_rundown', 'id_kelompok'),
            pk=qr_id,
        )
        # Hitung jumlah yang sudah scan
        hadir_count = AbsensiDAD.objects.filter(id_qr=qr).count()
        total_anggota = qr.id_kelompok.jumlah_anggota

        return render(request, self.template_name, {
            'qr': qr,
            'hadir_count': hadir_count,
            'total_anggota': total_anggota,
        })


class PanitiaQRDownloadView(PanitiaRequiredMixin, TahapRequiredMixin, View):
    """Panitia: download QR code sebagai PNG."""

    allowed_tahap = ['kegiatan_dad']

    def get(self, request, qr_id):
        qr = get_object_or_404(QRAbsensi, pk=qr_id)
        base_url = request.build_absolute_uri('/').rstrip('/')
        png_bytes = AbsensiService.generate_qr_image(qr.token, base_url)

        response = HttpResponse(png_bytes, content_type='image/png')
        filename = f"QR_{qr.id_kelompok.nama_kelompok}_{qr.id_rundown.materi[:30]}.png"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response


class PanitiaAbsensiStatusView(PanitiaRequiredMixin, TahapRequiredMixin, View):
    """Panitia: tandai status izin / sakit / alpha untuk satu sesi QR.

    Hanya boleh digunakan selama tahap ``kegiatan_dad`` masih berjalan.
    Semua anggota kelompok ditampilkan; status HADIR hanya bisa diubah via
    scan QR oleh peserta (tidak boleh di-override manual).
    """

    allowed_tahap = ['kegiatan_dad']
    template_name = 'pendaftaran/absensi_status_form.html'

    ALLOWED_MANUAL_STATUS = {
        StatusAbsensi.IZIN.value,
        StatusAbsensi.SAKIT.value,
        StatusAbsensi.ALPHA.value,
    }

    def _build_rows(self, qr):
        """Return list (pendaftaran, absensi_or_None) untuk semua anggota kelompok."""
        anggota = PendaftaranDAD.objects.filter(
            id_kelompok=qr.id_kelompok,
        ).select_related('id_biodata').order_by('id_biodata__nama_lengkap')

        absensi_map = {
            a.id_pendaftaran_id: a
            for a in AbsensiDAD.objects.filter(id_qr=qr)
        }
        rows = [(p, absensi_map.get(p.id_pendaftaran)) for p in anggota]
        return rows

    def _get_qr(self, qr_id, user):
        qr = get_object_or_404(
            QRAbsensi.objects.select_related('id_rundown', 'id_kelompok'),
            pk=qr_id,
        )
        # Panitia non-admin hanya boleh akses QR untuk kelompok yang dia pegang
        if user.role != UserRole.ADMIN:
            if qr.id_kelompok.id_pj_id != user.pk:
                return None
        return qr

    def get(self, request, qr_id):
        qr = self._get_qr(qr_id, request.user)
        if qr is None:
            messages.error(request, 'Anda tidak berhak mengakses sesi ini.')
            return redirect('absensi_panitia:absensi_list')

        if not qr.is_active:
            messages.warning(
                request,
                f'QR "{qr.id_rundown.materi}" sedang nonaktif. '
                'Aktifkan QR terlebih dahulu untuk input izin/sakit.',
            )
            return redirect('absensi_panitia:absensi_list')

        return render(request, self.template_name, {
            'qr': qr,
            'rows': self._build_rows(qr),
            'status_choices': [
                (StatusAbsensi.IZIN.value, StatusAbsensi.IZIN.label),
                (StatusAbsensi.SAKIT.value, StatusAbsensi.SAKIT.label),
                (StatusAbsensi.ALPHA.value, StatusAbsensi.ALPHA.label),
            ],
            'STATUS_HADIR': StatusAbsensi.HADIR.value,
        })

    def post(self, request, qr_id):
        qr = self._get_qr(qr_id, request.user)
        if qr is None:
            messages.error(request, 'Anda tidak berhak mengakses sesi ini.')
            return redirect('absensi_panitia:absensi_list')

        if not qr.is_active:
            messages.warning(
                request,
                f'QR "{qr.id_rundown.materi}" sedang nonaktif. '
                'Aktifkan QR terlebih dahulu untuk input izin/sakit.',
            )
            return redirect('absensi_panitia:absensi_list')

        pendaftaran_id = request.POST.get('pendaftaran_id')
        status = request.POST.get('status', '').strip()
        keterangan = request.POST.get('keterangan', '').strip()

        if status not in self.ALLOWED_MANUAL_STATUS:
            messages.error(request, 'Status tidak valid. Hanya izin/sakit/alpha yang bisa di-set manual.')
            return redirect('absensi_panitia:qr_status', qr_id=qr.id_qr)

        try:
            pendaftaran = PendaftaranDAD.objects.get(
                id_pendaftaran=pendaftaran_id,
                id_kelompok=qr.id_kelompok,
            )
        except PendaftaranDAD.DoesNotExist:
            messages.error(request, 'Peserta tidak ditemukan di kelompok ini.')
            return redirect('absensi_panitia:qr_status', qr_id=qr.id_qr)

        existing = AbsensiDAD.objects.filter(
            id_pendaftaran=pendaftaran, id_qr=qr,
        ).first()
        if existing is not None and existing.status == StatusAbsensi.HADIR:
            messages.warning(
                request,
                f'{pendaftaran.id_biodata.nama_lengkap} sudah tercatat HADIR (scan QR). '
                'Status tidak diubah.',
            )
            return redirect('absensi_panitia:qr_status', qr_id=qr.id_qr)

        if existing is None:
            AbsensiDAD.objects.create(
                id_pendaftaran=pendaftaran,
                id_qr=qr,
                status=status,
                keterangan=keterangan,
                waktu_scan=None,
            )
        else:
            existing.status = status
            existing.keterangan = keterangan
            existing.waktu_scan = None
            existing.save(update_fields=['status', 'keterangan', 'waktu_scan'])

        # Sinkronkan ulang poin kedisiplinan jika NilaiAktivitas hari tsb sudah ada
        from apps.penilaian.services import AktivitasService
        AktivitasService.sinkron_poin_kedisiplinan_untuk_sesi(qr.id_rundown, pendaftaran)

        messages.success(
            request,
            f'Status {pendaftaran.id_biodata.nama_lengkap} di sesi "{qr.id_rundown.materi}" '
            f'diset menjadi {dict(StatusAbsensi.choices).get(status, status)}.',
        )
        return redirect('absensi_panitia:qr_status', qr_id=qr.id_qr)


class PanitiaRekapAbsensiView(PanitiaRequiredMixin, TahapRequiredMixin, View):
    """Panitia: rekap kehadiran per peserta."""

    allowed_tahap = ['kegiatan_dad', 'pengumuman']
    template_name = 'pendaftaran/absensi_rekap.html'

    def get(self, request):
        periode = PeriodeDAD.get_active_period()
        rekap = []
        kelompok_pj = None

        if periode:
            if request.user.role == UserRole.ADMIN:
                rekap = AbsensiService.get_rekap_absensi(periode)
            else:
                kelompok_pj = KelompokDAD.objects.filter(
                    id_periode=periode, id_pj=request.user,
                ).first()
                if kelompok_pj:
                    rekap = AbsensiService.get_rekap_absensi(periode, kelompok_pj)

        return render(request, self.template_name, {
            'periode': periode,
            'kelompok_pj': kelompok_pj,
            'rekap': rekap,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# Calon Kader: Rundown & Absensi
# ═══════════════════════════════════════════════════════════════════════════════

class RundownPublicView(CalonKaderRequiredMixin, TahapRequiredMixin, View):
    """Calon Kader: lihat jadwal DAD sesuai kelompok mereka."""

    allowed_tahap = ['kegiatan_dad', 'pengumuman']
    template_name = 'pendaftaran/rundown_public.html'

    def get(self, request):
        biodata = getattr(request.user, 'biodata', None)
        pendaftaran = None
        hari_groups = {}

        if biodata:
            pendaftaran = PendaftaranDAD.objects.filter(id_biodata=biodata).select_related('id_kelompok').first()

        if pendaftaran and pendaftaran.id_periode:
            rundown_list = RundownDAD.objects.filter(id_periode=pendaftaran.id_periode)
            for r in rundown_list:
                hari_groups.setdefault(r.hari_ke, []).append(r)

        # Tanpa sorted(): ikuti urutan queryset (kronologis by tanggal).
        return render(request, self.template_name, {
            'pendaftaran': pendaftaran,
            'hari_groups': hari_groups,
        })


class AbsensiScanView(CalonKaderRequiredMixin, TahapRequiredMixin, View):
    """Calon Kader: interface scan QR code untuk absensi."""

    allowed_tahap = ['kegiatan_dad']
    template_name = 'pendaftaran/absensi_scan.html'

    def get(self, request):
        biodata = getattr(request.user, 'biodata', None)
        pendaftaran = None
        if biodata:
            pendaftaran = PendaftaranDAD.objects.filter(id_biodata=biodata).select_related('id_kelompok').first()

        return render(request, self.template_name, {
            'pendaftaran': pendaftaran,
        })


@method_decorator(csrf_protect, name='dispatch')
class AbsensiValidateView(CalonKaderRequiredMixin, TahapRequiredMixin, View):
    """Calon Kader: AJAX endpoint validasi scan QR."""

    allowed_tahap = ['kegiatan_dad']

    def post(self, request):
        try:
            body = json.loads(request.body)
            token_str = body.get('token', '')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'success': False, 'message': 'Request tidak valid.', 'materi': None})

        result = AbsensiService.validate_scan(token_str, request.user)
        return JsonResponse(result)


class AbsensiScanDirectView(CalonKaderRequiredMixin, TahapRequiredMixin, View):
    """Calon Kader: auto-validate saat kader buka URL QR langsung dari kamera HP native.

    QR code meng-encode URL '/pendaftaran/absensi/scan/<uuid>/'. Jika kader menggunakan
    aplikasi kamera bawaan (bukan scanner di dashboard), URL ini dibuka di browser.
    View ini otomatis memvalidasi token dan menampilkan hasil.
    """

    allowed_tahap = ['kegiatan_dad']
    template_name = 'pendaftaran/absensi_scan_result.html'

    def get(self, request, token):
        result = AbsensiService.validate_scan(str(token), request.user)
        return render(request, self.template_name, {
            'result': result,
        })


class AbsensiRiwayatView(CalonKaderRequiredMixin, TahapRequiredMixin, View):
    """Calon Kader: riwayat absensi saya."""

    allowed_tahap = ['kegiatan_dad', 'pengumuman']
    template_name = 'pendaftaran/absensi_riwayat.html'

    def get(self, request):
        biodata = getattr(request.user, 'biodata', None)
        pendaftaran = None
        absensi_list = []
        total_sesi = 0

        if biodata:
            pendaftaran = PendaftaranDAD.objects.filter(id_biodata=biodata).select_related('id_kelompok').first()

        if pendaftaran:
            absensi_list = AbsensiDAD.objects.filter(
                id_pendaftaran=pendaftaran,
            ).select_related('id_qr__id_rundown').order_by('id_qr__id_rundown__tanggal', 'id_qr__id_rundown__urutan')

            if pendaftaran.id_periode:
                total_sesi = RundownDAD.objects.filter(
                    id_periode=pendaftaran.id_periode,
                    is_absensi=True,
                ).count()

        return render(request, self.template_name, {
            'pendaftaran': pendaftaran,
            'absensi_list': absensi_list,
            'total_sesi': total_sesi,
            'total_hadir': len(absensi_list),
        })
