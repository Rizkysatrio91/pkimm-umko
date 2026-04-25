"""Context processor global."""
from django.http import HttpRequest


def global_context(request: HttpRequest) -> dict:
    """Inject global data ke semua template."""
    context = {}
    if request.user.is_authenticated:
        from apps.notifikasi.models import Notifikasi
        unread_qs = Notifikasi.objects.filter(id_user=request.user, is_read=False)
        context['unread_notif_count'] = unread_qs.count()
        context['recent_notifikasi'] = unread_qs.order_by('-created_at')[:5]
        context['user_role'] = request.user.role
        try:
            from apps.kader.models import BiodataKader
            context['user_biodata'] = BiodataKader.objects.filter(id_user=request.user).first()
        except Exception:
            context['user_biodata'] = None
        # URL foto profil: pakai user.foto_profil (semua role), fallback ke biodata.foto_profil
        if request.user.foto_profil:
            context['user_foto_url'] = request.user.foto_profil.url
        elif context.get('user_biodata') and context['user_biodata'].foto_profil:
            context['user_foto_url'] = context['user_biodata'].foto_profil.url
        else:
            context['user_foto_url'] = None
    return context
