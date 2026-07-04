"""Service layer untuk app penilaian."""
import logging
from decimal import Decimal

from django.db import transaction

from apps.notifikasi.models import Notifikasi
from apps.pendaftaran.models import AbsensiDAD, PendaftaranDAD, PeriodeDAD, QRAbsensi, RundownDAD
from apps.penilaian.models import NilaiAktivitas, RekapLeaderboard
from core.constants import StatusAbsensi, StatusKelulusan, TipeNotifikasi

logger = logging.getLogger(__name__)


# Skor per sesi berdasarkan status kehadiran (skala 0-100)
SKOR_STATUS: dict[str, Decimal] = {
    StatusAbsensi.HADIR.value: Decimal('100'),
    StatusAbsensi.IZIN.value: Decimal('60'),
    StatusAbsensi.SAKIT.value: Decimal('60'),
    StatusAbsensi.ALPHA.value: Decimal('0'),
}


class AktivitasService:
    """Service untuk perhitungan turunan pada NilaiAktivitas.

    Aturan poin kedisiplinan (disepakati dengan user 2026-04-17):
      - Skor per sesi: HADIR=100, IZIN/SAKIT=60, ALPHA (tidak ada row) = 0
      - Poin kedisiplinan harian = rata-rata skor semua sesi is_absensi
        di hari tersebut untuk kelompok peserta
      - Jika tidak ada sesi is_absensi di hari tsb → 0
    """

    @staticmethod
    def hitung_poin_kedisiplinan(pendaftaran: PendaftaranDAD, hari_ke: int) -> Decimal:
        """Hitung poin kedisiplinan (0-100) peserta untuk satu hari DAD.

        Args:
            pendaftaran: PendaftaranDAD peserta
            hari_ke: integer hari DAD (1, 2, atau 3)

        Returns:
            Decimal 0.00 - 100.00 (quantize 2 digit)
        """
        periode = pendaftaran.id_periode
        kelompok = pendaftaran.id_kelompok
        if periode is None or kelompok is None:
            return Decimal('0.00')

        # RundownDAD.hari_ke adalah CharField (label "Hari 1"/"Hari 2"/"Hari 3").
        # Cocokkan case-insensitive dengan label standar.
        hari_label = f'Hari {hari_ke}'
        sesi_list = list(
            RundownDAD.objects.filter(
                id_periode=periode,
                is_absensi=True,
                hari_ke__iexact=hari_label,
            )
        )
        total_sesi = len(sesi_list)
        if total_sesi == 0:
            return Decimal('0.00')

        # Ambil QR untuk sesi-sesi ini × kelompok peserta sekali jalan
        qr_map = {
            qr.id_rundown_id: qr
            for qr in QRAbsensi.objects.filter(
                id_rundown__in=sesi_list,
                id_kelompok=kelompok,
            )
        }
        qr_ids = [qr.id_qr for qr in qr_map.values()]
        absensi_map = {
            a.id_qr_id: a
            for a in AbsensiDAD.objects.filter(
                id_pendaftaran=pendaftaran,
                id_qr_id__in=qr_ids,
            )
        }

        total_skor = Decimal('0')
        for sesi in sesi_list:
            qr = qr_map.get(sesi.id_rundown)
            if qr is None:
                # QR belum di-generate untuk kelompok ini → anggap alpha
                total_skor += SKOR_STATUS[StatusAbsensi.ALPHA.value]
                continue
            absensi = absensi_map.get(qr.id_qr)
            if absensi is None:
                total_skor += SKOR_STATUS[StatusAbsensi.ALPHA.value]
            else:
                total_skor += SKOR_STATUS.get(
                    absensi.status, SKOR_STATUS[StatusAbsensi.ALPHA.value],
                )

        return (total_skor / Decimal(total_sesi)).quantize(Decimal('0.01'))

    @staticmethod
    def _hari_int_from_rundown(rundown: RundownDAD) -> int | None:
        """Ekstrak integer hari dari label RundownDAD.hari_ke (e.g. 'Hari 2' → 2).

        Return None jika tidak bisa di-parse sebagai integer hari DAD.
        """
        label = (rundown.hari_ke or '').strip().lower()
        # Format standar "Hari N"
        if label.startswith('hari'):
            sisa = label[4:].strip()
            if sisa.isdigit():
                return int(sisa)
        return None

    @staticmethod
    def sinkron_poin_kedisiplinan_untuk_sesi(
        rundown: RundownDAD, pendaftaran: PendaftaranDAD,
    ) -> None:
        """Re-hitung poin_kedisiplinan NilaiAktivitas jika sudah ada untuk hari tsb.

        Dipanggil saat panitia mengubah status absensi (IZIN/SAKIT/ALPHA)
        agar NilaiAktivitas yang mungkin sudah tersimpan langsung sinkron.
        No-op jika NilaiAktivitas untuk hari tsb belum ada.
        """
        hari_ke = AktivitasService._hari_int_from_rundown(rundown)
        if hari_ke is None:
            return
        try:
            nilai = NilaiAktivitas.objects.get(
                id_pendaftaran=pendaftaran, hari_ke=hari_ke,
            )
        except NilaiAktivitas.DoesNotExist:
            return
        nilai.poin_kedisiplinan = AktivitasService.hitung_poin_kedisiplinan(
            pendaftaran, hari_ke,
        )
        nilai.save()  # akan trigger hitung_skor_harian & update leaderboard


class KelulusanService:
    """Service untuk memproses keputusan kelulusan."""

    @staticmethod
    @transaction.atomic
    def tetapkan_kelulusan(passing_grade: Decimal, periode: PeriodeDAD | None = None) -> dict:
        """Tetapkan status kelulusan peserta SATU periode berdasarkan passing grade.

        Args:
            periode: PeriodeDAD yang diproses. Default None = periode aktif
                saat ini. Peserta periode lain TIDAK disentuh (status dan
                notifikasi kelulusan mereka tidak diproses ulang).

        Returns:
            dict berisi jumlah: {'lulus': int, 'tidak_lulus': int}
        """
        if periode is None:
            periode = PeriodeDAD.get_active_period()
        if periode is None:
            return {'lulus': 0, 'tidak_lulus': 0}

        rekap_list = RekapLeaderboard.objects.select_related(
            'id_pendaftaran__id_biodata__id_user',
        ).filter(id_pendaftaran__id_periode=periode)

        lulus_count = 0
        tidak_lulus_count = 0

        for rekap in rekap_list:
            pendaftaran = rekap.id_pendaftaran
            biodata = pendaftaran.id_biodata
            user = biodata.id_user

            if rekap.total_akhir >= passing_grade:
                pendaftaran.status_kelulusan = StatusKelulusan.LULUS
                pendaftaran.save(update_fields=['status_kelulusan'])

                # Promosikan ke kader
                biodata.jabatan_struktural = 'kader'
                biodata.save(update_fields=['jabatan_struktural'])

                lulus_count += 1

                if user:
                    Notifikasi.objects.create(
                        id_user=user,
                        judul='Selamat! Anda Dinyatakan LULUS DAD',
                        pesan=(
                            f'Selamat {biodata.nama_lengkap}! Anda dinyatakan LULUS '
                            f'Darul Arqam Dasar (DAD) PK IMM FTIK UMKO dengan total akhir '
                            f'{rekap.total_akhir:.2f} (passing grade: {passing_grade:.2f}). '
                            f'Peringkat Anda: #{rekap.peringkat}.'
                        ),
                        tipe=TipeNotifikasi.STATUS_KELULUSAN,
                    )
            else:
                pendaftaran.status_kelulusan = StatusKelulusan.TIDAK_LULUS
                pendaftaran.save(update_fields=['status_kelulusan'])

                tidak_lulus_count += 1

                if user:
                    Notifikasi.objects.create(
                        id_user=user,
                        judul='Hasil Kelulusan DAD',
                        pesan=(
                            f'Mohon maaf {biodata.nama_lengkap}, Anda dinyatakan '
                            f'Tidak Lulus DAD PK IMM FTIK UMKO dengan total akhir '
                            f'{rekap.total_akhir:.2f} (passing grade: {passing_grade:.2f}). '
                            f'Silakan mengikuti DAD pada periode berikutnya.'
                        ),
                        tipe=TipeNotifikasi.STATUS_KELULUSAN,
                    )

        return {'lulus': lulus_count, 'tidak_lulus': tidak_lulus_count}
