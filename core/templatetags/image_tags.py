"""
Template tags untuk render <picture> dengan WebP source + fallback.
Usage:
    {% load image_tags %}
    {% picture obj.foto alt="Foto Profil" classes="w-32 h-32 rounded-full" loading="lazy" %}
    {% picture_static "images/logo_AI.png" alt="AI Assistant" classes="w-16 h-16" %}
"""
import os
from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe
from django.utils.html import escape

register = template.Library()


def _webp_url_from_url(url: str) -> str:
    base, _ext = os.path.splitext(url)
    return base + ".webp"


def _webp_file_exists(url: str, root: str) -> bool:
    """Cek apakah file .webp sibling ada di disk."""
    rel = url.lstrip("/")
    if rel.startswith(settings.MEDIA_URL.lstrip("/")):
        rel = rel[len(settings.MEDIA_URL.lstrip("/")):]
        full = os.path.join(settings.MEDIA_ROOT, rel)
    elif settings.STATIC_URL and rel.startswith(settings.STATIC_URL.lstrip("/")):
        rel = rel[len(settings.STATIC_URL.lstrip("/")):]
        full = os.path.join(root, rel)
    else:
        full = os.path.join(root, rel)
    base, _ext = os.path.splitext(full)
    return os.path.exists(base + ".webp")


@register.simple_tag
def picture(image_field, alt="", classes="", loading="lazy", fetchpriority=""):
    """
    Render <picture> dari ImageField/FileField.
    Otomatis pakai .webp sibling kalau ada di MEDIA_ROOT.
    """
    if not image_field:
        return ""
    try:
        url = image_field.url
    except (ValueError, AttributeError):
        return ""

    attrs = []
    if loading:
        attrs.append(f'loading="{escape(loading)}"')
    if fetchpriority:
        attrs.append(f'fetchpriority="{escape(fetchpriority)}"')
    if classes:
        attrs.append(f'class="{escape(classes)}"')
    attrs.append(f'alt="{escape(alt)}"')
    attrs_str = " ".join(attrs)

    if _webp_file_exists(url, settings.MEDIA_ROOT):
        webp_url = _webp_url_from_url(url)
        return mark_safe(
            f'<picture>'
            f'<source type="image/webp" srcset="{escape(webp_url)}">'
            f'<img src="{escape(url)}" {attrs_str}>'
            f'</picture>'
        )
    return mark_safe(f'<img src="{escape(url)}" {attrs_str}>')


@register.simple_tag
def picture_static(static_path, alt="", classes="", loading="lazy", fetchpriority=""):
    """
    Render <picture> dari path static (relatif dari STATIC_ROOT).
    Otomatis pakai .webp sibling kalau ada di STATICFILES_DIRS atau STATIC_ROOT.
    Contoh: {% picture_static "images/logo_AI.png" alt="AI" %}
    """
    if not static_path:
        return ""

    url = static(static_path)
    attrs = []
    if loading:
        attrs.append(f'loading="{escape(loading)}"')
    if fetchpriority:
        attrs.append(f'fetchpriority="{escape(fetchpriority)}"')
    if classes:
        attrs.append(f'class="{escape(classes)}"')
    attrs.append(f'alt="{escape(alt)}"')
    attrs_str = " ".join(attrs)

    # Cari file di STATICFILES_DIRS dulu (dev), lalu STATIC_ROOT (prod)
    roots_to_check = list(getattr(settings, "STATICFILES_DIRS", []))
    if hasattr(settings, "STATIC_ROOT") and settings.STATIC_ROOT:
        roots_to_check.append(settings.STATIC_ROOT)

    webp_exists = False
    for root in roots_to_check:
        candidate = os.path.join(root, static_path)
        base, _ = os.path.splitext(candidate)
        if os.path.exists(base + ".webp"):
            webp_exists = True
            break

    if webp_exists:
        webp_url = _webp_url_from_url(url)
        return mark_safe(
            f'<picture>'
            f'<source type="image/webp" srcset="{escape(webp_url)}">'
            f'<img src="{escape(url)}" {attrs_str}>'
            f'</picture>'
        )
    return mark_safe(f'<img src="{escape(url)}" {attrs_str}>')
