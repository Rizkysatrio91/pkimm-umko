"""
Modul budget bulanan untuk OpenAI API.
Budget $5 dibagi 4 bulan = $1.25/bulan.
Saat periode DAD ramai, budget boleh lebih banyak terpakai.
Saat bulan biasa, hemat otomatis.
"""
from django.core.cache import cache
from django.utils import timezone


class BudgetLimiter:
    """Pembatas budget bulanan untuk OpenAI API."""

    # Budget bulanan: $1.25 agar $5 tahan 4 bulan
    MONTHLY_BUDGET = 1.25

    # Estimasi biaya per request
    COST_CHATBOT = 0.001
    COST_OCR = 0.002
    COST_EDITOR = 0.002

    @classmethod
    def _get_month_key(cls) -> str:
        """Key cache berdasarkan bulan+tahun saat ini."""
        return f"openai_budget_{timezone.now().strftime('%Y%m')}"

    @classmethod
    def _get_today_key(cls) -> str:
        """Key cache untuk tracking harian (monitoring saja)."""
        return f"openai_daily_{timezone.now().strftime('%Y%m%d')}"

    @classmethod
    def get_month_spent(cls) -> float:
        """Total pengeluaran bulan ini."""
        return cache.get(cls._get_month_key(), 0.0)

    @classmethod
    def get_today_spent(cls) -> float:
        """Total pengeluaran hari ini (untuk monitoring dashboard)."""
        return cache.get(cls._get_today_key(), 0.0)

    @classmethod
    def add_cost(cls, cost: float):
        """Catat biaya ke total bulanan dan harian."""
        # Update bulanan (TTL 31 hari)
        month_key = cls._get_month_key()
        current_month = cache.get(month_key, 0.0)
        cache.set(month_key, current_month + cost, 31 * 86400)

        # Update harian (TTL 24 jam, untuk monitoring saja)
        day_key = cls._get_today_key()
        current_day = cache.get(day_key, 0.0)
        cache.set(day_key, current_day + cost, 86400)

    @classmethod
    def is_budget_exceeded(cls) -> bool:
        """Cek apakah budget bulanan sudah habis."""
        return cls.get_month_spent() >= cls.MONTHLY_BUDGET

    @classmethod
    def get_remaining_budget(cls) -> float:
        """Sisa budget bulan ini."""
        return max(0, cls.MONTHLY_BUDGET - cls.get_month_spent())

    @classmethod
    def can_use_ai(cls, cost: float) -> bool:
        """Cek apakah masih cukup budget untuk request AI."""
        return cls.get_remaining_budget() >= cost
