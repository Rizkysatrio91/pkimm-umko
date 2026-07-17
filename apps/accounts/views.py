"""View untuk app accounts — semua menggunakan CBV."""
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from apps.accounts.forms import (
    ChangePasswordForm,
    ForgotPasswordForm,
    LoginForm,
    ProfileForm,
    RegisterForm,
    ResetPasswordForm,
    VerifyOTPForm,
)
from apps.accounts.models import User
from apps.accounts.services import OTPService
from core.exceptions import SSOServiceError
from core.rate_limiter import RateLimiter
from core.services import SSOService
from core.validators import validate_image_upload

ROLE_DASHBOARD_MAP = {
    'admin': '/admin-dashboard/',
    'panitia': '/panitia/dashboard/',
    'penulis': '/penulis/dashboard/',
    'calon_kader': '/kader/dashboard/',
}


class LoginView(View):
    """View login dengan redirect berbasis role."""

    template_name = 'accounts/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('accounts:login_redirect')
        form = LoginForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        # CEK RATE LIMIT LOGIN
        is_limited, _, retry = RateLimiter.check_login_limit(request)
        if is_limited:
            menit = max(1, retry // 60)
            messages.error(request, f'Terlalu banyak percobaan login yang gagal. Coba lagi dalam {menit} menit.')
            return render(request, self.template_name, {'form': LoginForm()})

        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            login(request, user)
            # Reset counter setelah berhasil login
            RateLimiter.reset_login_limit(request)
            # Validasi 'next' untuk cegah open redirect: hanya izinkan URL
            # internal (host sama / path relatif). URL eksternal diabaikan
            # supaya tidak bisa dipakai phishing (?next=https://situs-jahat).
            next_url = request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect('accounts:login_redirect')

        # Tampilkan sisa percobaan jika mendekati batas
        attempts = RateLimiter.get_login_attempts(request)
        sisa = 5 - attempts
        if 0 < sisa <= 2:
            messages.warning(request, f'Username atau password salah. Sisa {sisa} percobaan sebelum akun diblokir sementara.')
        return render(request, self.template_name, {'form': form})


class LogoutView(View):
    """Logout dan redirect ke halaman login."""

    def get(self, request):
        logout(request)
        messages.success(request, 'Anda telah berhasil logout.')
        return redirect('accounts:login')

    def post(self, request):
        return self.get(request)


def _mask_email(email: str) -> str:
    """Samarkan sebagian email agar tak membocorkan alamat penuh di layar.

    Contoh: '2259201005@umko.ac.id' → '22•••••••5@umko.ac.id'.
    """
    local, sep, domain = (email or '').partition('@')
    if not sep:
        return email or ''
    if len(local) <= 3:
        masked = local[:1] + '•' * max(1, len(local) - 1)
    else:
        masked = local[:2] + '•' * (len(local) - 3) + local[-1]
    return f'{masked}@{domain}'


def _create_calon_kader_account(pending: dict) -> None:
    """Buat User (role calon_kader) + BiodataKader dari data pending registrasi.

    Dipakai dua jalur: registrasi langsung (dev/lokal, tanpa OTP) dan setelah
    verifikasi OTP (produksi). Email akun = email kampus. Password sudah di-hash
    saat langkah 1 sehingga di-set langsung tanpa hashing ulang.
    """
    from apps.kader.models import BiodataKader

    bio = pending['biodata']
    npm = pending['npm']

    tgl_lahir = None
    raw_tgl = bio.get('tgl_lahir') or ''
    if raw_tgl:
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
            try:
                tgl_lahir = datetime.strptime(str(raw_tgl)[:10], fmt).date()
                break
            except ValueError:
                continue

    angkatan = f"20{npm[:2]}" if len(npm) >= 2 and npm[:2].isdigit() else ''

    with transaction.atomic():
        user = User(
            username=pending['username'],
            email=pending['email'],
            role='calon_kader',
        )
        user.password = pending['password_hash']  # sudah di-hash, jangan hash ulang
        user.save()

        BiodataKader.objects.create(
            id_user=user,
            npm=npm,
            nama_lengkap=bio.get('nama', ''),
            program_studi=(bio.get('program_studi') or '')[:50],
            fakultas=(bio.get('fakultas') or '')[:50],
            angkatan=angkatan[:4],
            tempat_lahir=(bio.get('tempat_lahir') or '')[:50],
            tgl_lahir=tgl_lahir,
            jenis_kelamin=(bio.get('jenis_kelamin') or '')[:1],
            alamat_domisili=bio.get('alamat') or '',
            no_hp=(bio.get('hp') or '')[:15],
            jabatan_struktural='calon',
        )


class RegisterView(View):
    """Registrasi untuk calon kader."""

    template_name = 'accounts/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('accounts:login_redirect')
        form = RegisterForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = RegisterForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        npm = form.cleaned_data['npm']

        # 1. Validasi NPM ke SSO UMKO
        try:
            sso = SSOService()
            mhs = sso.get_mahasiswa_by_nim(npm)
        except SSOServiceError as e:
            messages.error(request, f'Tidak dapat memverifikasi NPM ke SSO UMKO: {e}')
            return render(request, self.template_name, {'form': form})

        if mhs is None:
            form.add_error('npm', f'NPM {npm} tidak terdaftar di database mahasiswa UMKO.')
            return render(request, self.template_name, {'form': form})

        # 2. Cek prodi diizinkan berdasarkan konfigurasi admin
        from apps.kader.models import KonfigurasiSistem
        konfig = KonfigurasiSistem.get_instance()
        if not konfig.sso_id_fakultas or not konfig.allowed_prodi_codes:
            messages.error(
                request,
                'Pendaftaran belum dibuka. Administrator belum mengatur fakultas yang diizinkan.'
            )
            return render(request, self.template_name, {'form': form})

        if not konfig.is_prodi_allowed(mhs.get('id_program_studi', '')):
            form.add_error(
                'npm',
                f'Program studi "{mhs.get("program_studi", "-")}" tidak diizinkan mendaftar. '
                f'Pendaftaran hanya dibuka untuk fakultas {konfig.sso_nama_fakultas}.'
            )
            return render(request, self.template_name, {'form': form})

        # 3. Siapkan data pending. Email AKUN = email kampus dari SSO (bukan email
        #    bebas) — sekaligus tujuan OTP. Password di-hash sejak sekarang.
        campus_email = (mhs.get('email_kampus') or '').strip() or f'{npm}@umko.ac.id'
        pending = {
            'username': form.cleaned_data['username'],
            'email': campus_email,
            'password_hash': make_password(form.cleaned_data['password1']),
            'npm': npm,
            'campus_email': campus_email,
            'biodata': {
                'nama': mhs.get('nama', ''),
                'program_studi': mhs.get('program_studi', ''),
                'tempat_lahir': mhs.get('tempat_lahir', ''),
                'tgl_lahir': str(mhs.get('tanggal_lahir') or mhs.get('tgl_lahir') or ''),
                'jenis_kelamin': mhs.get('jenis_kelamin', ''),
                'alamat': mhs.get('alamat_domisili') or mhs.get('alamat', ''),
                'hp': mhs.get('hp', ''),
                'fakultas': konfig.sso_nama_fakultas,
            },
        }

        # LOKAL/DEV (REGISTRATION_REQUIRE_OTP=False): buat akun LANGSUNG tanpa OTP,
        # supaya data uji masuk otomatis tanpa perlu menerima email kampus.
        if not settings.REGISTRATION_REQUIRE_OTP:
            try:
                _create_calon_kader_account(pending)
            except IntegrityError:
                messages.error(
                    request,
                    'Username atau email kampus untuk NPM ini sudah terdaftar.',
                )
                return render(request, self.template_name, {'form': form})
            messages.success(
                request,
                'Registrasi berhasil! Biodata terisi otomatis dari SSO UMKO. Silakan login.',
            )
            return redirect('accounts:login')

        # PRODUKSI (default True): wajib verifikasi OTP ke email kampus sebagai
        # bukti kepemilikan NPM. Akun BELUM dibuat sampai OTP cocok — orang yang
        # memasukkan NPM acak milik mahasiswa lain tidak bisa menyelesaikannya.
        is_limited, _, retry = RateLimiter.check_register_otp_limit(request)
        if is_limited:
            menit = max(1, retry // 60)
            messages.error(
                request,
                f'Terlalu banyak permintaan kode verifikasi. Coba lagi dalam {menit} menit.',
            )
            return render(request, self.template_name, {'form': form})

        code = OTPService.generate_code()
        pending['otp_hash'] = make_password(code)
        pending['otp_expires'] = (timezone.now() + timedelta(minutes=10)).isoformat()
        request.session['pending_registration'] = pending
        OTPService.send_registration_otp(campus_email, code, pending['username'])
        messages.info(
            request,
            f'Kode verifikasi telah dikirim ke email kampus Anda ({_mask_email(campus_email)}). '
            f'Masukkan kode tersebut untuk menyelesaikan pendaftaran.',
        )
        return redirect('accounts:register_verify_otp')


class RegisterVerifyOTPView(View):
    """Langkah 2 pendaftaran: verifikasi OTP yang dikirim ke email kampus.

    Akun + biodata baru dibuat DI SINI, hanya setelah OTP cocok — membuktikan
    pendaftar adalah pemilik NPM (punya akses ke mailbox @umko.ac.id).
    """

    template_name = 'accounts/register_verify_otp.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('accounts:login_redirect')
        if 'pending_registration' not in request.session:
            messages.error(request, 'Silakan mulai pendaftaran terlebih dahulu.')
            return redirect('accounts:register')
        return super().dispatch(request, *args, **kwargs)

    def _render(self, request, form):
        pending = request.session['pending_registration']
        return render(request, self.template_name, {
            'form': form,
            'masked_email': _mask_email(pending['campus_email']),
        })

    def get(self, request):
        if request.GET.get('action') == 'resend':
            return self._resend(request)
        return self._render(request, VerifyOTPForm())

    def _resend(self, request):
        is_limited, _, retry = RateLimiter.check_register_otp_limit(request)
        if is_limited:
            menit = max(1, retry // 60)
            messages.error(
                request,
                f'Terlalu banyak permintaan kode. Coba lagi dalam {menit} menit.',
            )
            return redirect('accounts:register_verify_otp')
        pending = request.session['pending_registration']
        code = OTPService.generate_code()
        pending['otp_hash'] = make_password(code)
        pending['otp_expires'] = (timezone.now() + timedelta(minutes=10)).isoformat()
        request.session['pending_registration'] = pending
        request.session.modified = True
        OTPService.send_registration_otp(pending['campus_email'], code, pending['username'])
        messages.info(request, 'Kode OTP baru telah dikirim ke email kampus Anda.')
        return redirect('accounts:register_verify_otp')

    def post(self, request):
        form = VerifyOTPForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)

        # Anti brute-force: batasi percobaan tebak OTP per IP.
        is_limited, _, retry = RateLimiter.check_otp_verify_limit(request)
        if is_limited:
            menit = max(1, retry // 60)
            messages.error(
                request,
                f'Terlalu banyak percobaan kode OTP. Coba lagi dalam {menit} menit.',
            )
            return self._render(request, VerifyOTPForm())

        pending = request.session['pending_registration']
        otp = form.cleaned_data['otp'].strip()

        expired_at = datetime.fromisoformat(pending['otp_expires'])
        if timezone.now() >= expired_at:
            messages.error(
                request,
                'Kode OTP sudah kedaluarsa. Klik "Kirim ulang OTP" untuk kode baru.',
            )
            return self._render(request, VerifyOTPForm())

        if not check_password(otp, pending['otp_hash']):
            messages.error(request, 'Kode OTP salah. Periksa email kampus Anda.')
            return self._render(request, VerifyOTPForm())

        # OTP valid → buat akun + biodata.
        RateLimiter.reset_otp_verify_limit(request)
        try:
            _create_calon_kader_account(pending)
        except IntegrityError:
            messages.error(
                request,
                'Username, email, atau NPM sudah terdaftar. Silakan mulai '
                'pendaftaran ulang dengan data yang berbeda.',
            )
            request.session.pop('pending_registration', None)
            return redirect('accounts:register')

        request.session.pop('pending_registration', None)
        messages.success(
            request,
            'Verifikasi berhasil! Akun Anda telah dibuat dan biodata terisi '
            'otomatis dari SSO UMKO. Silakan login.',
        )
        return redirect('accounts:login')


class ForgotPasswordView(View):
    """Langkah 1: Input email, kirim OTP.

    Keamanan:
      - Rate limit 3 percobaan per 15 menit per IP (mencegah spam OTP).
      - Tidak mengungkap apakah email terdaftar (anti user enumeration):
        pesan ke user selalu sama baik email ada maupun tidak.
    """

    template_name = 'accounts/forgot_password.html'

    def get(self, request):
        form = ForgotPasswordForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        # Rate limit sebelum pemrosesan apapun
        is_limited, _, retry = RateLimiter.check_forgot_password_limit(request)
        if is_limited:
            menit = max(1, retry // 60)
            messages.error(
                request,
                f'Terlalu banyak permintaan reset password. Coba lagi dalam {menit} menit.',
            )
            return render(request, self.template_name, {'form': ForgotPasswordForm()})

        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            # Simpan email ke session supaya flow verifikasi OTP bisa dilanjutkan
            # meskipun email tidak terdaftar (user tetap diarahkan ke halaman OTP
            # agar attacker tidak bisa bedakan email yang valid dari respons).
            request.session['reset_email'] = email

            user = User.objects.filter(email=email).first()
            if user is not None:
                OTPService.send_otp_email(user)
            # Pesan selalu sama, bahkan kalau email tidak ada di DB. Tujuan: jangan
            # bocorkan apakah email terdaftar. User yang salah email tetap lihat
            # halaman OTP tapi OTP tidak akan pernah cocok.
            messages.info(
                request,
                'Jika email terdaftar, kode OTP akan dikirim ke email Anda. '
                'Silakan cek inbox/spam.',
            )
            return redirect('accounts:verify_otp')
        return render(request, self.template_name, {'form': form})


class VerifyOTPView(View):
    """Langkah 2: Verifikasi kode OTP."""

    template_name = 'accounts/verify_otp.html'

    def dispatch(self, request, *args, **kwargs):
        if 'reset_email' not in request.session:
            messages.error(request, 'Silakan masukkan email terlebih dahulu.')
            return redirect('accounts:forgot_password')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = VerifyOTPForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = VerifyOTPForm(request.POST)
        if form.is_valid():
            # Batasi percobaan tebak OTP (anti brute-force). Dicek hanya saat
            # form valid (6 digit) supaya salah ketik biasa tidak boros kuota.
            is_limited, _, retry = RateLimiter.check_otp_verify_limit(request)
            if is_limited:
                menit = max(1, retry // 60)
                messages.error(
                    request,
                    f'Terlalu banyak percobaan kode OTP. Coba lagi dalam {menit} menit.',
                )
                return render(request, self.template_name, {'form': VerifyOTPForm()})

            email = request.session['reset_email']
            otp = form.cleaned_data['otp']
            try:
                user = User.objects.get(email=email)
                status = user.check_otp(otp)
                if status == 'valid':
                    RateLimiter.reset_otp_verify_limit(request)
                    request.session['otp_verified'] = True
                    return redirect('accounts:reset_password')
                elif status == 'expired':
                    messages.error(
                        request,
                        'Kode OTP sudah kedaluarsa. Silakan klik "Kirim ulang OTP" untuk mendapatkan kode baru.',
                    )
                else:
                    messages.error(request, 'Kode OTP salah. Periksa kembali email Anda.')
            except User.DoesNotExist:
                messages.error(request, 'User tidak ditemukan.')
                return redirect('accounts:forgot_password')
        return render(request, self.template_name, {'form': form})


class ResetPasswordView(View):
    """Langkah 3: Tetapkan password baru."""

    template_name = 'accounts/reset_password.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get('otp_verified'):
            messages.error(request, 'Verifikasi OTP terlebih dahulu.')
            return redirect('accounts:forgot_password')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = ResetPasswordForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            email = request.session.get('reset_email')
            try:
                user = User.objects.get(email=email)
                user.set_password(form.cleaned_data['password1'])
                user.clear_otp()
                user.save()
                # Hapus data session
                request.session.pop('reset_email', None)
                request.session.pop('otp_verified', None)
                messages.success(request, 'Password berhasil diperbarui. Silakan login.')
                return redirect('accounts:login')
            except User.DoesNotExist:
                messages.error(request, 'User tidak ditemukan.')
                return redirect('accounts:forgot_password')
        return render(request, self.template_name, {'form': form})


class LoginRedirectView(LoginRequiredMixin, View):
    """Redirect user yang sudah login ke dashboard sesuai rolenya."""

    def get(self, request):
        url = ROLE_DASHBOARD_MAP.get(request.user.role, '/accounts/login/')
        return redirect(url)


class ProfileView(LoginRequiredMixin, View):
    """Edit profil dan ubah password."""

    template_name = 'accounts/profile.html'

    def _get_biodata(self, request):
        from apps.kader.models import BiodataKader
        return BiodataKader.objects.filter(id_user=request.user).first()

    def get(self, request):
        biodata = self._get_biodata(request)
        profile_form = ProfileForm(instance=request.user, biodata=biodata)
        password_form = ChangePasswordForm(user=request.user)
        return render(request, self.template_name, {
            'profile_form': profile_form,
            'password_form': password_form,
            'biodata': biodata,
        })

    def post(self, request):
        action = request.POST.get('action')
        biodata = self._get_biodata(request)

        if action == 'update_profile':
            profile_form = ProfileForm(request.POST, request.FILES, instance=request.user, biodata=biodata)
            password_form = ChangePasswordForm(user=request.user)
            if profile_form.is_valid():
                # Validasi upload foto profil — ukuran + tipe file
                foto_upload = request.FILES.get('foto_profil')
                if foto_upload is not None:
                    try:
                        validate_image_upload(foto_upload)
                    except ValidationError as exc:
                        messages.error(request, exc.messages[0])
                        return render(request, self.template_name, {
                            'profile_form': profile_form,
                            'password_form': password_form,
                            'biodata': biodata,
                        })
                user = profile_form.save(commit=False)
                if foto_upload is not None:
                    user.foto_profil = foto_upload
                user.save()
                messages.success(request, 'Profil berhasil diperbarui.')
                return redirect('accounts:profile')
        elif action == 'change_password':
            profile_form = ProfileForm(instance=request.user, biodata=biodata)
            password_form = ChangePasswordForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                request.user.set_password(password_form.cleaned_data['new_password1'])
                request.user.save()
                login(request, request.user)
                messages.success(request, 'Password berhasil diubah.')
                return redirect('accounts:profile')
        else:
            profile_form = ProfileForm(instance=request.user, biodata=biodata)
            password_form = ChangePasswordForm(user=request.user)

        return render(request, self.template_name, {
            'profile_form': profile_form,
            'password_form': password_form,
            'biodata': biodata,
        })
