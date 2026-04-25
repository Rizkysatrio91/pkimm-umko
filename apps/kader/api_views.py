"""API views untuk app kader."""
from datetime import datetime

from django.http import JsonResponse
from django.views import View

from apps.kader.models import KonfigurasiSistem, ProgramStudi
from core.exceptions import SSOServiceError
from core.services import SSOService



class SSOLookupView(View):
    """API: ambil data mahasiswa dari SSO UMKO berdasarkan NPM untuk autofill form kader.

    Hanya boleh dipanggil oleh admin yang sudah login.
    GET /api/sso-mahasiswa/?npm=<npm>
    Response JSON: {nama, program_studi, fakultas, angkatan, tempat_lahir,
                    tgl_lahir, jenis_kelamin, no_hp, alamat, status_mahasiswa}
    """

    def get(self, request):
        if not request.user.is_authenticated or request.user.role != 'admin':
            return JsonResponse({'error': 'Akses ditolak.'}, status=403)

        npm = request.GET.get('npm', '').strip()
        if not npm:
            return JsonResponse({'error': 'Parameter npm diperlukan.'}, status=400)

        try:
            sso = SSOService()
            mhs = sso.get_mahasiswa_by_nim(npm)
        except SSOServiceError as e:
            return JsonResponse({'error': str(e)}, status=503)

        if not mhs:
            return JsonResponse(
                {'error': f'Mahasiswa dengan NPM {npm} tidak ditemukan di SSO UMKO.'},
                status=404,
            )

        konfig = KonfigurasiSistem.get_instance()

        # ── Cocokkan program studi ke database lokal via word-overlap scoring ─────
        # SSO dan DB lokal sering berbeda: "Sistem dan Teknologi Informasi" vs
        # "Sistem Teknologi Informasi". Hitung irisan kata utama untuk match terbaik.
        prodi_sso = (mhs.get('program_studi') or '').strip()
        prodi_local = ''
        fak_local   = ''

        STOP_WORDS = {'dan', 'atau', 'the', 'of', 'ilmu', 's1', 's2', 'd3', 'd4'}

        def _kata_utama(s: str) -> set:
            return {w for w in s.lower().split() if w not in STOP_WORDS and len(w) > 1}

        if prodi_sso:
            kata_sso = _kata_utama(prodi_sso)
            best_obj, best_score = None, 0.0

            for p in ProgramStudi.objects.filter(is_active=True).select_related('fakultas'):
                kata_db = _kata_utama(p.nama_prodi)
                if not kata_db:
                    continue
                irisan = kata_sso & kata_db
                # Skor: rasio kata yang cocok terhadap set yang lebih besar
                score = len(irisan) / max(len(kata_sso), len(kata_db), 1)
                if score > best_score:
                    best_score = score
                    best_obj = p

            # Ambil jika minimal 50% kata cocok
            if best_obj and best_score >= 0.5:
                prodi_local = best_obj.nama_prodi
                fak_local   = best_obj.fakultas.nama_fakultas

        # Fallback: konfigurasi untuk fakultas, nilai SSO untuk prodi
        if not fak_local:
            fak_local = konfig.sso_nama_fakultas or ''
        if not prodi_local:
            prodi_local = prodi_sso

        # ── Angkatan dari SSO ────────────────────────────────────────────────────
        angkatan = str(mhs.get('angkatan') or mhs.get('tahun_masuk') or mhs.get('tahun_angkatan') or '')

        # ── Normalisasi tanggal lahir → YYYY-MM-DD ───────────────────────────────
        tgl_lahir = ''
        raw_tgl = str(mhs.get('tanggal_lahir') or mhs.get('tgl_lahir') or '')[:10]
        if raw_tgl:
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    tgl_lahir = datetime.strptime(raw_tgl, fmt).strftime('%Y-%m-%d')
                    break
                except ValueError:
                    continue

        # ── Normalisasi jenis kelamin → L / P ───────────────────────────────────
        jk_raw = (mhs.get('jenis_kelamin') or '').strip().upper()
        if jk_raw in ('L', 'LAKI-LAKI', 'LAKI', 'MALE', 'M'):
            jenis_kelamin = 'L'
        elif jk_raw in ('P', 'PEREMPUAN', 'WANITA', 'FEMALE', 'F'):
            jenis_kelamin = 'P'
        else:
            jenis_kelamin = ''

        return JsonResponse({
            'nama':             mhs.get('nama') or mhs.get('nama_lengkap') or '',
            'program_studi':    prodi_local,
            'fakultas':         fak_local,
            'angkatan':         angkatan,
            'tempat_lahir':     mhs.get('tempat_lahir') or '',
            'tgl_lahir':        tgl_lahir,
            'jenis_kelamin':    jenis_kelamin,
            'no_hp':            mhs.get('hp') or mhs.get('no_hp') or '',
            'alamat':           mhs.get('alamat_domisili') or mhs.get('alamat') or '',
            'status_mahasiswa': mhs.get('status_mahasiswa') or '',
        })


class ProdiByFakultasView(View):
    """API: return daftar prodi aktif berdasarkan fakultas_id atau fakultas_nama."""

    def get(self, request):
        fakultas_id = request.GET.get('fakultas_id')
        fakultas_nama = request.GET.get('fakultas_nama')

        filters = {'is_active': True}
        if fakultas_id:
            filters['fakultas_id'] = fakultas_id
        elif fakultas_nama:
            filters['fakultas__nama_fakultas'] = fakultas_nama
        else:
            return JsonResponse([], safe=False)

        prodi_qs = ProgramStudi.objects.filter(**filters).values(
            'id_prodi', 'nama_prodi',
        )
        return JsonResponse(list(prodi_qs), safe=False)
