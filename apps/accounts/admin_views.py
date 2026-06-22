"""View admin untuk manajemen user."""
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView

from apps.accounts.admin_forms import (
    AdminSetPasswordForm,
    AdminUserCreateForm,
    AdminUserUpdateForm,
)
from apps.accounts.models import User
from core.constants import UserRole
from core.mixins import AdminRequiredMixin


def _other_active_admins_exist(exclude_pk) -> bool:
    """True jika masih ada admin aktif LAIN selain user dengan pk ini.

    Dipakai untuk mencegah lockout: jangan sampai admin terakhir dihapus,
    diturunkan role-nya, atau dinonaktifkan sehingga tak ada lagi yang
    bisa masuk sebagai admin.
    """
    return User.objects.filter(
        role=UserRole.ADMIN, is_active=True,
    ).exclude(pk=exclude_pk).exists()


class UserListView(AdminRequiredMixin, ListView):
    """Admin: daftar semua user dengan filter role & search."""

    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'user_list'
    paginate_by = 10

    def get_queryset(self):
        qs = User.objects.all().order_by('-date_joined')
        role = self.request.GET.get('role')
        if role:
            qs = qs.filter(role=role)
        search = self.request.GET.get('q')
        if search:
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current_role'] = self.request.GET.get('role', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class UserCreateView(AdminRequiredMixin, CreateView):
    """Admin: buat akun staf baru (admin/panitia/penulis)."""

    model = User
    form_class = AdminUserCreateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('user_admin:user_list')

    def form_valid(self, form):
        messages.success(self.request, f'User "{form.instance.username}" berhasil dibuat.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'Tambah User'
        return ctx


class UserUpdateView(AdminRequiredMixin, UpdateView):
    """Admin: edit user (role, status aktif)."""

    model = User
    form_class = AdminUserUpdateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('user_admin:user_list')
    pk_url_kwarg = 'pk'

    def get_object(self, queryset=None):
        return get_object_or_404(User, id_user=self.kwargs['pk'])

    def form_valid(self, form):
        # Cegah lockout: dilarang menurunkan role / menonaktifkan admin
        # aktif terakhir (termasuk diri sendiri bila satu-satunya admin).
        removing_admin = (
            form.cleaned_data.get('role') != UserRole.ADMIN
            or not form.cleaned_data.get('is_active')
        )
        if removing_admin and not _other_active_admins_exist(form.instance.pk):
            messages.error(
                self.request,
                'Tidak dapat menurunkan atau menonaktifkan admin aktif terakhir. '
                'Tetapkan admin aktif lain terlebih dahulu.',
            )
            return self.form_invalid(form)
        messages.success(self.request, f'User "{form.instance.username}" berhasil diperbarui.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'Edit User'
        ctx['is_edit'] = True
        return ctx


class UserPasswordChangeView(AdminRequiredMixin, FormView):
    """Admin: ubah/atur ulang password user mana pun (semua role + diri sendiri).

    Halaman khusus, terpisah dari form edit identitas. Berguna sebagai
    alternatif cepat ketika user lupa password dan reset OTP email merepotkan:
    admin langsung menetapkan password baru di sini lalu memberitahukannya ke
    user yang bersangkutan.
    """

    template_name = 'accounts/user_password_change.html'
    form_class = AdminSetPasswordForm
    success_url = reverse_lazy('user_admin:user_list')

    def get_target_user(self) -> User:
        """User yang passwordnya akan diubah (di-cache per request)."""
        if not hasattr(self, '_target_user'):
            self._target_user = get_object_or_404(User, id_user=self.kwargs['pk'])
        return self._target_user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.get_target_user()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        target = self.get_target_user()
        ctx['target_user'] = target
        ctx['is_self'] = target.pk == self.request.user.pk
        return ctx

    def form_valid(self, form):
        target = form.user
        is_self = target.pk == self.request.user.pk
        form.save()
        # Bila admin mengubah password AKUNNYA SENDIRI, perbarui hash sesi agar
        # tidak otomatis ter-logout oleh SessionAuthenticationMiddleware.
        if is_self:
            update_session_auth_hash(self.request, target)
            messages.success(self.request, 'Password Anda berhasil diubah.')
        else:
            messages.success(
                self.request,
                f'Password user "{target.username}" berhasil diubah.',
            )
        return super().form_valid(form)


class UserDeleteView(AdminRequiredMixin, DeleteView):
    """Admin: hapus user dengan konfirmasi."""

    model = User
    template_name = 'accounts/user_confirm_delete.html'
    success_url = reverse_lazy('user_admin:user_list')

    def get_object(self, queryset=None):
        return get_object_or_404(User, id_user=self.kwargs['pk'])

    def form_valid(self, form):
        user = self.get_object()

        # Cegah lockout: tidak boleh menghapus akun sendiri, dan tidak boleh
        # menghapus admin aktif terakhir. Dicek SEBELUM import/cascade delete.
        if user.pk == self.request.user.pk:
            messages.error(self.request, 'Anda tidak dapat menghapus akun Anda sendiri.')
            return redirect(self.get_success_url())
        if user.role == UserRole.ADMIN:
            messages.error(
                self.request,
                'Akun admin tidak dapat dihapus. Akun admin hanya bisa diedit.',
            )
            return redirect(self.get_success_url())

        from apps.berita.models import Berita
        from apps.chatbot.models import DatasetChatbot, RiwayatChat
        from apps.kader.models import BiodataKader
        from apps.notifikasi.models import Notifikasi
        from apps.pendaftaran.models import PendaftaranDAD
        from apps.penilaian.models import NilaiAktivitas, NilaiInterview, RekapLeaderboard

        username = user.username

        # Hapus data kaderisasi (dari tabel paling dalam ke tabel terluar)
        biodata = BiodataKader.objects.filter(id_user=user).first()
        if biodata:
            pendaftaran = PendaftaranDAD.objects.filter(id_biodata=biodata).first()
            if pendaftaran:
                RekapLeaderboard.objects.filter(id_pendaftaran=pendaftaran).delete()
                NilaiAktivitas.objects.filter(id_pendaftaran=pendaftaran).delete()
                NilaiInterview.objects.filter(id_pendaftaran=pendaftaran).delete()
                pendaftaran.delete()
            biodata.delete()

        # Hapus penilaian yang dilakukan oleh user ini (jika berperan sebagai panitia)
        NilaiInterview.objects.filter(id_panitia=user).delete()
        NilaiAktivitas.objects.filter(id_panitia=user).delete()

        # Hapus data lain yang terkait user
        RiwayatChat.objects.filter(id_user=user).delete()
        Notifikasi.objects.filter(id_user=user).delete()
        Berita.objects.filter(id_penulis=user).delete()
        DatasetChatbot.objects.filter(created_by=user).delete()

        # Hapus akun user itu sendiri
        user.delete()

        messages.success(self.request, f'Akun "{username}" dan semua data terkait berhasil dihapus.')
        return redirect(self.get_success_url())
