"""Forms untuk app chatbot."""
from django import forms

from apps.chatbot.models import DatasetChatbot, DokumenPengetahuan


class DatasetChatbotForm(forms.ModelForm):
    """Form untuk membuat/mengedit entri dataset chatbot."""

    class Meta:
        model = DatasetChatbot
        fields = [
            'intent_keyword',
            'respon_jawaban',
            'kategori',
            'jenis_chatbot',
            'is_active',
        ]


class DokumenPengetahuanForm(forms.ModelForm):
    """Form upload PDF dokumen pengetahuan untuk RAG."""

    # Validasi tambahan: hanya .pdf, max 10 MB.
    MAX_PDF_SIZE = 10 * 1024 * 1024

    class Meta:
        model = DokumenPengetahuan
        fields = ['judul', 'file_pdf', 'jenis_chatbot', 'is_active']

    def clean_file_pdf(self):
        f = self.cleaned_data.get('file_pdf')
        if not f:
            raise forms.ValidationError('File PDF wajib diunggah.')
        # Periksa ekstensi & content type — jangan percaya satu saja.
        name = (f.name or '').lower()
        if not name.endswith('.pdf'):
            raise forms.ValidationError('Hanya file dengan ekstensi .pdf yang diperbolehkan.')
        if f.size > self.MAX_PDF_SIZE:
            raise forms.ValidationError(
                f'Ukuran file maksimal 10 MB. File Anda: {f.size / 1024 / 1024:.1f} MB.',
            )
        return f
