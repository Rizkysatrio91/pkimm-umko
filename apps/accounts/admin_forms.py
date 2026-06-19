"""Form admin untuk manajemen user."""
from django import forms

from apps.accounts.models import User
from core.constants import UserRole


class AdminUserCreateForm(forms.ModelForm):
    """Form untuk admin membuat user staf (admin/panitia/penulis)."""

    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Password (min. 8 karakter)'}),
    )
    password2 = forms.CharField(
        label='Konfirmasi Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Ulangi password'}),
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role']
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Username'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'Nama Depan'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Nama Belakang'}),
            'role': forms.Select(choices=[
                (UserRole.ADMIN, 'Admin'),
                (UserRole.PANITIA, 'Panitia'),
                (UserRole.PENULIS, 'Penulis'),
            ]),
        }

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if password1 and len(password1) < 8:
            raise forms.ValidationError('Password minimal 8 karakter.')
        return password1

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Password tidak cocok.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.is_active = True
        if commit:
            user.save()
        return user


class AdminUserUpdateForm(forms.ModelForm):
    """Form untuk admin memperbarui detail user.

    Field password opsional: bila dikosongkan, password lama dipertahankan;
    bila diisi, password di-hash ulang dengan ``set_password``. Ini satu-
    satunya jalan bagi admin mereset password staf (panitia/penulis) yang
    lupa/salah password, karena staf tidak punya akses self-service selain
    OTP email.
    """

    password1 = forms.CharField(
        label='Password Baru',
        required=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Kosongkan jika tidak ingin mengubah password',
            'autocomplete': 'new-password',
        }),
        help_text='Isi hanya jika ingin mereset password user ini (min. 8 karakter).',
    )
    password2 = forms.CharField(
        label='Konfirmasi Password Baru',
        required=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Ulangi password baru',
            'autocomplete': 'new-password',
        }),
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Username'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'Nama Depan'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Nama Belakang'}),
            'role': forms.Select(choices=[
                (UserRole.ADMIN, 'Admin'),
                (UserRole.PANITIA, 'Panitia'),
                (UserRole.PENULIS, 'Penulis'),
                (UserRole.CALON_KADER, 'Calon Kader'),
            ]),
        }

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if password1 and len(password1) < 8:
            raise forms.ValidationError('Password minimal 8 karakter.')
        return password1

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p1 != p2:
            self.add_error('password2', 'Password tidak cocok.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        # Hanya ubah password bila admin mengisinya. Kosong = pertahankan hash lama.
        new_password = self.cleaned_data.get('password1')
        if new_password:
            user.set_password(new_password)
        if commit:
            user.save()
        return user
