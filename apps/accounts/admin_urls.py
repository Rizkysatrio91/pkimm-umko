"""Pola URL admin untuk manajemen user."""
from django.urls import path

from apps.accounts.admin_views import (
    UserCreateView,
    UserDeleteView,
    UserListView,
    UserPasswordChangeView,
    UserUpdateView,
)

urlpatterns = [
    path('', UserListView.as_view(), name='user_list'),
    path('tambah/', UserCreateView.as_view(), name='user_create'),
    path('<int:pk>/edit/', UserUpdateView.as_view(), name='user_update'),
    path('<int:pk>/ubah-password/', UserPasswordChangeView.as_view(), name='user_password_change'),
    path('<int:pk>/hapus/', UserDeleteView.as_view(), name='user_delete'),
]
