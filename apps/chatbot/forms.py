"""Forms untuk app chatbot."""
from django import forms

from apps.chatbot.models import DatasetChatbot


class DatasetChatbotForm(forms.ModelForm):
    """Form untuk membuat/mengedit entri dataset chatbot."""

    class Meta:
        model = DatasetChatbot
        fields = [
            'intent_keyword',
            'respon_jawaban',
            'instruksi_ai',
            'kategori',
            'jenis_chatbot',
            'is_active',
        ]
