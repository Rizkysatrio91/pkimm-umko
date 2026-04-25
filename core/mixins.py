"""Mixin view kustom untuk kontrol akses berbasis role dan tahap periode."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect

from core.constants import UserRole


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin yang memeriksa role user."""

    allowed_roles: list[str] = []

    def test_func(self) -> bool:
        """Periksa apakah role user ada di allowed_roles."""
        return self.request.user.role in self.allowed_roles

    def handle_no_permission(self):
        """Redirect ke login jika akses ditolak."""
        return redirect('accounts:login')


class AdminRequiredMixin(RoleRequiredMixin):
    """Hanya mengizinkan user dengan role admin."""
    allowed_roles = [UserRole.ADMIN]


class PanitiaRequiredMixin(RoleRequiredMixin):
    """Mengizinkan user dengan role admin dan panitia."""
    allowed_roles = [UserRole.ADMIN, UserRole.PANITIA]


class PenulisRequiredMixin(RoleRequiredMixin):
    """Mengizinkan user dengan role admin dan penulis."""
    allowed_roles = [UserRole.ADMIN, UserRole.PENULIS]


class CalonKaderRequiredMixin(RoleRequiredMixin):
    """Hanya mengizinkan user dengan role calon kader."""
    allowed_roles = [UserRole.CALON_KADER]


class TahapRequiredMixin:
    """Batasi akses view berdasarkan tahap periode DAD yang sedang aktif.

    Pakai bersama role mixin, dan letakkan SETELAH role mixin pada MRO
    agar login+role dicek dulu sebelum tahap:

        class MyView(PanitiaRequiredMixin, TahapRequiredMixin, View):
            allowed_tahap = ['kegiatan_dad']

    Admin selalu di-bypass (agar bisa menyiapkan data sebelum acara).
    Jika periode belum ada atau tahap tidak sesuai, user di-redirect ke
    dashboard role-nya dengan pesan peringatan.
    """

    allowed_tahap: list[str] = []

    TAHAP_LABEL = {
        'nonaktif': 'Periode Nonaktif',
        'belum_dimulai': 'Belum Dimulai',
        'administrasi': 'Tahap 1: Administrasi Pendaftaran',
        'interview': 'Tahap 2: Seleksi Interview',
        'kegiatan_dad': 'Tahap 3: Kegiatan DAD',
        'pengumuman': 'Tahap 4: Pengumuman Kelulusan',
        'jeda_antar_tahap': 'Jeda Antar Tahap',
    }

    def _redirect_fallback(self):
        """Redirect ke dashboard sesuai role (calon kader → dashboard kader)."""
        user = self.request.user
        role = getattr(user, 'role', None)
        if role == UserRole.CALON_KADER:
            return redirect('kader:dashboard')
        if role in (UserRole.ADMIN,):
            return redirect('admin_dashboard')
        if role == UserRole.PANITIA:
            return redirect('panitia:panitia_dashboard')
        return redirect('accounts:login')

    def dispatch(self, request, *args, **kwargs):
        # Admin selalu di-bypass supaya bisa menyiapkan rundown/kelompok sebelum acara.
        if request.user.is_authenticated and getattr(request.user, 'role', None) == UserRole.ADMIN:
            return super().dispatch(request, *args, **kwargs)

        from apps.pendaftaran.models import PeriodeDAD

        periode = PeriodeDAD.get_active_period()
        if not periode:
            messages.warning(
                request,
                'Fitur ini belum tersedia — tidak ada periode DAD yang aktif.',
            )
            return self._redirect_fallback()

        tahap = periode.tahap_saat_ini
        if tahap not in self.allowed_tahap:
            label_boleh = ', '.join(self.TAHAP_LABEL.get(t, t) for t in self.allowed_tahap)
            label_kini = self.TAHAP_LABEL.get(tahap, tahap)
            messages.warning(
                request,
                f'Fitur ini hanya tersedia pada {label_boleh}. '
                f'Tahap saat ini: {label_kini}.',
            )
            return self._redirect_fallback()

        return super().dispatch(request, *args, **kwargs)
