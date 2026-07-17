"""Gerbang validasi naskah sebelum dikirim ke Editor AI (koreksi PUEBI).

LATAR BELAKANG (temuan uji):
  - Naskah berbahasa asing dahulu ikut DITERJEMAHKAN oleh AI dan hasilnya
    dilabeli sebagai koreksi "[PUEBI]". Padahal penerjemahan bukan ranah PUEBI
    (PUEBI mengatur ejaan, bukan alih bahasa) dan menulis ulang isi melanggar
    aturan anti-halusinasi milik prompt itu sendiri.
  - Potongan kode program lolos apa adanya dan justru disertifikasi
    "sudah memenuhi kaidah PUEBI" — klaim yang jelas keliru.

Pemeriksaan di modul ini DETERMINISTIK (tanpa memanggil AI): murah, cepat,
tidak memakai token, dan aturannya eksplisit sehingga mudah
dipertanggungjawabkan. Ini lapis pertama; prompt AI memiliki lapis kedua.
"""
import re

# Status hasil pemeriksaan naskah.
STATUS_OK = 'ok'
STATUS_BUKAN_NASKAH = 'bukan_naskah_berita'
STATUS_BUKAN_INDONESIA = 'bukan_bahasa_indonesia'

# Pola penanda KODE PROGRAM/SKRIP (bukan prosa berita). Sengaja dipilih pola
# yang spesifik agar naskah berita normal tidak salah tolak.
_POLA_KODE = (
    re.compile(r'<\s*/?\s*script\b', re.I),
    re.compile(r'</?\s*(?:iframe|object|embed)\b', re.I),
    re.compile(r'\bfunction\s*\w*\s*\([^)]*\)\s*\{'),
    re.compile(r'=>\s*\{'),
    re.compile(r'\b(?:var|let|const)\s+\w+\s*='),
    re.compile(r'\b(?:alert|eval|confirm)\s*\('),
    re.compile(r'\bconsole\s*\.\s*log\s*\('),
    re.compile(r'\bdocument\s*\.\s*(?:cookie|write|location|getElementById|querySelector)'),
    re.compile(r'\bwindow\s*\.\s*(?:location|open)\b'),
    re.compile(r'\bon(?:error|load|click|mouseover)\s*=', re.I),
)

# Kata fungsi bahasa Indonesia yang praktis selalu muncul di prosa apa pun.
# Dipakai mengukur "ke-Indonesia-an" teks tanpa perlu library deteksi bahasa.
_KATA_FUNGSI_ID = frozenset({
    'yang', 'dan', 'di', 'ke', 'dari', 'untuk', 'dengan', 'pada', 'adalah',
    'ini', 'itu', 'dalam', 'akan', 'tidak', 'oleh', 'para', 'telah', 'dapat',
    'sebagai', 'juga', 'atau', 'karena', 'agar', 'saat', 'serta', 'sudah',
    'bahwa', 'ada', 'kami', 'kita', 'mereka', 'tersebut', 'lebih', 'hanya',
    'bisa', 'saya', 'anda', 'setelah', 'antara', 'hingga', 'ketika', 'sebuah',
})

# Teks sepanjang >= _MIN_KATA baru dinilai ke-Indonesia-annya, supaya kalimat
# pendek yang wajar (mis. "Rapat panitia berjalan lancar.") tidak salah tolak.
_MIN_KATA = 12

# Ambang konservatif: prosa Indonesia normal biasanya 15-30% kata fungsi,
# jauh di atas 6%. Teks Inggris praktis 0%.
_AMBANG_RASIO_ID = 0.06

_ENTITY = (
    ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'"),
    ('&apos;', "'"), ('&nbsp;', ' '), ('&amp;', '&'),
)


def _decode_entity(teks: str) -> str:
    """Decode entity HTML dasar.

    WAJIB dilakukan: CKEditor menyimpan skrip yang diketik user dalam bentuk
    ter-escape (``&lt;script&gt;``), sehingga tanpa decode pola kode tidak akan
    pernah cocok.
    """
    for entity, char in _ENTITY:
        teks = teks.replace(entity, char)
    return teks


def html_ke_teks(html: str) -> str:
    """Buang tag HTML lalu decode entity dasar → teks polos."""
    teks = re.sub(r'<[^>]+>', ' ', html or '')
    return re.sub(r'\s+', ' ', _decode_entity(teks)).strip()


def periksa_naskah(html: str) -> tuple:
    """Periksa apakah naskah layak disunting Editor AI.

    Return ``(status, pesan)``. ``status == STATUS_OK`` berarti lolos dan
    ``pesan`` kosong; selain itu ``pesan`` berisi alasan ramah-pengguna.
    """
    # Pemeriksaan kode dijalankan pada HTML MENTAH (setelah decode entity) agar
    # payload yang bersembunyi di dalam atribut tag — mis. ``<img onerror=...>``
    # — ikut tertangkap; atribut akan hilang bila tag lebih dulu dibuang.
    mentah = _decode_entity(html or '')
    for pola in _POLA_KODE:
        if pola.search(mentah):
            return (
                STATUS_BUKAN_NASKAH,
                'Konten terdeteksi berisi kode program atau skrip, bukan naskah '
                'berita. Fitur koreksi hanya untuk naskah berita berbahasa '
                'Indonesia.',
            )

    teks = html_ke_teks(html)
    if not teks:
        return STATUS_BUKAN_NASKAH, 'Naskah kosong atau tidak berisi teks.'

    kata = re.findall(r"[a-zA-Z']+", teks.lower())
    if len(kata) >= _MIN_KATA:
        rasio = sum(1 for k in kata if k in _KATA_FUNGSI_ID) / len(kata)
        if rasio < _AMBANG_RASIO_ID:
            return (
                STATUS_BUKAN_INDONESIA,
                'Naskah terdeteksi bukan berbahasa Indonesia. Fitur ini hanya '
                'menyunting naskah berita berbahasa Indonesia sesuai kaidah '
                'PUEBI. Silakan tulis naskah dalam bahasa Indonesia.',
            )

    return STATUS_OK, ''
