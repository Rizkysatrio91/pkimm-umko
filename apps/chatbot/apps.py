"""Konfigurasi app chatbot."""
from django.apps import AppConfig


class ChatbotConfig(AppConfig):
    """Konfigurasi untuk app chatbot."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.chatbot'
    verbose_name = 'Chatbot AI'
