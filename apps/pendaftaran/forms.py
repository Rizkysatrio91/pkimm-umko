"""Form untuk app pendaftaran."""
from django import forms

from apps.accounts.models import User
from apps.pendaftaran.models import KelompokDAD, PeriodeDAD, RundownDAD
from core.constants import UserRole


class PendaftaranForm(forms.Form):
    """Form konfirmasi pendaftaran DAD. Data diambil dari biodata."""
    konfirmasi = forms.BooleanField(
        required=True,
        label='Saya menyatakan data biodata saya sudah benar dan lengkap'
    )


class PeriodeDADForm(forms.ModelForm):
    """Form untuk admin mengelola periode pendaftaran DAD dengan jadwal per tahap."""

    DT_INPUT = {
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-maroon/20 focus:border-maroon',
        'type': 'datetime-local',
    }
    DT_FORMAT = '%Y-%m-%dT%H:%M'

    class Meta:
        model = PeriodeDAD
        fields = [
            'nama_periode',
            'tgl_buka_administrasi', 'tgl_tutup_administrasi',
            'tgl_mulai_interview', 'tgl_selesai_interview',
            'tgl_mulai_kegiatan', 'tgl_selesai_kegiatan',
            'tgl_pengumuman_kelulusan',
            'is_active',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dt_attrs = self.DT_INPUT.copy()
        dt_format = self.DT_FORMAT

        self.fields['nama_periode'].widget = forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-maroon/20 focus:border-maroon',
            'placeholder': 'Contoh: DAD Periode 1 - 2026',
        })
        self.fields['is_active'].widget = forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-maroon border-gray-300 rounded focus:ring-maroon',
        })

        dt_fields = [
            'tgl_buka_administrasi', 'tgl_tutup_administrasi',
            'tgl_mulai_interview', 'tgl_selesai_interview',
            'tgl_mulai_kegiatan', 'tgl_selesai_kegiatan',
            'tgl_pengumuman_kelulusan',
        ]
        for name in dt_fields:
            self.fields[name].widget = forms.DateTimeInput(attrs=dt_attrs.copy(), format=dt_format)
            self.fields[name].input_formats = [dt_format]

    def clean(self):
        cleaned = super().clean()
        buka_adm = cleaned.get('tgl_buka_administrasi')
        tutup_adm = cleaned.get('tgl_tutup_administrasi')
        mulai_itv = cleaned.get('tgl_mulai_interview')
        selesai_itv = cleaned.get('tgl_selesai_interview')
        mulai_keg = cleaned.get('tgl_mulai_kegiatan')
        selesai_keg = cleaned.get('tgl_selesai_kegiatan')
        tgl_lulus = cleaned.get('tgl_pengumuman_kelulusan')

        errors = []
        if buka_adm and tutup_adm and tutup_adm <= buka_adm:
            errors.append('Tanggal tutup administrasi harus setelah tanggal buka.')
        if mulai_itv and selesai_itv and selesai_itv <= mulai_itv:
            errors.append('Tanggal selesai interview harus setelah tanggal mulai.')
        if mulai_itv and tutup_adm and mulai_itv < tutup_adm:
            errors.append('Interview harus dimulai setelah administrasi ditutup.')
        if mulai_keg and selesai_keg:
            if selesai_keg <= mulai_keg:
                errors.append('Tanggal selesai kegiatan harus setelah tanggal mulai.')
            else:
                selisih_hari = (selesai_keg.date() - mulai_keg.date()).days
                if selisih_hari != 2:
                    errors.append(
                        'Rentang Tahap Kegiatan DAD harus tepat 3 hari kalender '
                        f'(Hari 1, 2, 3 berturut-turut). Saat ini: {selisih_hari + 1} hari '
                        f'({mulai_keg.date():%d %b %Y} sampai {selesai_keg.date():%d %b %Y}).'
                    )
        if mulai_keg and selesai_itv and mulai_keg < selesai_itv:
            errors.append('Kegiatan DAD harus dimulai setelah interview selesai.')
        if tgl_lulus and selesai_keg and tgl_lulus < selesai_keg:
            errors.append('Pengumuman kelulusan harus setelah kegiatan selesai.')
        if errors:
            raise forms.ValidationError(errors)

        # Hanya boleh ada satu periode aktif dalam satu waktu
        if cleaned.get('is_active'):
            qs = PeriodeDAD.objects.filter(is_active=True)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Sudah ada periode aktif lain. Nonaktifkan dulu sebelum mengaktifkan yang baru.')
        return cleaned


# ═══════════════════════════════════════════════════════════════════════════════
# Kelompok DAD Forms
# ═══════════════════════════════════════════════════════════════════════════════

INPUT_CSS = 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-maroon/20 focus:border-maroon'


class KelompokPJForm(forms.Form):
    """Assign PJ panitia ke kelompok."""

    id_pj = forms.ModelChoiceField(
        queryset=User.objects.filter(role=UserRole.PANITIA, is_active=True),
        label='Penanggung Jawab (Panitia)',
        required=False,
        empty_label='— Belum ditentukan —',
        widget=forms.Select(attrs={'class': INPUT_CSS}),
    )


class KelompokPindahForm(forms.Form):
    """Pindah peserta ke kelompok lain."""

    id_kelompok = forms.ModelChoiceField(
        queryset=KelompokDAD.objects.none(),
        label='Kelompok Tujuan',
        widget=forms.Select(attrs={'class': INPUT_CSS}),
    )

    def __init__(self, *args, periode=None, exclude_kelompok=None, **kwargs):
        super().__init__(*args, **kwargs)
        if periode:
            qs = KelompokDAD.objects.filter(id_periode=periode)
            if exclude_kelompok:
                qs = qs.exclude(pk=exclude_kelompok.pk)
            self.fields['id_kelompok'].queryset = qs


# ═══════════════════════════════════════════════════════════════════════════════
# Rundown DAD Form
# ═══════════════════════════════════════════════════════════════════════════════

class RundownDADForm(forms.ModelForm):
    """CRUD form untuk sesi rundown DAD."""

    class Meta:
        model = RundownDAD
        fields = [
            'hari_ke', 'tanggal', 'jam_mulai', 'jam_selesai', 'materi',
            'pemateri_a', 'pemateri_b', 'pemateri_c',
            'pj_a', 'pj_b', 'pj_c',
            'is_absensi', 'urutan',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = INPUT_CSS
        self.fields['hari_ke'].widget = forms.TextInput(attrs={
            'class': css,
            'placeholder': 'Kedatangan / Hari 1 / Hari 2 / Hari 3',
            'maxlength': 30,
        })
        # HTML5 date/time input hanya menampilkan value jika formatnya YYYY-MM-DD / HH:MM.
        # Tanpa format eksplisit, Django merender format lokal sehingga field tampil kosong saat edit.
        self.fields['tanggal'].widget = forms.DateInput(
            attrs={'class': css, 'type': 'date'}, format='%Y-%m-%d')
        self.fields['jam_mulai'].widget = forms.TimeInput(
            attrs={'class': css, 'type': 'time'}, format='%H:%M')
        self.fields['jam_selesai'].widget = forms.TimeInput(
            attrs={'class': css, 'type': 'time'}, format='%H:%M')
        self.fields['materi'].widget = forms.TextInput(attrs={'class': css, 'placeholder': 'Nama materi / kegiatan'})
        self.fields['urutan'].widget = forms.NumberInput(attrs={'class': css, 'min': 0})
        self.fields['is_absensi'].widget = forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-maroon border-gray-300 rounded focus:ring-maroon',
        })
        for field_name in ('pemateri_a', 'pemateri_b', 'pemateri_c', 'pj_a', 'pj_b', 'pj_c'):
            self.fields[field_name].widget = forms.TextInput(attrs={
                'class': css,
                'placeholder': 'Nama pemateri / PJ',
            })
