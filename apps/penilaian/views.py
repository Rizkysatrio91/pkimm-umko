"""Views untuk app penilaian — semua menggunakan CBV."""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.pendaftaran.models import KelompokDAD, PendaftaranDAD, PeriodeDAD
from apps.penilaian.forms import (
    NilaiAktivitasForm,
    NilaiInterviewForm,
    PenetapanKelulusanForm,
)
from apps.penilaian.models import NilaiAktivitas, NilaiInterview, RekapLeaderboard
from apps.penilaian.services import AktivitasService, KelulusanService
from core.constants import StatusInterview, StatusVerifikasi, UserRole
from core.mixins import AdminRequiredMixin, PanitiaRequiredMixin, RoleRequiredMixin, TahapRequiredMixin


# ─── Helper: scoping kelompok panitia ───────────────────────────────────────

def get_kelompok_panitia(user):
    """Return KelompokDAD yang di-PJ-kan ke user pada periode aktif, atau None.

    Admin tidak terikat kelompok — selalu return None (artinya: lihat semua).
    """
    if getattr(user, 'role', None) != UserRole.PANITIA:
        return None
    periode = PeriodeDAD.get_active_period()
    if not periode:
        return None
    return KelompokDAD.objects.filter(id_periode=periode, id_pj=user).first()


class KelompokScopeMixin:
    """Batasi akses penilaian panitia hanya ke peserta kelompoknya sendiri.

    - Admin: bypass (lihat/koreksi semua kelompok).
    - Panitia: hanya peserta dengan id_kelompok == kelompok yang di-PJ-kan.
    - Panitia tanpa kelompok PJ: tidak melihat siapa pun + pesan peringatan.
    """

    @property
    def kelompok_pj(self):
        if not hasattr(self, '_kelompok_pj'):
            self._kelompok_pj = get_kelompok_panitia(self.request.user)
        return self._kelompok_pj

    @property
    def is_panitia_scoped(self) -> bool:
        return self.request.user.role == UserRole.PANITIA

    def scope_pendaftaran_qs(self, qs):
        """Filter queryset PendaftaranDAD sesuai kelompok panitia."""
        if not self.is_panitia_scoped:
            return qs
        if self.kelompok_pj is None:
            return qs.none()
        return qs.filter(id_kelompok=self.kelompok_pj)

    def boleh_nilai(self, pendaftaran) -> bool:
        """Cek apakah user boleh menilai peserta ini."""
        if not self.is_panitia_scoped:
            return True
        return (
            self.kelompok_pj is not None
            and pendaftaran.id_kelompok_id == self.kelompok_pj.id_kelompok
        )

    def tolak_akses_kelompok(self, request, redirect_to):
        """Pesan error + redirect saat panitia mengakses peserta kelompok lain."""
        if self.kelompok_pj is None:
            messages.error(
                request,
                'Anda belum ditetapkan sebagai PJ kelompok mana pun. '
                'Hubungi admin untuk penetapan kelompok.',
            )
        else:
            messages.error(
                request,
                f'Peserta ini bukan anggota Kelas {self.kelompok_pj.nama_kelompok}. '
                'Anda hanya dapat menilai peserta kelompok Anda sendiri.',
            )
        return redirect(redirect_to)


# ─── Panitia: Dashboard ─────────────────────────────────────────────────────

class PanitiaDashboardView(PanitiaRequiredMixin, View):
    """Dashboard untuk panitia dengan statistik penilaian."""

    template_name = 'dashboard/panitia.html'

    def get(self, request):
        lolos_count = PendaftaranDAD.objects.filter(
            status_verifikasi=StatusVerifikasi.LOLOS,
        ).count()
        sudah_interview = NilaiInterview.objects.count()
        belum_interview = lolos_count - sudah_interview
        if belum_interview < 0:
            belum_interview = 0

        avg_interview = NilaiInterview.objects.aggregate(
            avg=Avg('rata_rata'),
        )['avg'] or Decimal('0')

        lulus_interview = NilaiInterview.objects.filter(
            status_interview=StatusInterview.LULUS,
        ).count()

        sudah_aktivitas = NilaiAktivitas.objects.values('id_pendaftaran').distinct().count()

        # Info kelompok yang dipegang panitia ini (khusus role panitia)
        kelompok_pj = None
        anggota_kelompok = []
        periode_aktif = PeriodeDAD.get_active_period()
        if periode_aktif and request.user.role == UserRole.PANITIA:
            kelompok_pj = KelompokDAD.objects.filter(
                id_periode=periode_aktif, id_pj=request.user,
            ).first()
            if kelompok_pj:
                anggota_kelompok = PendaftaranDAD.objects.filter(
                    id_kelompok=kelompok_pj,
                ).select_related('id_biodata').order_by('id_biodata__nama_lengkap')

        return render(request, self.template_name, {
            'lolos_count': lolos_count,
            'sudah_interview': sudah_interview,
            'belum_interview': belum_interview,
            'avg_interview': avg_interview,
            'lulus_interview': lulus_interview,
            'sudah_aktivitas': sudah_aktivitas,
            'kelompok_pj': kelompok_pj,
            'anggota_kelompok': anggota_kelompok,
            'periode_aktif': periode_aktif,
        })


# ─── Panitia: Interview ─────────────────────────────────────────────────────

class InterviewListView(PanitiaRequiredMixin, TahapRequiredMixin, KelompokScopeMixin, ListView):
    """Daftar peserta yang berhak mengikuti interview (lolos administrasi, belum ada nilai interview).

    Panitia hanya melihat peserta kelompoknya sendiri; admin melihat semua.
    """

    allowed_tahap = ['interview', 'kegiatan_dad']
    template_name = 'penilaian/interview_list.html'
    context_object_name = 'pendaftaran_list'
    paginate_by = 10

    def get_queryset(self):
        qs = PendaftaranDAD.objects.filter(
            status_verifikasi=StatusVerifikasi.LOLOS,
        ).select_related('id_biodata').annotate(
            has_interview=Count('nilai_interview_set'),
        ).order_by('-tgl_daftar')  # eksplisit: annotate() menghapus ordering default Meta
        return self.scope_pendaftaran_qs(qs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tab'] = self.request.GET.get('tab', 'belum')
        ctx['kelompok_pj'] = self.kelompok_pj
        ctx['panitia_tanpa_kelompok'] = self.is_panitia_scoped and self.kelompok_pj is None
        return ctx


class InterviewCreateView(PanitiaRequiredMixin, TahapRequiredMixin, KelompokScopeMixin, View):
    """Input nilai interview untuk seorang peserta.

    Panitia hanya boleh menilai peserta kelompoknya sendiri; admin bebas.
    """

    allowed_tahap = ['interview', 'kegiatan_dad']
    template_name = 'penilaian/interview_form.html'

    def get_pendaftaran(self, pendaftaran_id):
        return get_object_or_404(
            PendaftaranDAD.objects.select_related('id_biodata'),
            id_pendaftaran=pendaftaran_id,
            status_verifikasi=StatusVerifikasi.LOLOS,
        )

    def get(self, request, pendaftaran_id):
        pendaftaran = self.get_pendaftaran(pendaftaran_id)
        if not self.boleh_nilai(pendaftaran):
            return self.tolak_akses_kelompok(request, 'panitia:interview_list')
        if NilaiInterview.objects.filter(id_pendaftaran=pendaftaran).exists():
            messages.info(request, 'Peserta ini sudah memiliki nilai interview.')
            return redirect('panitia:interview_list')
        form = NilaiInterviewForm()
        return render(request, self.template_name, {
            'form': form,
            'pendaftaran': pendaftaran,
        })

    def post(self, request, pendaftaran_id):
        pendaftaran = self.get_pendaftaran(pendaftaran_id)
        if not self.boleh_nilai(pendaftaran):
            return self.tolak_akses_kelompok(request, 'panitia:interview_list')
        if NilaiInterview.objects.filter(id_pendaftaran=pendaftaran).exists():
            messages.info(request, 'Peserta ini sudah memiliki nilai interview.')
            return redirect('panitia:interview_list')
        form = NilaiInterviewForm(request.POST)
        if form.is_valid():
            interview = form.save(commit=False)
            interview.id_pendaftaran = pendaftaran
            interview.id_panitia = request.user
            interview.save()  # triggers hitung_rata_rata + signal
            messages.success(
                request,
                f'Nilai interview untuk {pendaftaran.id_biodata.nama_lengkap} berhasil disimpan. '
                f'Rata-rata: {interview.rata_rata}, Status: {interview.get_status_interview_display()}'
            )
            return redirect('panitia:interview_list')
        return render(request, self.template_name, {
            'form': form,
            'pendaftaran': pendaftaran,
        })


class InterviewDetailView(PanitiaRequiredMixin, KelompokScopeMixin, DetailView):
    """Tampilkan detail nilai interview (5 kategori × 3 sub-item).

    Panitia hanya bisa melihat detail nilai peserta kelompoknya sendiri.
    """

    model = NilaiInterview
    template_name = 'penilaian/interview_detail.html'
    context_object_name = 'interview'
    pk_url_kwarg = 'pk'

    def get_queryset(self):
        qs = super().get_queryset().select_related('id_pendaftaran__id_biodata')
        if not self.is_panitia_scoped:
            return qs
        if self.kelompok_pj is None:
            return qs.none()
        return qs.filter(id_pendaftaran__id_kelompok=self.kelompok_pj)

    def get_context_data(self, **kwargs):
        from apps.penilaian.forms import INTERVIEW_KATEGORI
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        nilai_kategori_map = {
            "Al-Qur'an": obj.nilai_quran,
            'Hafalan Ayat': obj.nilai_hafalan,
            'Ideologi': obj.nilai_ideologi,
            'Dialektika': obj.nilai_dialektika,
            'Kesiapan': obj.nilai_kesiapan,
        }
        kategori_rows = []
        for kat in INTERVIEW_KATEGORI:
            items = [
                {'label': label, 'nilai': getattr(obj, name)}
                for (name, label) in kat['items']
            ]
            kategori_rows.append({
                'nama': kat['nama'],
                'items': items,
                'rata_rata': nilai_kategori_map[kat['nama']],
            })
        ctx['kategori_rows'] = kategori_rows
        return ctx


# ─── Panitia: Aktivitas DAD Harian ──────────────────────────────────────────

class AktivitasListView(PanitiaRequiredMixin, TahapRequiredMixin, KelompokScopeMixin, ListView):
    """Daftar peserta yang lulus interview beserta status nilai aktivitas harian.

    Panitia hanya melihat peserta kelompoknya sendiri; admin melihat semua.
    """

    allowed_tahap = ['kegiatan_dad']
    template_name = 'penilaian/aktivitas_list.html'
    context_object_name = 'peserta_list'
    paginate_by = 10

    def get_queryset(self):
        qs = PendaftaranDAD.objects.filter(
            nilai_interview_set__status_interview=StatusInterview.LULUS,
        ).select_related('id_biodata').prefetch_related('nilai_aktivitas_set').distinct()
        return self.scope_pendaftaran_qs(qs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Hitung tanggal kalender untuk tiap hari_ke berdasarkan periode aktif.
        # Panitia hanya boleh input nilai pada tanggal hari tersebut atau sesudahnya;
        # admin selalu di-bypass untuk keperluan koreksi data.
        periode = PeriodeDAD.get_active_period()
        today = timezone.localdate()
        is_admin = self.request.user.role == UserRole.ADMIN
        tanggal_per_hari: dict[int, dict] = {}
        if periode and periode.tgl_mulai_kegiatan:
            # PENTING: konversi ke waktu lokal (WIB) dulu — .date() langsung pada
            # datetime aware (UTC) menggeser tanggal mundur 1 hari untuk jam < 07:00.
            mulai_date = timezone.localtime(periode.tgl_mulai_kegiatan).date()
            for i in range(1, 4):
                tgl = mulai_date + timedelta(days=i - 1)
                tanggal_per_hari[i] = {
                    'tanggal': tgl,
                    'tersedia': is_admin or today >= tgl,
                }

        for p in ctx['peserta_list']:
            hari_map = {a.hari_ke: a for a in p.nilai_aktivitas_set.all()}
            p.hari_status = []
            for i in range(1, 4):
                info = tanggal_per_hari.get(i, {})
                p.hari_status.append({
                    'hari': i,
                    'aktivitas': hari_map.get(i),
                    'tanggal': info.get('tanggal'),
                    'tersedia': info.get('tersedia', True),
                })
        ctx['is_admin'] = is_admin
        ctx['kelompok_pj'] = self.kelompok_pj
        ctx['panitia_tanpa_kelompok'] = self.is_panitia_scoped and self.kelompok_pj is None
        return ctx


class AktivitasCreateView(PanitiaRequiredMixin, TahapRequiredMixin, KelompokScopeMixin, View):
    """Input nilai aktivitas harian untuk seorang peserta.

    Panitia hanya boleh menilai peserta kelompoknya sendiri; admin bebas.
    """

    allowed_tahap = ['kegiatan_dad']
    template_name = 'penilaian/aktivitas_form.html'

    def get_pendaftaran(self, pendaftaran_id):
        return get_object_or_404(
            PendaftaranDAD.objects.select_related('id_biodata'),
            id_pendaftaran=pendaftaran_id,
        )

    def _validasi_tanggal_input(self, request, hari_ke: int):
        """Panitia hanya boleh input nilai pada tanggal hari tsb atau sesudahnya.

        Admin selalu di-bypass agar bisa mengoreksi data.
        Return (is_valid: bool, error_message: str | None).
        """
        if request.user.role == UserRole.ADMIN:
            return True, None
        periode = PeriodeDAD.get_active_period()
        if not periode or not periode.tgl_mulai_kegiatan:
            return True, None
        # PENTING: konversi ke waktu lokal (WIB) dulu — .date() langsung pada
        # datetime aware (UTC) menggeser tanggal mundur 1 hari untuk jam < 07:00.
        mulai_date = timezone.localtime(periode.tgl_mulai_kegiatan).date()
        tgl_hari_ke = mulai_date + timedelta(days=int(hari_ke) - 1)
        if timezone.localdate() < tgl_hari_ke:
            return False, (
                f'Penilaian Hari ke-{hari_ke} baru dapat diinput mulai '
                f'{tgl_hari_ke:%d %B %Y}. Silakan kembali pada tanggal tersebut.'
            )
        return True, None

    def get(self, request, pendaftaran_id, hari_ke):
        pendaftaran = self.get_pendaftaran(pendaftaran_id)
        if not self.boleh_nilai(pendaftaran):
            return self.tolak_akses_kelompok(request, 'panitia:aktivitas_list')
        ok, err = self._validasi_tanggal_input(request, hari_ke)
        if not ok:
            messages.error(request, err)
            return redirect('panitia:aktivitas_list')
        if NilaiAktivitas.objects.filter(id_pendaftaran=pendaftaran, hari_ke=hari_ke).exists():
            messages.info(request, f'Penilaian hari ke-{hari_ke} sudah diisi.')
            return redirect('panitia:aktivitas_list')
        form = NilaiAktivitasForm()
        poin_kedisiplinan_preview = AktivitasService.hitung_poin_kedisiplinan(
            pendaftaran, hari_ke,
        )
        return render(request, self.template_name, {
            'form': form,
            'pendaftaran': pendaftaran,
            'hari_ke': hari_ke,
            'poin_kedisiplinan_preview': poin_kedisiplinan_preview,
        })

    def post(self, request, pendaftaran_id, hari_ke):
        pendaftaran = self.get_pendaftaran(pendaftaran_id)
        if not self.boleh_nilai(pendaftaran):
            return self.tolak_akses_kelompok(request, 'panitia:aktivitas_list')
        ok, err = self._validasi_tanggal_input(request, hari_ke)
        if not ok:
            messages.error(request, err)
            return redirect('panitia:aktivitas_list')
        if NilaiAktivitas.objects.filter(id_pendaftaran=pendaftaran, hari_ke=hari_ke).exists():
            messages.info(request, f'Penilaian hari ke-{hari_ke} sudah diisi.')
            return redirect('panitia:aktivitas_list')
        form = NilaiAktivitasForm(request.POST)
        if form.is_valid():
            aktivitas = form.save(commit=False)
            aktivitas.id_pendaftaran = pendaftaran
            aktivitas.id_panitia = request.user
            aktivitas.hari_ke = hari_ke
            # Poin kedisiplinan di-hitung otomatis dari data AbsensiDAD —
            # tidak boleh di-input manual oleh panitia.
            aktivitas.poin_kedisiplinan = AktivitasService.hitung_poin_kedisiplinan(
                pendaftaran, hari_ke,
            )
            aktivitas.save()  # triggers hitung_skor_harian + signal
            messages.success(
                request,
                f'Penilaian hari ke-{hari_ke} untuk {pendaftaran.id_biodata.nama_lengkap} '
                f'berhasil disimpan. Skor: {aktivitas.skor_harian} '
                f'(Kedisiplinan: {aktivitas.poin_kedisiplinan}).'
            )
            return redirect('panitia:aktivitas_list')
        poin_kedisiplinan_preview = AktivitasService.hitung_poin_kedisiplinan(
            pendaftaran, hari_ke,
        )
        return render(request, self.template_name, {
            'form': form,
            'pendaftaran': pendaftaran,
            'hari_ke': hari_ke,
            'poin_kedisiplinan_preview': poin_kedisiplinan_preview,
        })


# ─── Leaderboard ────────────────────────────────────────────────────────────

class LeaderboardView(RoleRequiredMixin, ListView):
    """Leaderboard yang dapat dilihat oleh admin, panitia, dan calon kader saja."""

    allowed_roles = [UserRole.ADMIN, UserRole.PANITIA, UserRole.CALON_KADER]

    model = RekapLeaderboard
    template_name = 'penilaian/leaderboard.html'
    context_object_name = 'leaderboard'

    def get_queryset(self):
        return RekapLeaderboard.objects.select_related(
            'id_pendaftaran__id_biodata',
        ).order_by('peringkat')


# ─── Admin: Penetapan Kelulusan ─────────────────────────────────────────────

class PenetapanKelulusanView(AdminRequiredMixin, View):
    """Admin: tetapkan passing grade dan tentukan status kelulusan."""

    template_name = 'penilaian/penetapan_kelulusan.html'

    def get(self, request):
        form = PenetapanKelulusanForm()
        leaderboard = RekapLeaderboard.objects.select_related(
            'id_pendaftaran__id_biodata',
        ).order_by('peringkat')
        return render(request, self.template_name, {
            'form': form,
            'leaderboard': leaderboard,
        })

    def post(self, request):
        form = PenetapanKelulusanForm(request.POST)
        if form.is_valid():
            passing_grade = form.cleaned_data['passing_grade']
            result = KelulusanService.tetapkan_kelulusan(passing_grade)
            messages.success(
                request,
                f'Kelulusan berhasil ditetapkan! '
                f'Lulus: {result["lulus"]} peserta, '
                f'Tidak Lulus: {result["tidak_lulus"]} peserta. '
                f'(Passing Grade: {passing_grade})'
            )
            return redirect('penilaian_admin:penetapan_kelulusan')

        leaderboard = RekapLeaderboard.objects.select_related(
            'id_pendaftaran__id_biodata',
        ).order_by('peringkat')
        return render(request, self.template_name, {
            'form': form,
            'leaderboard': leaderboard,
        })
