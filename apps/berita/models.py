"""Berita model (Skripsi Tabel 3.7)."""
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django_ckeditor_5.fields import CKEditor5Field

from core.constants import KategoriBerita, StatusBerita


class Berita(models.Model):
    """Artikel berita PK IMM FTIK UMKO."""

    id_berita = models.AutoField(primary_key=True)
    id_penulis = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='id_penulis',
        related_name='berita_list',
    )
    judul = models.CharField(max_length=200)
    slug = models.SlugField(max_length=210, unique=True, blank=True)
    kategori = models.CharField(max_length=20, choices=KategoriBerita.choices)
    konten_draft = CKEditor5Field('Konten Draft', config_name='default')
    konten_final = CKEditor5Field('Konten Final', config_name='default', blank=True)
    saran_ai = models.TextField(null=True, blank=True)
    gambar_utama = models.ImageField(upload_to='berita/')
    status = models.CharField(
        max_length=20,
        choices=StatusBerita.choices,
        default=StatusBerita.DRAFT,
    )
    jumlah_views = models.IntegerField(default=0)
    tgl_dibuat = models.DateTimeField(auto_now_add=True)
    tgl_terbit = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'berita'
        verbose_name = 'Berita'
        verbose_name_plural = 'Berita'
        ordering = ['-tgl_dibuat']

    def __str__(self) -> str:
        return self.judul

    def save(self, *args, **kwargs) -> None:
        """Auto-generate slug dari judul + sanitasi konten HTML (anti-XSS).

        Sanitasi dilakukan di level model agar SEMUA jalur simpan (form
        penulis, koreksi AI, admin, shell) ikut terlindungi. Fail-safe:
        bila nh3 belum terpasang, konten dikembalikan apa adanya.
        """
        from core.sanitizer import sanitize_html
        if self.konten_draft:
            self.konten_draft = sanitize_html(self.konten_draft)
        if self.konten_final:
            self.konten_final = sanitize_html(self.konten_final)
        if not self.slug:
            base_slug = slugify(self.judul)
            slug = base_slug
            counter = 1
            while Berita.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def publish(self) -> None:
        """Set status menjadi published dan catat tanggal terbit."""
        self.status = StatusBerita.PUBLISHED
        self.tgl_terbit = timezone.now()
        if not self.konten_final:
            self.konten_final = self.konten_draft
        self.save()

    def increment_views(self) -> None:
        """Tambah jumlah views sebanyak 1."""
        self.jumlah_views += 1
        self.save(update_fields=['jumlah_views'])


class KataSambutan(models.Model):
    """Kata sambutan ketua umum untuk ditampilkan di beranda."""

    nama = models.CharField(max_length=100)
    jabatan = models.CharField(max_length=100, default='Ketua Umum PK IMM FTIK UMKO')
    foto = models.ImageField(upload_to='sambutan/')
    kata_sambutan = models.TextField()
    periode = models.CharField(max_length=20, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kata_sambutan'
        verbose_name = 'Kata Sambutan'
        verbose_name_plural = 'Kata Sambutan'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"Sambutan — {self.nama}"

    def save(self, *args, **kwargs) -> None:
        """Sanitasi HTML kata sambutan (CKEditor) sebelum simpan — anti-XSS."""
        from core.sanitizer import sanitize_html
        if self.kata_sambutan:
            self.kata_sambutan = sanitize_html(self.kata_sambutan)
        super().save(*args, **kwargs)


class VisiMisi(models.Model):
    """Visi dan misi organisasi."""

    visi = models.TextField()
    misi = models.TextField(help_text='Pisahkan setiap poin misi dengan baris baru')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'visi_misi'
        verbose_name = 'Visi & Misi'
        verbose_name_plural = 'Visi & Misi'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"Visi & Misi ({'Aktif' if self.is_active else 'Nonaktif'})"

    def save(self, *args, **kwargs) -> None:
        """Sanitasi HTML visi & misi (CKEditor) sebelum simpan — anti-XSS."""
        from core.sanitizer import sanitize_html
        if self.visi:
            self.visi = sanitize_html(self.visi)
        if self.misi:
            self.misi = sanitize_html(self.misi)
        super().save(*args, **kwargs)

    def get_misi_list(self) -> list:
        """Return misi sebagai list (split per baris)."""
        return [m.strip() for m in self.misi.split('\n') if m.strip()]


class Sejarah(models.Model):
    """Sejarah organisasi."""

    judul = models.CharField(max_length=200, default='Sejarah PK IMM FTIK UMKO')
    konten = models.TextField()
    gambar = models.ImageField(upload_to='sejarah/', blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sejarah'
        verbose_name = 'Sejarah'
        verbose_name_plural = 'Sejarah'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.judul

    def save(self, *args, **kwargs) -> None:
        """Sanitasi HTML konten (CKEditor) sebelum simpan — anti-XSS.

        Template ``profil/sejarah.html`` merender ``konten`` dengan ``|safe``,
        jadi konten wajib disanitasi seperti VisiMisi/KataSambutan/Berita.
        """
        from core.sanitizer import sanitize_html
        if self.konten:
            self.konten = sanitize_html(self.konten)
        super().save(*args, **kwargs)
