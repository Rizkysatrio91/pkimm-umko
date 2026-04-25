"""Konfigurasi URL untuk app chatbot."""
from django.urls import path

from apps.chatbot import views

app_name = 'chatbot'

urlpatterns = [
    path('', views.ChatbotPublikView.as_view(), name='publik'),
    path('api/send/', views.ChatbotAPIView.as_view(), name='api_send'),
]

admin_urlpatterns = [
    path('dataset/', views.DatasetListView.as_view(), name='dataset_list'),
    path('dataset/tambah/', views.DatasetCreateView.as_view(), name='dataset_create'),
    path('dataset/<int:pk>/edit/', views.DatasetUpdateView.as_view(), name='dataset_update'),
    path('dataset/<int:pk>/hapus/', views.DatasetDeleteView.as_view(), name='dataset_delete'),
    path('unanswered/<int:pk>/delete/', views.DeleteUnansweredView.as_view(), name='delete_unanswered'),
    path('unanswered/<int:pk>/detail/', views.UnansweredDetailView.as_view(), name='unanswered_detail'),
    path('unanswered/delete-all/', views.DeleteAllUnansweredView.as_view(), name='delete_all_unanswered'),
]
