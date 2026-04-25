"""Forms untuk app berita."""
from django import forms
from django_ckeditor_5.widgets import CKEditor5Widget

from apps.berita.models import Berita, KataSambutan, Sejarah, VisiMisi
from core.validators import validate_image_upload


class BeritaForm(forms.ModelForm):
    """Form untuk membuat/mengedit artikel berita."""

    class Meta:
        model = Berita
        fields = ['judul', 'kategori', 'konten_draft', 'gambar_utama']
        widgets = {
            'konten_draft': CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"},
                config_name='default',
            ),
        }

    def clean_gambar_utama(self):
        gambar = self.cleaned_data.get('gambar_utama')
        validate_image_upload(gambar)
        return gambar


class KataSambutanForm(forms.ModelForm):
    """Form untuk kata sambutan ketua umum."""

    class Meta:
        model = KataSambutan
        fields = ['nama', 'jabatan', 'foto', 'kata_sambutan', 'periode', 'is_active']
        widgets = {
            'nama': forms.TextInput(attrs={'placeholder': 'Nama Ketua Umum'}),
            'jabatan': forms.TextInput(attrs={'placeholder': 'Jabatan'}),
            'kata_sambutan': CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"},
                config_name='default',
            ),
            'periode': forms.TextInput(attrs={'placeholder': 'Contoh: 2024-2025'}),
        }

    def clean_foto(self):
        foto = self.cleaned_data.get('foto')
        validate_image_upload(foto)
        return foto


class VisiMisiForm(forms.ModelForm):
    """Form untuk visi dan misi."""

    class Meta:
        model = VisiMisi
        fields = ['visi', 'misi', 'is_active']
        widgets = {
            'visi': CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"},
                config_name='default',
            ),
            'misi': CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"},
                config_name='default',
            ),
        }


class SejarahForm(forms.ModelForm):
    """Form untuk sejarah organisasi."""

    class Meta:
        model = Sejarah
        fields = ['judul', 'konten', 'gambar', 'is_active']
        widgets = {
            'judul': forms.TextInput(attrs={'placeholder': 'Judul Sejarah'}),
            'konten': CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"},
                config_name='default',
            ),
        }

    def clean_gambar(self):
        gambar = self.cleaned_data.get('gambar')
        validate_image_upload(gambar)
        return gambar
