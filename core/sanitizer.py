"""Sanitasi HTML untuk konten kaya yang dirender dengan filter ``|safe``.

Tujuan: mencegah stored XSS pada konten CKEditor (mis. ``Berita.konten_final``)
TANPA membuang format yang sah — heading, bold/italic, list, tabel, warna,
rata teks, gambar, dan link tetap dipertahankan.

DESAIN FAIL-SAFE (penting agar tidak merusak sistem yang sudah berjalan):
  1. Bila library ``nh3`` BELUM terpasang, fungsi mengembalikan HTML apa
     adanya — perilaku identik dengan sebelum patch. Jadi men-deploy kode
     ini tanpa ``nh3`` tidak mengubah/merusak apa pun. Untuk MENGAKTIFKAN
     proteksi: ``pip install nh3`` lalu restart Gunicorn.
  2. Bila proses sanitasi melempar error tak terduga, konten dikembalikan
     apa adanya juga (tidak pernah lebih buruk dari kondisi saat ini),
     supaya fitur publish berita tidak pernah gagal karenanya.

nh3 dibangun di atas ammonia (Rust): menghapus ``<script>``, ``<iframe>``,
atribut event handler (``onclick`` dll.), dan URL berskema ``javascript:``.
"""
import logging

logger = logging.getLogger(__name__)

# Tag yang boleh membawa atribut ``style``/``class`` — dipakai CKEditor 5
# untuk rata teks (text-align), warna (color/background-color), dan ukuran
# font. Tanpa mengizinkan ini, format konten lama akan hilang.
_STYLABLE_TAGS = {
    'p', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'blockquote', 'pre', 'code', 'ul', 'ol', 'li',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption',
    'figure', 'figcaption', 'img', 'a',
    'strong', 'em', 'b', 'i', 'u', 's',
}

# Seluruh tag yang diizinkan = tag stylable + tag tanpa style.
_ALLOWED_TAGS = _STYLABLE_TAGS | {
    'br', 'hr', 'sub', 'sup', 'strike', 'del', 'ins',
    'oembed', 'label', 'input',
}


def _build_allowed_attributes() -> dict:
    """Bangun peta tag -> set atribut yang diizinkan."""
    attrs = {tag: {'class', 'style'} for tag in _STYLABLE_TAGS}
    # 'rel' TIDAK didaftarkan di sini: nh3 mengelolanya otomatis lewat
    # parameter link_rel di sanitize_html (mendaftarkan keduanya = error).
    attrs['a'] |= {'href', 'title', 'target'}
    attrs['img'] |= {'src', 'alt', 'width', 'height'}
    attrs['td'] |= {'colspan', 'rowspan'}
    attrs['th'] |= {'colspan', 'rowspan', 'scope'}
    # Media embed CKEditor disimpan sebagai <oembed url="...">.
    attrs['oembed'] = {'url'}
    # Checkbox pada to-do list (selalu non-interaktif: disabled).
    attrs['input'] = {'type', 'checked', 'disabled'}
    return attrs


_ALLOWED_ATTRIBUTES = _build_allowed_attributes()


def sanitize_html(html):
    """Kembalikan versi ``html`` yang aman dirender dengan ``|safe``.

    Aman dipanggil dengan ``None``/``''`` (dikembalikan apa adanya).
    """
    if not html:
        return html

    try:
        import nh3
    except ImportError:
        logger.warning(
            'nh3 belum terpasang — konten HTML TIDAK disanitasi. '
            'Aktifkan proteksi XSS dengan: pip install nh3'
        )
        return html

    try:
        return nh3.clean(
            html,
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRIBUTES,
            link_rel='noopener noreferrer nofollow',
        )
    except Exception:
        logger.exception('Sanitasi HTML gagal; konten dikembalikan apa adanya.')
        return html
