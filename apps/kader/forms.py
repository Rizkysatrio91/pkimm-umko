"""Form untuk app kader."""
import datetime

from django import forms

from apps.kader.models import BiodataKader, Fakultas, ProgramStudi
from core.constants import JabatanKader, JenisKelamin
from core.validators import validate_image_upload


def _angkatan_full_choices():
    """Choices tahun angkatan (2020 – tahun ini) untuk biodata."""
    current_year = datetime.datetime.now().year
    return [('', '-- Pilih Angkatan --')] + [
        (str(y), str(y)) for y in range(2020, current_year + 1)
    ]


def _fakultas_choices():
    """Choices fakultas aktif dari database."""
    return [('', '-- Pilih Fakultas --')] + [
        (f.nama_fakultas, f.nama_fakultas)
        for f in Fakultas.objects.filter(is_active=True)
    ]


def _prodi_choices():
    """Choices semua prodi aktif dari database."""
    return [('', '-- Pilih Program Studi --')] + [
        (p.nama_prodi, p.nama_prodi)
        for p in ProgramStudi.objects.filter(is_active=True)
    ]


class BiodataForm(forms.ModelForm):
    """Form untuk calon kader melengkapi biodata mereka."""

    class Meta:
        model = BiodataKader
        fields = [
            'nama_lengkap', 'npm', 'program_studi', 'fakultas', 'angkatan',
            'tempat_lahir', 'tgl_lahir', 'jenis_kelamin', 'alamat_domisili',
            'no_hp', 'nama_ayah', 'nama_ibu', 'no_hp_ortu', 'foto_profil',
        ]
        widgets = {
            'nama_lengkap': forms.TextInput(attrs={'placeholder': 'Nama Lengkap', 'readonly': 'readonly'}),
            'npm': forms.TextInput(attrs={'placeholder': 'NPM', 'readonly': 'readonly'}),
            'program_studi': forms.TextInput(attrs={'readonly': 'readonly'}),
            'fakultas': forms.TextInput(attrs={'readonly': 'readonly'}),
            'angkatan': forms.TextInput(attrs={'readonly': 'readonly'}),
            'tempat_lahir': forms.TextInput(attrs={'placeholder': 'Tempat Lahir'}),
            'tgl_lahir': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'jenis_kelamin': forms.Select(choices=[('', '-- Pilih --')] + list(JenisKelamin.choices)),
            'alamat_domisili': forms.Textarea(attrs={'placeholder': 'Alamat Domisili', 'rows': 3}),
            'no_hp': forms.TextInput(attrs={'placeholder': 'No. HP (08xxxxxxxxxx)'}),
            'nama_ayah': forms.TextInput(attrs={'placeholder': 'Nama Ayah'}),
            'nama_ibu': forms.TextInput(attrs={'placeholder': 'Nama Ibu'}),
            'no_hp_ortu': forms.TextInput(attrs={'placeholder': 'No. HP Orang Tua'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tgl_lahir'].input_formats = ['%Y-%m-%d']

    def clean_foto_profil(self):
        foto = self.cleaned_data.get('foto_profil')
        validate_image_upload(foto)
        return foto


class KaderAdminForm(forms.ModelForm):
    """Form untuk admin membuat/mengedit data kader (tanpa FK user)."""

    class Meta:
        model = BiodataKader
        fields = [
            'npm', 'nama_lengkap', 'program_studi', 'fakultas', 'angkatan',
            'tempat_lahir', 'tgl_lahir', 'jenis_kelamin', 'alamat_domisili',
            'no_hp', 'nama_ayah', 'nama_ibu', 'no_hp_ortu',
            'jabatan_struktural', 'periode_jabatan', 'foto_profil',
        ]
        widgets = {
            'npm': forms.TextInput(attrs={'placeholder': 'NPM'}),
            'nama_lengkap': forms.TextInput(attrs={'placeholder': 'Nama Lengkap'}),
            'program_studi': forms.Select(),
            'fakultas': forms.Select(),
            'angkatan': forms.TextInput(attrs={'placeholder': 'Angkatan', 'maxlength': '4'}),
            'tempat_lahir': forms.TextInput(attrs={'placeholder': 'Tempat Lahir'}),
            'tgl_lahir': forms.DateInput(attrs={'type': 'date'}),
            'jenis_kelamin': forms.Select(choices=[('', '-- Pilih --')] + list(JenisKelamin.choices)),
            'alamat_domisili': forms.Textarea(attrs={'placeholder': 'Alamat Domisili', 'rows': 3}),
            'no_hp': forms.TextInput(attrs={'placeholder': 'No. HP'}),
            'nama_ayah': forms.TextInput(attrs={'placeholder': 'Nama Ayah'}),
            'nama_ibu': forms.TextInput(attrs={'placeholder': 'Nama Ibu'}),
            'no_hp_ortu': forms.TextInput(attrs={'placeholder': 'No. HP Orang Tua'}),
            'jabatan_struktural': forms.Select(choices=[('', '-- Pilih Jabatan --')] + list(JabatanKader.choices)),
            'periode_jabatan': forms.TextInput(attrs={'placeholder': 'Contoh: 2024-2025'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fakultas'].widget = forms.Select(choices=_fakultas_choices())
        self.fields['program_studi'].widget = forms.Select(choices=_prodi_choices())

    def clean_foto_profil(self):
        foto = self.cleaned_data.get('foto_profil')
        validate_image_upload(foto)
        return foto
