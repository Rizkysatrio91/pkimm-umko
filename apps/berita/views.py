"""Views untuk app berita — semua CBV."""
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, ListView

from apps.berita.forms import BeritaForm, KataSambutanForm, SejarahForm, VisiMisiForm
from apps.berita.models import Berita, KataSambutan, Sejarah, VisiMisi
from core.budget_limiter import BudgetLimiter
from core.constants import JabatanKader, StatusBerita
from core.exceptions import OpenAIServiceError
from core.mixins import AdminRequiredMixin, PenulisRequiredMixin
from core.rate_limiter import RateLimiter
from core.services import OpenAIService


# ─── Publik ────────────────────────────────────────────────────────────────

class BerandaView(ListView):
    """Beranda publik dengan 6 artikel published terbaru untuk slider."""

    model = Berita
    template_name = 'berita/beranda.html'
    context_object_name = 'berita_list'

    def get_queryset(self):
        return Berita.objects.filter(
            status=StatusBerita.PUBLISHED,
        ).order_by('-tgl_terbit')[:6]

    def get_context_data(self, **kwargs):
        from apps.pendaftaran.models import PeriodeDAD
        from apps.kader.models import BiodataKader
        ctx = super().get_context_data(**kwargs)
        ctx['periode_aktif'] = PeriodeDAD.get_active_period()
        ctx['total_kader'] = BiodataKader.objects.exclude(jabatan_struktural='calon').count()
        ctx['sambutan'] = KataSambutan.objects.filter(is_active=True).first()
        return ctx


class BeritaListView(ListView):
    """Daftar publik semua artikel yang sudah published."""

    model = Berita
    template_name = 'berita/list.html'
    context_object_name = 'berita_list'
    paginate_by = 9

    def get_queryset(self):
        return Berita.objects.filter(
            status=StatusBerita.PUBLISHED,
        ).order_by('-tgl_terbit')


class BeritaDetailView(DetailView):
    """Detail artikel publik dengan penghitung views."""

    model = Berita
    template_name = 'berita/detail.html'
    context_object_name = 'berita'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return Berita.objects.filter(status=StatusBerita.PUBLISHED)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj.increment_views()
        return obj


# ─── Penulis: Dashboard ───────────────────────────────────────────────────

class PenulisDashboardView(PenulisRequiredMixin, View):
    """Dashboard untuk penulis dengan statistik artikel."""

    template_name = 'dashboard/penulis.html'

    def get(self, request):
        berita_saya = Berita.objects.filter(id_penulis=request.user)
        total_berita = berita_saya.count()
        total_views = sum(b.jumlah_views for b in berita_saya)
        draft_count = berita_saya.filter(status=StatusBerita.DRAFT).count()
        published_count = berita_saya.filter(status=StatusBerita.PUBLISHED).count()

        return render(request, self.template_name, {
            'berita_list': berita_saya[:10],
            'total_berita': total_berita,
            'total_views': total_views,
            'draft_count': draft_count,
            'published_count': published_count,
        })


# ─── Penulis: CRUD Berita ─────────────────────────────────────────────────

class BeritaCreateView(PenulisRequiredMixin, View):
    """Buat artikel baru dengan opsi koreksi AI."""

    template_name = 'berita/form.html'

    def get(self, request):
        form = BeritaForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = BeritaForm(request.POST, request.FILES)
        if form.is_valid():
            berita = form.save(commit=False)
            berita.id_penulis = request.user
            # Gunakan konten_final dari hidden field jika sudah dikoreksi AI, jika tidak gunakan draft
            konten_final = request.POST.get('konten_final_hidden', '')
            saran_ai = request.POST.get('saran_ai_hidden', '')
            if konten_final:
                berita.konten_final = konten_final
                berita.saran_ai = saran_ai
            else:
                berita.konten_final = berita.konten_draft
            berita.publish()
            messages.success(request, 'Berita berhasil dipublikasikan.')
            return redirect('penulis:penulis_dashboard')
        return render(request, self.template_name, {'form': form})


class BeritaUpdateView(PenulisRequiredMixin, View):
    """Edit artikel yang sudah ada."""

    template_name = 'berita/form.html'

    def get_berita(self, pk, user):
        return get_object_or_404(Berita, id_berita=pk, id_penulis=user)

    def get(self, request, pk):
        berita = self.get_berita(pk, request.user)
        form = BeritaForm(instance=berita)
        return render(request, self.template_name, {
            'form': form,
            'berita': berita,
            'is_edit': True,
        })

    def post(self, request, pk):
        berita = self.get_berita(pk, request.user)
        form = BeritaForm(request.POST, request.FILES, instance=berita)
        if form.is_valid():
            berita = form.save(commit=False)
            konten_final = request.POST.get('konten_final_hidden', '')
            saran_ai = request.POST.get('saran_ai_hidden', '')
            if konten_final:
                berita.konten_final = konten_final
                berita.saran_ai = saran_ai
            else:
                berita.konten_final = berita.konten_draft
            berita.publish()
            messages.success(request, 'Berita berhasil diperbarui.')
            return redirect('penulis:penulis_dashboard')
        return render(request, self.template_name, {
            'form': form,
            'berita': berita,
            'is_edit': True,
        })


class BeritaDeleteView(PenulisRequiredMixin, View):
    """Penulis menghapus berita miliknya sendiri."""

    def post(self, request, pk):
        berita = get_object_or_404(Berita, id_berita=pk)

        if berita.id_penulis != request.user:
            messages.error(request, 'Anda tidak memiliki izin untuk menghapus berita ini.')
            return redirect('penulis:penulis_dashboard')

        judul = berita.judul

        if berita.gambar_utama:
            import os
            try:
                if os.path.isfile(berita.gambar_utama.path):
                    os.remove(berita.gambar_utama.path)
            except Exception:
                pass

        berita.delete()
        messages.success(request, f'Berita "{judul}" berhasil dihapus.')
        return redirect('penulis:penulis_dashboard')


# ─── API: Koreksi AI ──────────────────────────────────────────────────────

class KoreksiAIView(LoginRequiredMixin, View):
    """API endpoint untuk koreksi teks AI (AJAX)."""

    def post(self, request):
        # Cek rate limit editor
        is_limited, _, _ = RateLimiter.check_editor_limit(request)
        if is_limited:
            return JsonResponse({'success': False, 'error': 'Batas koreksi AI hari ini sudah tercapai (10x). Coba lagi besok.'})

        # Cek budget
        if not BudgetLimiter.can_use_ai(BudgetLimiter.COST_EDITOR):
            return JsonResponse({'success': False, 'error': 'Layanan AI sedang maintenance bulan ini.'})

        try:
            data = json.loads(request.body)
            konten_draft = data.get('konten_draft', '').strip()
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'success': False, 'error': 'Data tidak valid.'}, status=400)

        if not konten_draft:
            return JsonResponse({'success': False, 'error': 'Konten draft tidak boleh kosong.'}, status=400)

        try:
            service = OpenAIService()
            result = service.koreksi_berita(konten_draft)
            BudgetLimiter.add_cost(BudgetLimiter.COST_EDITOR)
            return JsonResponse({
                'success': True,
                'konten_final': result['konten_final'],
                'saran_ai': result['saran_ai'],
                'saran_list': result.get('saran_list', []),
            })
        except OpenAIServiceError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ─── Publik: Profil Organisasi ───────────────────────────────────────────

# Urutan prioritas jabatan untuk halaman struktur organisasi
JABATAN_ORDER = [
    JabatanKader.KETUA_UMUM,
    JabatanKader.SEKRETARIS_UMUM,
    JabatanKader.BENDAHARA_UMUM,
    JabatanKader.KETUA_BID_ORGANISASI, JabatanKader.SEKRETARIS_BID_ORGANISASI,
    JabatanKader.KETUA_BID_KADERISASI, JabatanKader.SEKRETARIS_BID_KADERISASI,
    JabatanKader.KETUA_BID_RISTEK, JabatanKader.SEKRETARIS_BID_RISTEK,
    JabatanKader.KETUA_BID_KAJIAN, JabatanKader.SEKRETARIS_BID_KAJIAN,
    JabatanKader.KETUA_BID_HIKMAH, JabatanKader.SEKRETARIS_BID_HIKMAH,
    JabatanKader.KETUA_BID_IMAWATI, JabatanKader.SEKRETARIS_BID_IMAWATI,
    JabatanKader.KETUA_BID_MEDKOM, JabatanKader.SEKRETARIS_BID_MEDKOM,
    JabatanKader.KETUA_BID_SOSIAL, JabatanKader.SEKRETARIS_BID_SOSIAL,
    JabatanKader.KETUA_BID_LH, JabatanKader.SEKRETARIS_BID_LH,
    JabatanKader.KETUA_BID_EKONOMI, JabatanKader.SEKRETARIS_BID_EKONOMI,
    JabatanKader.KETUA_BID_PEMUDA, JabatanKader.SEKRETARIS_BID_PEMUDA,
]


class StrukturOrganisasiView(View):
    """Halaman publik struktur kepengurusan organisasi."""

    template_name = 'profil/struktur_organisasi.html'

    def get(self, request):
        from apps.kader.models import BiodataKader

        structural_jabatan = [j.value for j in JABATAN_ORDER]
        pengurus = BiodataKader.objects.filter(
            jabatan_struktural__in=structural_jabatan,
        )

        order_map = {j: i for i, j in enumerate(structural_jabatan)}
        pengurus_sorted = sorted(pengurus, key=lambda p: order_map.get(p.jabatan_struktural, 999))

        pimpinan_inti = [p for p in pengurus_sorted if p.jabatan_struktural in [
            JabatanKader.KETUA_UMUM, JabatanKader.SEKRETARIS_UMUM, JabatanKader.BENDAHARA_UMUM,
        ]]
        bidang_list = []
        i = 3
        while i < len(structural_jabatan):
            ketua_jab = structural_jabatan[i]
            sekretaris_jab = structural_jabatan[i + 1] if i + 1 < len(structural_jabatan) else None
            ketua = next((p for p in pengurus_sorted if p.jabatan_struktural == ketua_jab), None)
            sekretaris = next((p for p in pengurus_sorted if p.jabatan_struktural == sekretaris_jab), None) if sekretaris_jab else None
            nama_bidang = dict(JabatanKader.choices).get(ketua_jab, '').replace('Ketua ', '')
            bidang_list.append({
                'nama': nama_bidang,
                'ketua': ketua,
                'sekretaris': sekretaris,
            })
            i += 2

        return render(request, self.template_name, {
            'pimpinan_inti': pimpinan_inti,
            'bidang_list': bidang_list,
        })


class VisiMisiPublikView(View):
    """Halaman publik visi dan misi organisasi."""

    template_name = 'profil/visi_misi.html'

    def get(self, request):
        visimisi = VisiMisi.objects.filter(is_active=True).first()
        return render(request, self.template_name, {'visimisi': visimisi})


class SejarahPublikView(View):
    """Halaman publik sejarah organisasi."""

    template_name = 'profil/sejarah.html'

    def get(self, request):
        sejarah = Sejarah.objects.filter(is_active=True).first()
        return render(request, self.template_name, {'sejarah': sejarah})


# ─── Admin: CRUD Kata Sambutan ───────────────────────────────────────────

class SambutanListView(AdminRequiredMixin, ListView):
    """Daftar kata sambutan."""

    model = KataSambutan
    template_name = 'profil/admin/sambutan_list.html'
    context_object_name = 'sambutan_list'


class SambutanCreateView(AdminRequiredMixin, View):
    """Buat kata sambutan baru."""

    template_name = 'profil/admin/sambutan_form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': KataSambutanForm()})

    def post(self, request):
        form = KataSambutanForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kata sambutan berhasil ditambahkan.')
            return redirect('profil_admin:sambutan_list')
        return render(request, self.template_name, {'form': form})


class SambutanUpdateView(AdminRequiredMixin, View):
    """Edit kata sambutan."""

    template_name = 'profil/admin/sambutan_form.html'

    def get(self, request, pk):
        sambutan = get_object_or_404(KataSambutan, pk=pk)
        return render(request, self.template_name, {'form': KataSambutanForm(instance=sambutan), 'is_edit': True, 'sambutan': sambutan})

    def post(self, request, pk):
        sambutan = get_object_or_404(KataSambutan, pk=pk)
        form = KataSambutanForm(request.POST, request.FILES, instance=sambutan)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kata sambutan berhasil diperbarui.')
            return redirect('profil_admin:sambutan_list')
        return render(request, self.template_name, {'form': form, 'is_edit': True, 'sambutan': sambutan})


class SambutanDeleteView(AdminRequiredMixin, View):
    """Hapus kata sambutan."""

    def post(self, request, pk):
        sambutan = get_object_or_404(KataSambutan, pk=pk)
        sambutan.delete()
        messages.success(request, 'Kata sambutan berhasil dihapus.')
        return redirect('profil_admin:sambutan_list')


# ─── Admin: CRUD Visi & Misi ────────────────────────────────────────────

class VisiMisiListView(AdminRequiredMixin, ListView):
    """Daftar visi & misi."""

    model = VisiMisi
    template_name = 'profil/admin/visimisi_list.html'
    context_object_name = 'visimisi_list'


class VisiMisiCreateView(AdminRequiredMixin, View):
    """Buat visi & misi baru."""

    template_name = 'profil/admin/visimisi_form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': VisiMisiForm()})

    def post(self, request):
        form = VisiMisiForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Visi & Misi berhasil ditambahkan.')
            return redirect('profil_admin:visimisi_list')
        return render(request, self.template_name, {'form': form})


class VisiMisiUpdateView(AdminRequiredMixin, View):
    """Edit visi & misi."""

    template_name = 'profil/admin/visimisi_form.html'

    def get(self, request, pk):
        visimisi = get_object_or_404(VisiMisi, pk=pk)
        return render(request, self.template_name, {'form': VisiMisiForm(instance=visimisi), 'is_edit': True, 'visimisi': visimisi})

    def post(self, request, pk):
        visimisi = get_object_or_404(VisiMisi, pk=pk)
        form = VisiMisiForm(request.POST, instance=visimisi)
        if form.is_valid():
            form.save()
            messages.success(request, 'Visi & Misi berhasil diperbarui.')
            return redirect('profil_admin:visimisi_list')
        return render(request, self.template_name, {'form': form, 'is_edit': True, 'visimisi': visimisi})


class VisiMisiDeleteView(AdminRequiredMixin, View):
    """Hapus visi & misi."""

    def post(self, request, pk):
        visimisi = get_object_or_404(VisiMisi, pk=pk)
        visimisi.delete()
        messages.success(request, 'Visi & Misi berhasil dihapus.')
        return redirect('profil_admin:visimisi_list')


# ─── Admin: CRUD Sejarah ────────────────────────────────────────────────

class SejarahListView(AdminRequiredMixin, ListView):
    """Daftar sejarah."""

    model = Sejarah
    template_name = 'profil/admin/sejarah_list.html'
    context_object_name = 'sejarah_list'


class SejarahCreateView(AdminRequiredMixin, View):
    """Buat sejarah baru."""

    template_name = 'profil/admin/sejarah_form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': SejarahForm()})

    def post(self, request):
        form = SejarahForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Sejarah berhasil ditambahkan.')
            return redirect('profil_admin:sejarah_list')
        return render(request, self.template_name, {'form': form})


class SejarahUpdateView(AdminRequiredMixin, View):
    """Edit sejarah."""

    template_name = 'profil/admin/sejarah_form.html'

    def get(self, request, pk):
        sejarah = get_object_or_404(Sejarah, pk=pk)
        return render(request, self.template_name, {'form': SejarahForm(instance=sejarah), 'is_edit': True, 'sejarah': sejarah})

    def post(self, request, pk):
        sejarah = get_object_or_404(Sejarah, pk=pk)
        form = SejarahForm(request.POST, request.FILES, instance=sejarah)
        if form.is_valid():
            form.save()
            messages.success(request, 'Sejarah berhasil diperbarui.')
            return redirect('profil_admin:sejarah_list')
        return render(request, self.template_name, {'form': form, 'is_edit': True, 'sejarah': sejarah})


class SejarahDeleteView(AdminRequiredMixin, View):
    """Hapus sejarah."""

    def post(self, request, pk):
        sejarah = get_object_or_404(Sejarah, pk=pk)
        sejarah.delete()
        messages.success(request, 'Sejarah berhasil dihapus.')
        return redirect('profil_admin:sejarah_list')
