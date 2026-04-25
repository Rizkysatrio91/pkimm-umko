"""Form untuk app penilaian."""
from decimal import Decimal

from django import forms

from apps.penilaian.models import NilaiAktivitas, NilaiInterview


INTERVIEW_KATEGORI = [
    {
        'nama': "Al-Qur'an",
        'deskripsi': "Penilaian bacaan Al-Qur'an peserta.",
        'items': [
            ('qur_makhraj_tajwid', 'Makhraj, Ilmu Tajwid & Kelancaran'),
            ('qur_tulis_surat', 'Tuliskan Surat (contoh Al-Maun:1-7)'),
            ('qur_kandungan_surat', 'Kandungan Surat'),
        ],
    },
    {
        'nama': 'Hafalan Ayat',
        'deskripsi': 'Hafalan surat/ayat pilihan.',
        'items': [
            ('hafalan_5_pendek', '5 Surah Pendek dalam Juz 30'),
            ('hafalan_2_pengkaderan', '2 Surah/Ayat Pengkaderan'),
            ('hafalan_1_favorit', '1 Surah/Ayat yang Disukai'),
        ],
    },
    {
        'nama': 'Ideologi',
        'deskripsi': 'Pemahaman ideologi.',
        'items': [
            ('ideologi_umum', 'Pengertian & Macam Ideologi'),
            ('ideologi_muhammadiyah', 'Ideologi Muhammadiyah'),
            ('ideologi_imm', 'Ideologi IMM'),
        ],
    },
    {
        'nama': 'Dialektika',
        'deskripsi': 'Motivasi & minat peserta.',
        'items': [
            ('dialektika_tujuan', 'Tujuan Mengikuti DAD'),
            ('dialektika_minat', 'Minat yang Ingin Dicapai'),
            ('dialektika_bakat', 'Bakat / Kemampuan Peserta'),
        ],
    },
    {
        'nama': 'Kesiapan',
        'deskripsi': 'Kesiapan mengikuti DAD.',
        'items': [
            ('kesiapan_ikut_penuh', 'Kesediaan Mengikuti DAD dari Awal hingga Akhir'),
            ('kesiapan_persiapan', 'Persiapan Peserta Mengikuti DAD'),
            ('kesiapan_konsekuensi', 'Sanggup Menerima Konsekuensi jika Tidak Tertib'),
        ],
    },
]


class NilaiInterviewForm(forms.ModelForm):
    """Form panitia input nilai interview: 5 kategori × 3 sub-item (total 100)."""

    class Meta:
        model = NilaiInterview
        fields = list(NilaiInterview.SUB_FIELDS) + ['catatan']
        widgets = {
            **{
                name: forms.NumberInput(attrs={
                    'min': '0', 'max': '100', 'step': '0.01',
                    'placeholder': '0 - 100',
                })
                for name in NilaiInterview.SUB_FIELDS
            },
            'catatan': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Catatan tambahan (opsional)',
            }),
        }
        labels = {
            name: label
            for kat in INTERVIEW_KATEGORI
            for (name, label) in kat['items']
        }

    def clean(self):
        cleaned = super().clean()
        for field_name in NilaiInterview.SUB_FIELDS:
            val = cleaned.get(field_name)
            if val is None:
                self.add_error(field_name, 'Nilai wajib diisi.')
            elif val < Decimal('0') or val > Decimal('100'):
                self.add_error(field_name, 'Nilai harus antara 0 dan 100.')
        return cleaned

    def iter_kategori(self):
        """Yield (kategori_dict, list_of_bound_fields) untuk rendering grouped."""
        for kat in INTERVIEW_KATEGORI:
            fields = [self[name] for (name, _) in kat['items']]
            yield kat, fields


class NilaiAktivitasForm(forms.ModelForm):
    """Form untuk panitia menginput nilai aktivitas harian.

    Field ``poin_kedisiplinan`` TIDAK disertakan di form — poin tersebut
    dihitung otomatis dari data AbsensiDAD via
    ``AktivitasService.hitung_poin_kedisiplinan`` dan di-set di view.
    """

    class Meta:
        model = NilaiAktivitas
        fields = ['poin_keaktifan', 'poin_kontribusi', 'catatan']
        widgets = {
            'poin_keaktifan': forms.NumberInput(attrs={
                'min': '0', 'max': '100', 'step': '0.01',
                'placeholder': '0 - 100',
            }),
            'poin_kontribusi': forms.NumberInput(attrs={
                'min': '0', 'max': '100', 'step': '0.01',
                'placeholder': '0 - 100',
            }),
            'catatan': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Catatan tambahan (opsional)',
            }),
        }
        labels = {
            'poin_keaktifan': 'Poin Keaktifan',
            'poin_kontribusi': 'Poin Kontribusi',
        }

    def clean(self):
        cleaned = super().clean()
        for field_name in ['poin_keaktifan', 'poin_kontribusi']:
            val = cleaned.get(field_name)
            if val is None:
                self.add_error(field_name, 'Poin wajib diisi.')
            elif val < Decimal('0') or val > Decimal('100'):
                self.add_error(field_name, 'Poin harus antara 0 dan 100.')
        return cleaned


class PenetapanKelulusanForm(forms.Form):
    """Form untuk admin menetapkan passing grade."""

    passing_grade = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        widget=forms.NumberInput(attrs={
            'min': '0', 'max': '100', 'step': '0.01',
            'placeholder': 'Contoh: 60.00',
        }),
        label='Passing Grade (Batas Minimum Total Akhir)',
    )
