"""Form untuk app accounts."""
import re

from django import forms
from django.contrib.auth import authenticate

from apps.accounts.models import User


class LoginForm(forms.Form):
    """Form login dengan username/email dan password."""

    username = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'placeholder': 'Username atau Email',
            'autocomplete': 'username',
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Password',
            'autocomplete': 'current-password',
        }),
    )

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')

        if username and password:
            # Izinkan login menggunakan email
            if '@' in username:
                try:
                    user_obj = User.objects.get(email=username)
                    username = user_obj.username
                    cleaned_data['username'] = username
                except User.DoesNotExist:
                    raise forms.ValidationError('Username/email atau password salah.')

            user = authenticate(username=username, password=password)
            if user is None:
                raise forms.ValidationError('Username/email atau password salah.')
            if not user.is_active:
                raise forms.ValidationError('Akun Anda tidak aktif.')
            cleaned_data['user'] = user
        return cleaned_data


class RegisterForm(forms.ModelForm):
    """Form registrasi calon kader — data mahasiswa diambil otomatis dari SSO UMKO.

    Calon kader hanya mengisi: username, email, NPM, password. Nama lengkap,
    fakultas, prodi, dll. diambil otomatis dari API SSO UMKO berdasarkan NPM.
    """

    npm = forms.CharField(
        max_length=20,
        label='NPM',
        widget=forms.TextInput(attrs={
            'placeholder': 'Masukkan NPM UMKO Anda',
            'inputmode': 'numeric',
        }),
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Password (min. 8 karakter)'}),
    )
    password2 = forms.CharField(
        label='Konfirmasi Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Ulangi Password'}),
    )

    class Meta:
        model = User
        fields = ['username', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Username'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email'}),
        }

    def clean_npm(self):
        npm = self.cleaned_data.get('npm', '').strip()
        if not npm.isdigit():
            raise forms.ValidationError('NPM harus berupa angka.')
        if len(npm) < 7:
            raise forms.ValidationError('Format NPM tidak valid.')
        from apps.kader.models import BiodataKader
        if BiodataKader.objects.filter(npm=npm).exists():
            raise forms.ValidationError('NPM sudah terdaftar.')
        return npm

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if not password1:
            return password1
        errors = []
        if len(password1) < 8:
            errors.append('Minimal 8 karakter.')
        if not re.search(r'[A-Z]', password1):
            errors.append('Harus mengandung minimal 1 huruf besar (A-Z).')
        if not re.search(r'[a-z]', password1):
            errors.append('Harus mengandung minimal 1 huruf kecil (a-z).')
        if not re.search(r'[0-9]', password1):
            errors.append('Harus mengandung minimal 1 angka (0-9).')
        if not re.search(r'[!@#$%^&*]', password1):
            errors.append('Harus mengandung minimal 1 karakter spesial (!@#$%^&*).')
        if errors:
            raise forms.ValidationError(errors)
        return password1

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Password tidak cocok.')
        username = cleaned_data.get('username', '')
        email = cleaned_data.get('email', '')
        if password1 and username and password1.lower() == username.lower():
            self.add_error('password1', 'Password tidak boleh sama dengan username.')
        if password1 and email and password1.lower() == email.lower():
            self.add_error('password1', 'Password tidak boleh sama dengan email.')
        return cleaned_data


class ForgotPasswordForm(forms.Form):
    """Langkah 1: Input email untuk reset password.

    Catatan keamanan: form tidak mengungkap apakah email terdaftar atau
    tidak (anti user enumeration). Cek eksistensi dilakukan di view
    secara diam-diam, dan pesan ke user selalu generik.
    """

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'Masukkan email Anda'}),
    )


class VerifyOTPForm(forms.Form):
    """Langkah 2: Input kode OTP."""

    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'placeholder': 'Masukkan 6 digit OTP',
            'maxlength': '6',
            'pattern': '[0-9]{6}',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'class': 'text-center tracking-[0.5em]',
        }),
    )


class ResetPasswordForm(forms.Form):
    """Langkah 3: Tetapkan password baru."""

    password1 = forms.CharField(
        label='Password Baru',
        widget=forms.PasswordInput(attrs={'placeholder': 'Password baru (min. 8 karakter)'}),
    )
    password2 = forms.CharField(
        label='Konfirmasi Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Ulangi password baru'}),
    )

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if not password1:
            return password1
        errors = []
        if len(password1) < 8:
            errors.append('Minimal 8 karakter.')
        if not re.search(r'[A-Z]', password1):
            errors.append('Harus mengandung minimal 1 huruf besar (A-Z).')
        if not re.search(r'[a-z]', password1):
            errors.append('Harus mengandung minimal 1 huruf kecil (a-z).')
        if not re.search(r'[0-9]', password1):
            errors.append('Harus mengandung minimal 1 angka (0-9).')
        if not re.search(r'[!@#$%^&*]', password1):
            errors.append('Harus mengandung minimal 1 karakter spesial (!@#$%^&*).')
        if errors:
            raise forms.ValidationError(errors)
        return password1

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Password tidak cocok.')
        return cleaned_data


class ProfileForm(forms.ModelForm):
    """Form untuk mengedit profil user."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Nama Depan'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Nama Belakang'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email'}),
            'username': forms.TextInput(attrs={'placeholder': 'Username'}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('biodata', None)
        super().__init__(*args, **kwargs)


class ChangePasswordForm(forms.Form):
    """Form untuk mengubah password (memerlukan password lama)."""

    old_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password lama'}),
    )
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password baru (min. 8 karakter)'}),
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Ulangi password baru'}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data.get('old_password')
        if not self.user.check_password(old_password):
            raise forms.ValidationError('Password lama salah.')
        return old_password

    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')
        if not password:
            return password
        errors = []
        if len(password) < 8:
            errors.append('Minimal 8 karakter.')
        if not re.search(r'[A-Z]', password):
            errors.append('Harus mengandung minimal 1 huruf besar (A-Z).')
        if not re.search(r'[a-z]', password):
            errors.append('Harus mengandung minimal 1 huruf kecil (a-z).')
        if not re.search(r'[0-9]', password):
            errors.append('Harus mengandung minimal 1 angka (0-9).')
        if not re.search(r'[!@#$%^&*]', password):
            errors.append('Harus mengandung minimal 1 karakter spesial (!@#$%^&*).')
        if errors:
            raise forms.ValidationError(errors)
        return password

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password1')
        p2 = cleaned_data.get('new_password2')
        if p1 and p2 and p1 != p2:
            self.add_error('new_password2', 'Password tidak cocok.')
        return cleaned_data
