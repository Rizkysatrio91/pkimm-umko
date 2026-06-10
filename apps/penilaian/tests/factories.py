"""Fixture helpers untuk test app penilaian.

Hanya bikin minimum row yang dibutuhkan untuk uji service & model.
Tidak memakai library factory_boy supaya tidak menambah dependensi.
"""
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.kader.models import BiodataKader
from apps.pendaftaran.models import (
    AbsensiDAD,
    KelompokDAD,
    PendaftaranDAD,
    PeriodeDAD,
    QRAbsensi,
    RundownDAD,
)
from core.constants import NamaKelompok, StatusAbsensi, UserRole

User = get_user_model()


_counter = {'n': 0}


def _next() -> int:
    """Counter monotonic untuk memastikan unique value antar fixture."""
    _counter['n'] += 1
    return _counter['n']


def make_user(role: str = UserRole.PANITIA, **kwargs) -> User:
    n = _next()
    defaults = {
        'username': f'user{n}',
        'email': f'user{n}@example.com',
        'password': 'TestPass123!',
        'role': role,
    }
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def make_biodata(user: User | None = None, **kwargs) -> BiodataKader:
    n = _next()
    defaults = {
        'npm': f'2259201{n:03d}',
        'nama_lengkap': f'Peserta {n}',
        'program_studi': 'Sistem Informasi',
        'fakultas': 'FTIK',
        'angkatan': '2022',
    }
    defaults.update(kwargs)
    biodata = BiodataKader.objects.create(id_user=user, **defaults)
    return biodata


def make_periode(is_active: bool = True, **kwargs) -> PeriodeDAD:
    n = _next()
    now = timezone.now()
    defaults = {
        'nama_periode': f'DAD Periode {n}',
        'tgl_buka_administrasi': now,
        'tgl_tutup_administrasi': now,
        'is_active': is_active,
    }
    defaults.update(kwargs)
    return PeriodeDAD.objects.create(**defaults)


def make_kelompok(
    periode: PeriodeDAD,
    nama: str = NamaKelompok.A,
    pj: User | None = None,
) -> KelompokDAD:
    return KelompokDAD.objects.create(
        id_periode=periode,
        nama_kelompok=nama,
        id_pj=pj,
    )


def make_pendaftaran(
    biodata: BiodataKader | None = None,
    periode: PeriodeDAD | None = None,
    kelompok: KelompokDAD | None = None,
    **kwargs,
) -> PendaftaranDAD:
    if biodata is None:
        biodata = make_biodata()
    return PendaftaranDAD.objects.create(
        id_biodata=biodata,
        id_periode=periode,
        id_kelompok=kelompok,
        **kwargs,
    )


def make_rundown(
    periode: PeriodeDAD,
    hari_ke: str = 'Hari 1',
    is_absensi: bool = True,
    materi: str = 'Sesi Materi',
    jam_mulai: time = time(8, 0),
    jam_selesai: time = time(10, 0),
    urutan: int = 1,
) -> RundownDAD:
    return RundownDAD.objects.create(
        id_periode=periode,
        hari_ke=hari_ke,
        tanggal=date.today(),
        jam_mulai=jam_mulai,
        jam_selesai=jam_selesai,
        materi=materi,
        is_absensi=is_absensi,
        urutan=urutan,
    )


def make_qr(rundown: RundownDAD, kelompok: KelompokDAD) -> QRAbsensi:
    return QRAbsensi.objects.create(id_rundown=rundown, id_kelompok=kelompok)


def make_absensi(
    pendaftaran: PendaftaranDAD,
    qr: QRAbsensi,
    status: str = StatusAbsensi.HADIR,
) -> AbsensiDAD:
    waktu = timezone.now() if status == StatusAbsensi.HADIR else None
    return AbsensiDAD.objects.create(
        id_pendaftaran=pendaftaran,
        id_qr=qr,
        status=status,
        waktu_scan=waktu,
    )
