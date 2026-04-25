"""Exception kustom untuk proyek ini."""


class OpenAIServiceError(Exception):
    """Diangkat ketika pemanggilan OpenAI API gagal."""
    pass


class SSOServiceError(Exception):
    """Exception untuk error saat mengakses API SSO UMKO."""
    pass
