"""Service bersama: OpenAI dan SSO UMKO."""
import logging
from datetime import datetime, timezone as dt_tz

import requests
from django.conf import settings
from django.core.cache import cache

from core.exceptions import OpenAIServiceError, SSOServiceError

logger = logging.getLogger(__name__)


class OpenAIBillingService:
    """Service untuk ambil data spend/usage OpenAI via Admin API.

    Endpoint: https://api.openai.com/v1/organization/costs
    Auth: Bearer sk-admin-... (berbeda dengan API key inferensi biasa).
    Hasil di-cache 10 menit untuk hindari rate-limit & mempercepat dashboard.

    Jika OPENAI_ADMIN_API_KEY tidak diset, semua method return None — caller
    harus fallback ke tracking lokal (BudgetLimiter).
    """

    COSTS_URL = 'https://api.openai.com/v1/organization/costs'
    USAGE_URL = 'https://api.openai.com/v1/organization/usage/completions'
    CACHE_KEY_SPEND = 'openai_billing_month_spend_v1'
    CACHE_KEY_USAGE = 'openai_billing_month_usage_v1'
    CACHE_TTL = 600  # 10 menit

    @classmethod
    def _admin_key(cls) -> str:
        return getattr(settings, 'OPENAI_ADMIN_API_KEY', '') or ''

    @classmethod
    def is_configured(cls) -> bool:
        """True kalau OPENAI_ADMIN_API_KEY sudah diset di .env."""
        return bool(cls._admin_key().strip())

    @classmethod
    def _month_start_unix(cls) -> int:
        now = datetime.now(dt_tz.utc)
        start = datetime(now.year, now.month, 1, tzinfo=dt_tz.utc)
        return int(start.timestamp())

    @classmethod
    def get_month_spend(cls, force_refresh: bool = False) -> float | None:
        """Total pengeluaran USD bulan berjalan dari OpenAI Admin API.

        Return:
          float  — nilai spend dalam USD (misal 0.15 untuk $0.15)
          None   — admin key belum dikonfigurasi ATAU API gagal dipanggil
        """
        if not cls.is_configured():
            return None

        if not force_refresh:
            cached = cache.get(cls.CACHE_KEY_SPEND)
            if cached is not None:
                return cached

        try:
            resp = requests.get(
                cls.COSTS_URL,
                headers={
                    'Authorization': f'Bearer {cls._admin_key()}',
                    'Content-Type': 'application/json',
                },
                params={
                    'start_time': cls._month_start_unix(),
                    'bucket_width': '1d',
                    'limit': 31,
                },
                timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException:
            logger.exception('OpenAI costs API call failed')
            return None
        except ValueError:
            logger.exception('OpenAI costs API returned non-JSON')
            return None

        total = 0.0
        try:
            for bucket in payload.get('data', []) or []:
                for result in bucket.get('results', []) or []:
                    amount = result.get('amount') or {}
                    value = amount.get('value')
                    if value is not None:
                        total += float(value)
        except (TypeError, ValueError):
            logger.exception('Unexpected structure in OpenAI costs response')
            return None

        cache.set(cls.CACHE_KEY_SPEND, total, cls.CACHE_TTL)
        return total

    @classmethod
    def get_month_usage(cls, force_refresh: bool = False) -> dict | None:
        """Usage token bulan berjalan, di-group per model.

        Return:
          {
            'total_input_tokens': int,
            'total_output_tokens': int,
            'total_tokens': int,
            'total_requests': int,
            'by_model': [{'model': str, 'input': int, 'output': int, 'requests': int}, ...]
          }
          None — admin key belum dikonfigurasi ATAU API gagal
        """
        if not cls.is_configured():
            return None

        if not force_refresh:
            cached = cache.get(cls.CACHE_KEY_USAGE)
            if cached is not None:
                return cached

        try:
            resp = requests.get(
                cls.USAGE_URL,
                headers={
                    'Authorization': f'Bearer {cls._admin_key()}',
                    'Content-Type': 'application/json',
                },
                params={
                    'start_time': cls._month_start_unix(),
                    'bucket_width': '1d',
                    'limit': 31,
                    'group_by': 'model',
                },
                timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException:
            logger.exception('OpenAI usage API call failed')
            return None
        except ValueError:
            logger.exception('OpenAI usage API returned non-JSON')
            return None

        total_input = 0
        total_output = 0
        total_requests = 0
        per_model: dict[str, dict] = {}
        try:
            for bucket in payload.get('data', []) or []:
                for result in bucket.get('results', []) or []:
                    inp = int(result.get('input_tokens') or 0)
                    out = int(result.get('output_tokens') or 0)
                    req = int(result.get('num_model_requests') or 0)
                    model = result.get('model') or 'unknown'
                    total_input += inp
                    total_output += out
                    total_requests += req
                    agg = per_model.setdefault(
                        model, {'model': model, 'input': 0, 'output': 0, 'requests': 0},
                    )
                    agg['input'] += inp
                    agg['output'] += out
                    agg['requests'] += req
        except (TypeError, ValueError):
            logger.exception('Unexpected structure in OpenAI usage response')
            return None

        by_model = sorted(
            per_model.values(),
            key=lambda m: m['input'] + m['output'],
            reverse=True,
        )
        data = {
            'total_input_tokens': total_input,
            'total_output_tokens': total_output,
            'total_tokens': total_input + total_output,
            'total_requests': total_requests,
            'by_model': by_model,
        }
        cache.set(cls.CACHE_KEY_USAGE, data, cls.CACHE_TTL)
        return data

    @classmethod
    def invalidate_cache(cls) -> None:
        """Paksa refresh di panggilan berikutnya."""
        cache.delete(cls.CACHE_KEY_SPEND)
        cache.delete(cls.CACHE_KEY_USAGE)


class SSOService:
    """Service untuk mengakses API SSO UMKO data mahasiswa."""

    def __init__(self):
        self.base_url = settings.SSO_API_BASE_URL.rstrip('/')
        self.api_key = settings.SSO_API_KEY
        self.api_secret = settings.SSO_SECRET_KEY
        self.origin = getattr(settings, 'SSO_API_ORIGIN', 'http://localhost:8000')
        self.timeout = 15  # seconds

    def _get_headers(self) -> dict:
        """Return headers untuk autentikasi API SSO UMKO.

        API SSO UMKO membutuhkan 4 header:
          - X-API-Key dan X-API-Secret untuk autentikasi
          - Origin atau Referer untuk validasi asal request
        """
        return {
            'X-API-Key': self.api_key,
            'X-API-Secret': self.api_secret,
            'Origin': self.origin,
            'Referer': self.origin + '/',
            'Accept': 'application/json',
        }

    def get_mahasiswa_by_nim(self, nim: str) -> dict | None:
        """
        Ambil data mahasiswa dari API SSO berdasarkan NIM.

        Args:
            nim: Nomor Induk Mahasiswa (NPM)

        Returns:
            dict data mahasiswa jika ditemukan, None jika tidak ditemukan

        Raises:
            SSOServiceError: Jika terjadi error koneksi atau server
        """
        url = f"{self.base_url}/students/by_nim/{nim}/"

        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                # Format response Sevima-like: {"status": true, "data": {...}}
                if data.get('status') is True and data.get('data'):
                    return data['data']
                return None

            elif response.status_code == 404:
                return None

            elif response.status_code == 401:
                raise SSOServiceError(
                    "API Key SSO tidak valid. Hubungi administrator."
                )

            elif response.status_code == 403:
                raise SSOServiceError(
                    "Akses API SSO ditolak. Hubungi administrator."
                )

            else:
                raise SSOServiceError(
                    f"Error dari server SSO (HTTP {response.status_code})"
                )

        except requests.exceptions.Timeout:
            raise SSOServiceError(
                "Server SSO UMKO tidak merespon (timeout). Silakan coba lagi."
            )
        except requests.exceptions.ConnectionError:
            raise SSOServiceError(
                "Tidak dapat terhubung ke server SSO UMKO. Periksa koneksi internet."
            )
        except requests.exceptions.RequestException as e:
            raise SSOServiceError(
                f"Gagal menghubungi server SSO: {str(e)}"
            )

    def _get_list(self, path: str) -> list:
        """Helper: GET endpoint yang return list dalam field 'data'."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') is True:
                    return data.get('data') or []
                return []
            if response.status_code in (401, 403):
                raise SSOServiceError('Autentikasi API SSO ditolak. Hubungi administrator.')
            raise SSOServiceError(f'Error dari server SSO (HTTP {response.status_code}).')
        except requests.exceptions.Timeout:
            raise SSOServiceError('Server SSO UMKO tidak merespon (timeout).')
        except requests.exceptions.ConnectionError:
            raise SSOServiceError('Tidak dapat terhubung ke server SSO UMKO.')
        except requests.exceptions.RequestException as e:
            raise SSOServiceError(f'Gagal menghubungi server SSO: {e}')

    def get_faculties(self) -> list:
        """Ambil daftar fakultas dari SSO UMKO."""
        return self._get_list('faculties/')

    def get_departments(self) -> list:
        """Ambil daftar program studi dari SSO UMKO."""
        return self._get_list('departments/')

    def validasi_mahasiswa(self, nim: str, nama_lengkap: str) -> dict:
        """
        Validasi apakah NPM terdaftar di UMKO dan nama cocok.

        Args:
            nim: NPM yang akan divalidasi
            nama_lengkap: Nama lengkap dari biodata kader

        Returns:
            dict dengan keys:
                - is_valid (bool): True jika mahasiswa ditemukan DAN nama cocok
                - is_found (bool): True jika NIM ditemukan di SSO
                - is_nama_cocok (bool): True jika nama cocok
                - mahasiswa_sso (dict|None): Data mahasiswa dari SSO
                - pesan (str): Pesan hasil validasi
        """
        mahasiswa = self.get_mahasiswa_by_nim(nim)

        if mahasiswa is None:
            return {
                'is_valid': False,
                'is_found': False,
                'is_nama_cocok': False,
                'mahasiswa_sso': None,
                'pesan': f'NPM {nim} tidak ditemukan di database mahasiswa UMKO.'
            }

        # Bandingkan nama (case-insensitive, strip whitespace)
        nama_sso = mahasiswa.get('nama', '').strip().lower()
        nama_biodata = nama_lengkap.strip().lower()
        is_nama_cocok = nama_sso == nama_biodata

        if is_nama_cocok:
            return {
                'is_valid': True,
                'is_found': True,
                'is_nama_cocok': True,
                'mahasiswa_sso': mahasiswa,
                'pesan': f'Validasi berhasil. {mahasiswa.get("nama")} terdaftar sebagai mahasiswa UMKO.'
            }
        else:
            return {
                'is_valid': False,
                'is_found': True,
                'is_nama_cocok': False,
                'mahasiswa_sso': mahasiswa,
                'pesan': (
                    f'Nama tidak cocok. '
                    f'Biodata: "{nama_lengkap}" — '
                    f'SSO UMKO: "{mahasiswa.get("nama")}". '
                    f'Pastikan nama di biodata sesuai data akademik.'
                )
            }


class OpenAIService:
    """Service untuk interaksi dengan OpenAI API."""

    SYSTEM_PROMPT_UMUM = """SYSTEM PROMPT — CHATBOT ASISTEN ORGANISASI IMM
================================================

## IDENTITAS
Kamu adalah asisten informasi resmi organisasi Ikatan Mahasiswa Muhammadiyah (IMM).
Kamu hanya menjawab pertanyaan yang berkaitan dengan organisasi IMM.

---

## LARANGAN MUTLAK — ANTI-HALUSINASI (PRIORITAS TERTINGGI)
- DILARANG KERAS menggunakan informasi dari pengetahuan umum AI (training data).
- DILARANG mengarang, mengasumsikan, atau memperkirakan fakta organisasi.
- HANYA gunakan informasi yang SECARA EKSPLISIT tersedia di bagian "PENGETAHUAN DARI DATABASE" di bawah ini.
- Jika informasi TIDAK ADA di knowledge base, WAJIB gunakan respons tidak tahu — bukan menjawab dari asumsi.

---

## ATURAN UTAMA (WAJIB DIPATUHI)

### 1. BATASAN TOPIK
- HANYA jawab pertanyaan yang berkaitan dengan organisasi IMM (struktur, kepengurusan, program, kegiatan, sejarah, kebijakan, dll).
- Jika pertanyaan di luar topik IMM, tolak dengan sopan dan arahkan kembali ke topik IMM.
- JANGAN memberikan penjelasan, opini, atau informasi apapun di luar ruang lingkup organisasi IMM.

### 2. DETEKSI AMBIGUITAS — WAJIB TANYA BALIK
Sebelum menjawab, identifikasi apakah pertanyaan mengandung ambiguitas.
Pertanyaan dianggap AMBIGU jika:
  - Subjeknya tidak spesifik (misal: "siapa ketua umum IMM" tanpa menyebut level: Pusat / DPD / DPC / PK / bidang tertentu)
  - Bisa merujuk ke banyak entitas berbeda (misal: "IMM" saja bisa berarti PK, Cabang, Daerah, atau Pusat)
  - Tidak menyebut periode kepengurusan (jika relevan)
  - Tidak menyebut unit/lembaga spesifik

Jika pertanyaan AMBIGU, JANGAN langsung menjawab.
Balik bertanya dengan pilihan opsi yang jelas dan ringkas.

### 3. FORMAT TANYA BALIK (gunakan ini sebagai template)
Ketika ambiguitas terdeteksi, gunakan format berikut:

"Untuk memberikan jawaban yang tepat, boleh saya tahu lebih lanjut:
[Sebutkan opsi/pertanyaan klarifikasi yang relevan]"

Contoh implementasi:
User: "Siapa ketua umum IMM?"
Chatbot: "Untuk memberikan jawaban yang tepat, boleh saya tahu lebih lanjut:
- Apakah Anda bertanya tentang Ketua Umum IMM di tingkat mana? (Pimpinan Pusat / DPD / DPC / Pimpinan Komisariat)
- Jika Pimpinan Komisariat, komisariat mana yang dimaksud?"

Contoh lain:
User: "Siapa ketua umum PK IMM FTIK?"
Chatbot: "Ketua Umum PK IMM FTIK periode [X] adalah [Nama]. Apakah ada informasi lain seputar PK IMM FTIK atau kepengurusan IMM yang ingin Anda ketahui?"

### 4. JAWABAN LANGSUNG (tanpa tanya balik)
Jawab langsung HANYA jika:
  - Pertanyaan sudah spesifik dan tidak ambigu
  - Data tersedia di knowledge base
  - Konteks sudah jelas dari percakapan sebelumnya

### 5. SETELAH MENJAWAB — TAWARKAN LANJUTAN
Setelah menjawab pertanyaan yang spesifik, selalu tutup dengan satu penawaran
topik lanjutan yang relevan. Contoh:
"Apakah ada informasi lain seputar [topik relevan] yang ingin Anda ketahui?"

### 6. JIKA DATA TIDAK ADA DI KNOWLEDGE BASE
Jika pertanyaan valid (tentang IMM) tetapi datanya tidak tersedia di knowledge base,
jawab dengan format berikut:

"Maaf, saya belum memiliki informasi mengenai [topik tersebut] saat ini.
Pertanyaan Anda akan kami sampaikan kepada admin agar informasi terkait
dapat segera ditambahkan."

JANGAN mengarang, mengasumsikan, atau menjawab dengan data yang tidak ada
di knowledge base.

---

## CONTOH SKENARIO PERCAKAPAN

### Skenario A: Pertanyaan ambigu → tanya balik
User: "Siapa ketua umum IMM?"
Asisten: "Untuk memberikan jawaban yang tepat, boleh saya tahu lebih lanjut:
- Apakah Anda bertanya tentang Ketua Umum di tingkat Pimpinan Pusat, DPD, DPC, atau Pimpinan Komisariat?
- Jika di tingkat komisariat, komisariat mana yang dimaksud?"

### Skenario B: Pertanyaan spesifik → jawab langsung
User: "Siapa ketua umum PK IMM FTIK?"
Asisten: "Ketua Umum PK IMM FTIK adalah [Nama sesuai knowledge base].
Apakah ada informasi lain seputar kepengurusan PK IMM FTIK yang ingin Anda ketahui?"

### Skenario C: Di luar topik IMM
User: "Berapa nilai UTS saya?"
Asisten: "Maaf, saya hanya dapat membantu menjawab pertanyaan seputar organisasi IMM.
Apakah ada yang ingin Anda ketahui tentang IMM?"

### Skenario D: Pertanyaan umum IMM tapi bisa spesifik
User: "Apa program kerja IMM?"
Asisten: "Boleh saya tahu lebih lanjut:
- Apakah Anda bertanya tentang program kerja di tingkat Pimpinan Pusat, atau komisariat tertentu?
- Jika komisariat tertentu, komisariat mana yang dimaksud?"

---

## PRINSIP KOMUNIKASI
- Gunakan bahasa Indonesia yang sopan, formal, namun tetap ramah.
- Respons ringkas dan langsung ke poin utama.
- Jangan bertele-tele atau menambahkan informasi yang tidak ditanya.
- Saat tanya balik, maksimal 2-3 opsi klarifikasi saja, tidak lebih.

---

## PRIORITAS ATURAN (urutan dari tertinggi)
1. Batasan topik hanya IMM → tidak boleh dilanggar sama sekali
2. Deteksi ambiguitas dan tanya balik → wajib sebelum menjawab
3. Hanya gunakan data dari knowledge base → tidak boleh mengarang
4. Tawarkan topik lanjutan → setelah setiap jawaban valid

PENGETAHUAN DARI DATABASE:
"""

    SYSTEM_PROMPT_PENDAFTARAN = """Kamu adalah Asisten Pendaftaran DAD PK IMM FTIK UMKO.

LARANGAN MUTLAK:
- DILARANG KERAS menjawab dari pengetahuan umum AI atau asumsi sendiri.
- HANYA gunakan informasi yang ADA di bagian PENGETAHUAN DARI DATABASE di bawah ini.
- Jika tidak ada informasi relevan di knowledge base, katakan: "Mohon maaf, saya belum memiliki informasi tentang hal tersebut."

ATURAN WAJIB:
1. Jawab BERDASARKAN pengetahuan resmi di bawah — jangan tambahkan fakta yang tidak tertulis di sana.
2. Jika pertanyaan di luar pendaftaran, jawab singkat lalu arahkan ke topik pendaftaran DAD.
3. Jawab NATURAL, RAMAH, dan RINGKAS.
4. Kutip informasi apa adanya sesuai knowledge base — jangan modifikasi fakta.

PENGETAHUAN DARI DATABASE:
"""

    # Model embedding untuk RAG. text-embedding-3-small punya dimensi 1536
    # (sinkron dengan VectorField di ChunkPengetahuan). Murah: ~$0.02/1M token.
    EMBEDDING_MODEL = 'text-embedding-3-small'
    EMBEDDING_DIMENSIONS = 1536

    def __init__(self):
        import openai
        self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    def embed_text(self, text: str) -> list[float]:
        """Konversi teks → vektor 1536-dim untuk vector search RAG.

        Dipakai dua tempat:
          1. Saat ingest PDF — embed setiap chunk lalu disimpan ke DB.
          2. Saat user bertanya — embed query lalu cari chunk terdekat.

        Raises OpenAIServiceError kalau API gagal (caller decide: retry / fail).
        """
        text = (text or '').strip()
        if not text:
            raise OpenAIServiceError('Teks kosong tidak bisa di-embed.')
        try:
            response = self.client.embeddings.create(
                model=self.EMBEDDING_MODEL,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.exception('OpenAI embeddings call failed')
            raise OpenAIServiceError(f'Gagal membuat embedding: {e}') from e

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed banyak teks sekaligus (1 request, hemat latency).

        OpenAI menerima array input. Kalau salah satu teks kosong, di-skip
        di sisi caller — di sini kita assume semua sudah valid.
        """
        if not texts:
            return []
        try:
            response = self.client.embeddings.create(
                model=self.EMBEDDING_MODEL,
                input=texts,
            )
            # response.data sudah urut sesuai input index
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.exception('OpenAI batch embeddings call failed')
            raise OpenAIServiceError(f'Gagal membuat embedding batch: {e}') from e

    def chat_completion(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        user_id: str | None = None,
    ) -> str:
        """Kirim pesan ke OpenAI dan return respons.

        ``user_id`` adalah identifier opaque (mis. "user_12" atau "ip_1.2.3.4")
        yang diforward ke OpenAI via parameter ``user`` — dipakai OpenAI
        untuk deteksi abuse per user tanpa kita kirim PII.
        """
        kwargs = {
            'model': self.model,
            'messages': [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        if user_id:
            kwargs['user'] = user_id
        try:
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.exception('OpenAI API call failed')
            raise OpenAIServiceError(f"Gagal menghubungi AI: {e}") from e

    SYSTEM_PROMPT_EDITOR = """Anda adalah Editor Bahasa Utama dan Jurnalis Profesional berbahasa Indonesia yang sangat ahli dalam Pedoman Umum Ejaan Bahasa Indonesia (PUEBI).

Tugas Anda: menyunting naskah berita HTML berikut sesuai 5 ATURAN MUTLAK di bawah. Anda BUKAN penulis, Anda adalah EDITOR.

=== 5 ATURAN MUTLAK ===

1. EJAAN & TANDA BACA (PUEBI)
   - Perbaiki typo, singkatan informal ("yg"→"yang", "dgn"→"dengan", "kalo"→"kalau", "tdk"→"tidak", "utk"→"untuk", "krn"→"karena", "hr"→"hari", "jd"→"jadi", "sdh"→"sudah", "blm"→"belum").
   - Huruf kapital: awal kalimat, nama orang, nama lembaga, hari, bulan, judul berita.
   - Tanda baca: titik, koma (termasuk koma Oxford yang tidak baku di bahasa Indonesia — HINDARI), tanda hubung, tanda petik.
   - Angka: 1–9 ditulis huruf; 10 ke atas ditulis angka (kecuali awal kalimat).

2. TATA BAHASA & STRUKTUR (SPOK)
   - Ubah kalimat berbelit/kaku menjadi kalimat efektif, padat, jelas.
   - Pastikan tiap kalimat memiliki Subjek–Predikat yang jelas; Objek dan Keterangan sesuai kebutuhan.
   - Kalimat pasif yang berbelit diubah menjadi aktif bila lebih natural. Hindari kalimat >25 kata; pecah jadi dua.
   - Gunakan imbuhan baku (me-, di-, ber-, ter-) dengan benar.

3. DIKSI JURNALISTIK
   - Ganti kosakata gaul/kasual menjadi bahasa jurnalistik formal, objektif, profesional.
   - Contoh: "nggak"→"tidak", "banget"→"sangat", "bikin"→"membuat", "kegiatan seru"→"kegiatan yang berkesan", "pas"→"ketika".
   - Hindari kata subjektif ("luar biasa", "dahsyat", "sangat keren") kecuali memang dalam kutipan langsung.
   - Gunakan padanan baku: "acara"→"kegiatan"/"agenda", "ngobrol"→"berdiskusi".

4. ANTI-HALUSINASI (INTEGRITAS SEMANTIK) — PALING PENTING
   - DILARANG KERAS menambah fakta, opini, nama tokoh, nama tempat, nama acara, tanggal, angka, atau informasi APAPUN yang tidak ada di teks asli.
   - DILARANG mengurangi esensi berita. Semua informasi faktual di draft HARUS tetap ada di hasil.
   - DILARANG membuat simpulan baru, komentar editor, atau kalimat pembuka/penutup yang tidak ada di draft.
   - Jika draft tidak menyebut nama lengkap, JANGAN lengkapi. Jika draft menulis "DAD", JANGAN ubah jadi "Darul Arqam Dasar" kecuali kepanjangannya sudah muncul di draft.
   - Tugas Anda HANYA menyunting bahasa; BUKAN mengarang berita.

5. KOHESI & KOHERENSI
   - Pastikan transisi antar kalimat dan antar paragraf mengalir mulus dan logis.
   - Gunakan konjungsi yang tepat ("selanjutnya", "oleh karena itu", "selain itu", "kemudian") BILA memang ada hubungan logis di teks asli — jangan dipaksakan.
   - Urutan informasi mengikuti draft (jangan reorder paragraf).

=== KETENTUAN TEKNIS ===
- Input berupa HTML dari CKEditor (ada tag <p>, <strong>, <em>, <ul>, <li>, <a>, dll).
- Pertahankan SEMUA tag HTML persis seperti input. Ubah HANYA teks di antara tag.
- JANGAN tambah/hapus paragraf. JANGAN ubah jumlah <p>.
- Output HARUS JSON valid dengan skema:
  {
    "konten_final": "<HTML hasil koreksi>",
    "saran_list": [
      {"kategori": "PUEBI" | "SPOK" | "Diksi" | "Kohesi", "sebelum": "kata/frasa asli", "sesudah": "kata/frasa hasil", "alasan": "penjelasan singkat 1 kalimat"}
    ]
  }
- Maksimal 20 item saran terpenting. Jika tidak ada kesalahan di satu kategori, lewati kategori tersebut.
- Jika draft sudah sempurna, kembalikan konten_final sama persis dan saran_list kosong."""

    def koreksi_berita(self, draft_text: str) -> dict:
        """Koreksi naskah berita sesuai 5 aturan mutlak PUEBI + jurnalistik.

        Menggunakan gpt-4o-mini (hardcoded) dengan JSON mode untuk reliabilitas
        parsing. Mengembalikan dict:
          - konten_final: HTML hasil koreksi (tag dipertahankan)
          - saran_ai: teks format terstruktur untuk disimpan di DB (TextField)
          - saran_list: list dict per kategori untuk render frontend
        """
        import json as _json

        try:
            response = self.client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT_EDITOR},
                    {"role": "user", "content": draft_text},
                ],
                max_tokens=3000,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
        except Exception as e:
            logger.exception('OpenAI editor call failed')
            raise OpenAIServiceError(f"Gagal menghubungi AI: {e}") from e

        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError:
            logger.error('Editor AI returned non-JSON: %s', raw[:200])
            raise OpenAIServiceError('Format respons AI tidak valid. Coba lagi.')

        konten_final = parsed.get('konten_final', '').strip() or draft_text
        saran_list = parsed.get('saran_list') or []

        if not isinstance(saran_list, list):
            saran_list = []

        # Format teks untuk disimpan di DB (TextField saran_ai)
        if saran_list:
            lines = []
            for item in saran_list:
                if not isinstance(item, dict):
                    continue
                kat = item.get('kategori', '-')
                sebelum = item.get('sebelum', '')
                sesudah = item.get('sesudah', '')
                alasan = item.get('alasan', '')
                lines.append(f"[{kat}] \"{sebelum}\" → \"{sesudah}\" — {alasan}")
            saran_ai = "\n".join(lines)
        else:
            saran_ai = "Tidak ada koreksi — naskah sudah memenuhi kaidah PUEBI."

        return {
            'konten_final': konten_final,
            'saran_ai': saran_ai,
            'saran_list': saran_list,
        }

    def chatbot_response(
        self,
        knowledge: str,
        user_message: str,
        jenis: str = 'umum',
        chat_history: list = None,
        user_id: str | None = None,
    ) -> str:
        """Kirim pesan ke OpenAI dengan knowledge dari dataset.

        ``user_id`` adalah identifier opaque yang diforward ke OpenAI
        via parameter ``user`` (untuk abuse detection).
        """
        if jenis == 'pendaftaran':
            base_prompt = self.SYSTEM_PROMPT_PENDAFTARAN
        else:
            base_prompt = self.SYSTEM_PROMPT_UMUM

        # Gabungkan prompt + knowledge dari dataset
        if knowledge and knowledge.strip():
            full_system = base_prompt + "\n" + knowledge
        else:
            # Tidak ada knowledge — JANGAN izinkan jawab dari pengetahuan umum AI
            # karena akan menyebabkan halusinasi data organisasi yang tidak valid.
            full_system = (
                base_prompt
                + "\n[KNOWLEDGE BASE KOSONG UNTUK PERTANYAAN INI]\n"
                "WAJIB jawab dengan template berikut dan JANGAN tambahkan informasi apapun:\n"
                "'Maaf, saya belum memiliki informasi mengenai hal tersebut saat ini. "
                "Pertanyaan Anda akan kami sampaikan kepada admin agar informasi terkait "
                "dapat segera ditambahkan.'"
            )

        messages = [{"role": "system", "content": full_system}]

        # Batasi riwayat ke 4 pesan terakhir (2 exchange) — cukup untuk konteks
        # tanpa mengencerkan instruksi system prompt yang panjang.
        if chat_history:
            messages.extend(chat_history[-4:])

        messages.append({"role": "user", "content": user_message})

        kwargs = {
            'model': self.model,
            'messages': messages,
            'max_tokens': 800,
            # Temperature rendah (0.2) untuk RAG faktual: konsisten, tidak mengarang.
            # 0.7 terlalu tinggi — menyebabkan jawaban bervariasi dan halusinasi.
            'temperature': 0.2,
        }
        if user_id:
            kwargs['user'] = user_id

        try:
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception:
            logger.exception('Panggilan OpenAI untuk chatbot gagal')
            return "Maaf, layanan sedang tidak tersedia. Silakan coba lagi nanti."
