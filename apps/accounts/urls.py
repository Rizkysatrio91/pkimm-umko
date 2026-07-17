"""Konfigurasi URL untuk app accounts."""
from django.urls import path

from apps.accounts import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('register/verify-otp/', views.RegisterVerifyOTPView.as_view(), name='register_verify_otp'),
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot_password'),
    path('verify-otp/', views.VerifyOTPView.as_view(), name='verify_otp'),
    path('reset-password/', views.ResetPasswordView.as_view(), name='reset_password'),
    path('redirect/', views.LoginRedirectView.as_view(), name='login_redirect'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
]
