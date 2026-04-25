"""Signals untuk pembaruan otomatis leaderboard."""
from decimal import Decimal

from django.db.models import Avg
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.penilaian.models import NilaiAktivitas, NilaiInterview, RekapLeaderboard


@receiver(post_save, sender=NilaiInterview)
def update_leaderboard_on_interview(sender, instance: NilaiInterview, **kwargs) -> None:
    """Perbarui RekapLeaderboard ketika NilaiInterview disimpan."""
    rekap, _ = RekapLeaderboard.objects.get_or_create(
        id_pendaftaran=instance.id_pendaftaran,
    )
    rekap.nilai_interview = instance.rata_rata
    rekap.hitung_total_akhir()
    rekap.save()
    RekapLeaderboard.perbarui_semua_peringkat()


@receiver(post_save, sender=NilaiAktivitas)
def update_leaderboard_on_aktivitas(sender, instance: NilaiAktivitas, **kwargs) -> None:
    """Perbarui RekapLeaderboard ketika NilaiAktivitas disimpan."""
    rekap, _ = RekapLeaderboard.objects.get_or_create(
        id_pendaftaran=instance.id_pendaftaran,
    )
    avg = NilaiAktivitas.objects.filter(
        id_pendaftaran=instance.id_pendaftaran,
    ).aggregate(avg_skor=Avg('skor_harian'))
    rekap.total_skor_aktivitas = avg['avg_skor'] or Decimal('0.00')
    rekap.hitung_total_akhir()
    rekap.save()
    RekapLeaderboard.perbarui_semua_peringkat()
