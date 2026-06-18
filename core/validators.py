"""Validator bersama untuk upload file.

Mencegah user mengunggah file yang terlalu besar atau tipe file yang
berisiko (SVG dengan script, HTML polyglot, dsb.). Dipakai oleh form
di apps.accounts, apps.berita, apps.kader.
"""
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

# Ukuran maksimal upload gambar — 5 MB cukup untuk foto HP modern
# yang sudah di-kompres; lebih dari itu biasanya tanda salah upload.
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024

# Content-type allowlist. SVG dan GIF tidak diizinkan karena SVG bisa
# berisi <script> dan GIF tidak dipakai sistem ini.
ALLOWED_IMAGE_CONTENT_TYPES = frozenset({
    'image/jpeg',
    'image/png',
    'image/webp',
})

# Extension allowlist (case-insensitive) — dicek bila content_type
# tidak tersedia (mis. dari admin shell).
ALLOWED_IMAGE_EXTENSIONS = frozenset({'jpg', 'jpeg', 'png', 'webp'})


def validate_image_upload(uploaded_file):
    """Validasi ukuran + tipe file untuk ImageField.

    Raise ValidationError dengan pesan bahasa Indonesia yang ramah user
    kalau file terlalu besar atau ekstensinya tidak diizinkan.

    Dipanggil dari form.clean_<field>() yang menangani ImageField.
    Aman dipanggil dengan None/empty (return tanpa error).
    """
    if not uploaded_file:
        return

    # Hanya validasi file yang BARU di-upload user. Saat edit tanpa
    # mengganti gambar, yang masuk adalah FieldFile lama yang sudah
    # tersimpan di DB — mengakses .size-nya memicu storage lookup
    # (os.path.getsize) yang melempar FileNotFoundError bila file fisiknya
    # hilang (mis. media tidak ikut ter-deploy), menyebabkan 500.
    if not isinstance(uploaded_file, UploadedFile):
        return

    size = getattr(uploaded_file, 'size', None)
    if size is not None and size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(
            f'Ukuran file maksimal 5 MB. File Anda berukuran '
            f'{size / (1024 * 1024):.1f} MB.'
        )

    content_type = getattr(uploaded_file, 'content_type', None)
    if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ValidationError(
            'Hanya file JPG, PNG, atau WEBP yang diperbolehkan.'
        )

    # Cek ekstensi sebagai pertahanan tambahan (content-type bisa dipalsukan)
    name = getattr(uploaded_file, 'name', '') or ''
    if name and '.' in name:
        ext = name.rsplit('.', 1)[-1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValidationError(
                'Hanya file JPG, PNG, atau WEBP yang diperbolehkan.'
            )
