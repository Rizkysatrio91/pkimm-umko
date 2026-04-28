"""Service layer untuk app pendaftaran."""
import logging
import uuid
from io import BytesIO

import qrcode
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifikasi.models import Notifikasi
from apps.pendaftaran.models import (
    AbsensiDAD,
    KelompokDAD,
    PendaftaranDAD,
    PeriodeDAD,
    QRAbsensi,
    RundownDAD,
)
from core.constants import NamaKelompok, StatusAbsensi, StatusVerifikasi, TipeNotifikasi
from core.exceptions import SSOServiceError
from core.services import SSOService

logger = logging.getLogger(__name__)


class PendaftaranService:
    """Service untuk alur kerja pendaftaran DAD."""

    @staticmethod
    def process_verifikasi_sso(pendaftaran: PendaftaranDAD) -> None:
        """Proses verifikasi data mahasiswa via API SSO UMKO."""
        biodata = pendaftaran.id_biodata

        try:
            sso = SSOService()
            hasil = sso.validasi_mahasiswa(
                nim=biodata.npm,
                nama_lengkap=biodata.nama_lengkap
            )

            if hasil['is_found']:
                mhs = hasil['mahasiswa_sso']
                pendaftaran.api_nama_sso = mhs.get('nama', '')
                pendaftaran.api_status_mahasiswa = mhs.get('status_mahasiswa', '')
                pendaftaran.api_program_studi = mhs.get('program_studi', '')
            else:
                pendaftaran.api_nama_sso = None
                pendaftaran.api_status_mahasiswa = None
                pendaftaran.api_program_studi = None

            pendaftaran.validasi_identitas()
            pendaftaran.tgl_verifikasi = timezone.now()
            pendaftaran.save()

        except SSOServiceError:
            logger.exception('SSO verification failed for pendaftaran %s', pendaftaran.no_registrasi)
            pendaftaran.status_verifikasi = StatusVerifikasi.MENUNGGU
            pendaftaran.tgl_verifikasi = timezone.now()
            pendaftaran.save()
            return

        # Auto-assign ke kelompok saat peserta LOLOS administrasi
        kelompok_assigned = None
        if pendaftaran.is_identic:
            kelompok_assigned = KelompokService.assign_one_least_full(pendaftaran)

        # Notifikasi otomatis
        user = biodata.id_user
        if user:
            if pendaftaran.is_identic:
                if kelompok_assigned:
                    info_kelompok = f' Anda masuk ke Kelas {kelompok_assigned.nama_kelompok}.'
                else:
                    info_kelompok = ''
                judul = 'Pendaftaran DAD: Lolos Administrasi'
                pesan = (
                    f'Selamat! Pendaftaran Anda ({pendaftaran.no_registrasi}) lolos verifikasi administrasi. '
                    f'Data Anda terverifikasi sebagai mahasiswa UMKO.{info_kelompok}'
                )
            else:
                judul = 'Pendaftaran DAD: Ditolak'
                pesan = (
                    f'Pendaftaran Anda ({pendaftaran.no_registrasi}) ditolak. '
                    f'Data tidak cocok dengan database akademik UMKO.'
                )
            Notifikasi.objects.create(
                id_user=user,
                judul=judul,
                pesan=pesan,
                tipe=TipeNotifikasi.STATUS_VERIFIKASI,
            )


class KelompokService:
    """Service untuk pembagian kelompok DAD."""

    @staticmethod
    @transaction.atomic
    def init_kelompok(periode: PeriodeDAD) -> list[KelompokDAD]:
        """Buat kelompok A, B, C untuk periode jika belum ada."""
        kelompok_list = []
        for nama in NamaKelompok.values:
            obj, _ = KelompokDAD.objects.get_or_create(
                id_periode=periode,
                nama_kelompok=nama,
            )
            kelompok_list.append(obj)
        return kelompok_list

    @staticmethod
    @transaction.atomic
    def assign_kelompok_otomatis(periode: PeriodeDAD) -> dict[str, int]:
        """Bagi peserta LOLOS yang belum punya kelompok secara round-robin.

        Returns dict {'A': count, 'B': count, 'C': count}.
        """
        kelompok_list = KelompokService.init_kelompok(periode)
        peserta = PendaftaranDAD.objects.filter(
            id_periode=periode,
            status_verifikasi=StatusVerifikasi.LOLOS,
            id_kelompok__isnull=True,
        ).order_by('tgl_daftar')

        counts = {k.nama_kelompok: 0 for k in kelompok_list}
        for idx, p in enumerate(peserta):
            kel = kelompok_list[idx % len(kelompok_list)]
            p.id_kelompok = kel
            p.save(update_fields=['id_kelompok'])
            counts[kel.nama_kelompok] += 1
        return counts

    @staticmethod
    @transaction.atomic
    def assign_one_least_full(pendaftaran: PendaftaranDAD) -> KelompokDAD | None:
        """Tempatkan SATU peserta LOLOS ke kelompok dengan anggota paling sedikit.

        Dipanggil otomatis saat peserta baru saja lolos verifikasi SSO.
        Jika peserta sudah punya kelompok, tidak mengubah apa pun.
        """
        if pendaftaran.id_kelompok_id:
            return pendaftaran.id_kelompok
        if pendaftaran.status_verifikasi != StatusVerifikasi.LOLOS:
            return None
        periode = pendaftaran.id_periode
        if not periode:
            return None

        kelompok_list = KelompokService.init_kelompok(periode)
        # Pilih kelompok dengan anggota paling sedikit (seimbang)
        kel_terpilih = min(
            kelompok_list,
            key=lambda k: PendaftaranDAD.objects.filter(id_kelompok=k).count(),
        )
        pendaftaran.id_kelompok = kel_terpilih
        pendaftaran.save(update_fields=['id_kelompok'])
        return kel_terpilih

    @staticmethod
    def pindah_anggota(pendaftaran: PendaftaranDAD, kelompok_baru: KelompokDAD) -> None:
        """Pindah peserta ke kelompok lain."""
        pendaftaran.id_kelompok = kelompok_baru
        pendaftaran.save(update_fields=['id_kelompok'])


class AbsensiService:
    """Service untuk proses absensi QR code."""

    @staticmethod
    @transaction.atomic
    def generate_all_qr(periode: PeriodeDAD) -> int:
        """Batch-create QRAbsensi untuk semua sesi is_absensi × semua kelompok.

        Returns jumlah QR yang berhasil dibuat (skip yang sudah ada).
        """
        kelompok_list = KelompokService.init_kelompok(periode)
        sesi_list = RundownDAD.objects.filter(
            id_periode=periode,
            is_absensi=True,
        )
        created = 0
        for sesi in sesi_list:
            for kel in kelompok_list:
                _, is_new = QRAbsensi.objects.get_or_create(
                    id_rundown=sesi,
                    id_kelompok=kel,
                )
                if is_new:
                    created += 1
        return created

    @staticmethod
    def validate_scan(token_str: str, user) -> dict:
        """Validasi scan QR dan catat absensi.

        Returns {'success': bool, 'message': str, 'materi': str|None}.
        """
        try:
            token_uuid = uuid.UUID(token_str)
        except (ValueError, AttributeError):
            return {'success': False, 'message': 'QR Code tidak valid.', 'materi': None}

        try:
            qr = QRAbsensi.objects.select_related(
                'id_rundown', 'id_kelompok',
            ).get(token=token_uuid)
        except QRAbsensi.DoesNotExist:
            return {'success': False, 'message': 'QR Code tidak ditemukan.', 'materi': None}

        if not qr.is_active:
            return {'success': False, 'message': 'QR Code belum diaktifkan oleh panitia.', 'materi': None}

        # Cari pendaftaran user
        try:
            pendaftaran = PendaftaranDAD.objects.select_related('id_kelompok').get(
                id_biodata__id_user=user,
            )
        except PendaftaranDAD.DoesNotExist:
            return {'success': False, 'message': 'Anda belum terdaftar sebagai peserta DAD.', 'materi': None}

        # Cek kelompok cocok
        if pendaftaran.id_kelompok_id != qr.id_kelompok_id:
            return {
                'success': False,
                'message': f'QR ini untuk Kelas {qr.id_kelompok.nama_kelompok}, bukan kelas Anda.',
                'materi': None,
            }

        # Cek sudah ada row absensi untuk (pendaftaran, qr) — mungkin sudah HADIR
        # atau sudah di-set IZIN/SAKIT oleh panitia sebelumnya.
        existing = AbsensiDAD.objects.filter(
            id_pendaftaran=pendaftaran, id_qr=qr,
        ).first()
        if existing is not None:
            if existing.status == StatusAbsensi.HADIR:
                return {
                    'success': False,
                    'message': 'Anda sudah absen untuk sesi ini.',
                    'materi': qr.id_rundown.materi,
                }
            # Override IZIN/SAKIT/ALPHA tetap HADIR jika benar-benar scan QR aktif
            existing.status = StatusAbsensi.HADIR
            existing.waktu_scan = timezone.now()
            existing.keterangan = ''
            existing.save(update_fields=['status', 'waktu_scan', 'keterangan'])
        else:
            try:
                AbsensiDAD.objects.create(
                    id_pendaftaran=pendaftaran,
                    id_qr=qr,
                    status=StatusAbsensi.HADIR,
                    waktu_scan=timezone.now(),
                )
            except IntegrityError:
                return {'success': False, 'message': 'Anda sudah absen untuk sesi ini.', 'materi': None}

        # Sinkronkan ulang poin kedisiplinan kalau NilaiAktivitas hari tsb sudah
        # ada — supaya kalau panitia input keaktifan/kontribusi DULU lalu peserta
        # absen sesi tertunda, skor harian otomatis update tanpa intervensi.
        # Import di sini (bukan di top) untuk hindari circular import.
        from apps.penilaian.services import AktivitasService
        AktivitasService.sinkron_poin_kedisiplinan_untuk_sesi(qr.id_rundown, pendaftaran)

        return {
            'success': True,
            'message': f'Absensi berhasil! Sesi: {qr.id_rundown.materi}',
            'materi': qr.id_rundown.materi,
        }

    @staticmethod
    def generate_qr_image(token: uuid.UUID, base_url: str = '') -> bytes:
        """Generate QR code image sebagai PNG bytes."""
        scan_url = f"{base_url}/pendaftaran/absensi/scan/{token}/"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(scan_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='#5B1525', back_color='#FDF8F0')

        buffer = BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()

    @staticmethod
    def get_rekap_absensi(periode: PeriodeDAD, kelompok: KelompokDAD | None = None):
        """Rekap kehadiran per peserta.

        Returns list of dicts: [{pendaftaran, nama, total_sesi, hadir, persen}].
        """
        total_sesi = RundownDAD.objects.filter(
            id_periode=periode, is_absensi=True,
        ).count()

        qs = PendaftaranDAD.objects.filter(
            id_periode=periode,
            id_kelompok__isnull=False,
        ).select_related('id_biodata', 'id_kelompok')

        if kelompok:
            qs = qs.filter(id_kelompok=kelompok)

        rekap = []
        for p in qs.order_by('id_kelompok__nama_kelompok', 'id_biodata__nama_lengkap'):
            hadir = AbsensiDAD.objects.filter(id_pendaftaran=p).count()
            persen = round(hadir / total_sesi * 100, 1) if total_sesi > 0 else 0
            rekap.append({
                'pendaftaran': p,
                'nama': p.id_biodata.nama_lengkap,
                'kelompok': p.id_kelompok.nama_kelompok if p.id_kelompok else '-',
                'total_sesi': total_sesi,
                'hadir': hadir,
                'persen': persen,
            })
        return rekap
