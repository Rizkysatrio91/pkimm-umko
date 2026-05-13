"""Registrasi admin untuk app accounts."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import AuditLog, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Konfigurasi admin untuk model User kustom."""
    list_display = ('username', 'email', 'role', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'email')
    ordering = ('-date_joined',)
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Role & OTP', {'fields': ('role', 'otp_token', 'otp_expired_at')}),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Tampilan read-only audit log akses data sensitif (SSO lookup, dll).

    Append-only: tidak ada izin add/change/delete dari UI admin
    supaya catatan tidak bisa dimanipulasi.
    """
    list_display = ('created_at', 'id_user', 'action', 'target', 'ip_address', 'success')
    list_filter = ('action', 'success', 'created_at')
    search_fields = ('id_user__username', 'target', 'ip_address')
    readonly_fields = ('id_audit', 'id_user', 'action', 'target',
                       'ip_address', 'user_agent', 'success', 'created_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
