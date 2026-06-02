"""Views untuk app notifikasi."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from apps.notifikasi.models import Notifikasi


class NotifikasiListView(LoginRequiredMixin, ListView):
    """Daftar semua notifikasi user yang login."""

    model = Notifikasi
    template_name = 'notifikasi/list.html'
    context_object_name = 'notifikasi_list'
    paginate_by = 10

    def get_queryset(self):
        return Notifikasi.objects.filter(id_user=self.request.user).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Flag untuk menampilkan tombol "Hapus yang Sudah Dibaca" hanya jika
        # memang ada notifikasi terbaca yang bisa dihapus.
        context['has_read'] = Notifikasi.objects.filter(
            id_user=self.request.user, is_read=True
        ).exists()
        return context


class NotifikasiMarkReadView(LoginRequiredMixin, View):
    """Tandai satu notifikasi sebagai dibaca (POST atau AJAX)."""

    def post(self, request, pk):
        notif = get_object_or_404(Notifikasi, id_notif=pk, id_user=request.user)
        notif.tandai_dibaca()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok'})
        return redirect('notifikasi:list')


class NotifikasiMarkAllReadView(LoginRequiredMixin, View):
    """Tandai semua notifikasi user sebagai dibaca."""

    def post(self, request):
        Notifikasi.objects.filter(id_user=request.user, is_read=False).update(is_read=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok'})
        return redirect('notifikasi:list')


class NotifikasiDeleteReadView(LoginRequiredMixin, View):
    """Hapus semua notifikasi user yang SUDAH dibaca (is_read=True).

    Notifikasi yang belum dibaca sengaja tidak dihapus supaya user tidak
    kehilangan informasi yang belum sempat dilihat. Difilter id_user agar
    user hanya bisa menghapus notifikasi miliknya sendiri.
    """

    def post(self, request):
        deleted, _ = Notifikasi.objects.filter(
            id_user=request.user, is_read=True
        ).delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok', 'deleted': deleted})
        return redirect('notifikasi:list')
