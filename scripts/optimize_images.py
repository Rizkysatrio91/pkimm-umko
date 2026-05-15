"""
Batch optimize gambar di media/ dan static/images/.

Aturan:
- Resize: lebar > 1600 px → kecilkan ke 1600 px (jaga aspek rasio).
  Khusus logo (ada kata 'logo' di nama file): max 800 px (sudah jauh dari cukup).
- JPEG: re-encode quality 85, optimize, progressive.
- PNG: re-encode quality 85 → JPEG kalau opaque, atau tetap PNG dengan optimize.
  Khusus logo dengan transparency: tetap PNG (transparan).
- WebP sibling: generate file .webp quality 80 di samping file asli.
- Backup: kalau folder backup tidak ada, dibuat di {root}_backup/.
- Skip file yang sudah < 100 KB (sudah optimal).

Jalankan dari root project: python scripts/optimize_images.py
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from PIL import Image

# Threshold ukuran file: di bawah ini, skip (sudah optimal)
SKIP_BELOW_BYTES = 100 * 1024  # 100 KB
# Max width default
MAX_WIDTH = 1600
MAX_WIDTH_LOGO = 800

JPEG_QUALITY = 85
WEBP_QUALITY = 80
PNG_OPTIMIZE = True

ROOTS = ["media", "static/images"]
IMG_EXT = {".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG"}


def is_logo(path: Path) -> bool:
    return "logo" in path.name.lower()


def kb(n_bytes: int) -> str:
    if n_bytes < 1024:
        return f"{n_bytes} B"
    if n_bytes < 1024 * 1024:
        return f"{n_bytes/1024:.1f} KB"
    return f"{n_bytes/1024/1024:.2f} MB"


def backup_path(src: Path) -> Path:
    """media/foo.jpg → media_backup/foo.jpg, static/images/x.png → static_backup/images/x.png"""
    parts = src.parts
    root = parts[0]
    rest = parts[1:]
    backup_root = f"{root}_backup"
    return Path(backup_root, *rest)


def has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)


def process_image(src: Path, dry_run: bool = False) -> dict:
    """Return stats dict."""
    orig_size = src.stat().st_size
    stat = {
        "src": str(src),
        "orig": orig_size,
        "skipped": False,
        "skip_reason": "",
        "new_jpeg": None,
        "new_webp": None,
    }

    if orig_size < SKIP_BELOW_BYTES:
        stat["skipped"] = True
        stat["skip_reason"] = f"sudah kecil ({kb(orig_size)})"
        return stat

    try:
        img = Image.open(src)
    except Exception as e:
        stat["skipped"] = True
        stat["skip_reason"] = f"tidak bisa dibuka: {e}"
        return stat

    # Tentukan max width
    max_w = MAX_WIDTH_LOGO if is_logo(src) else MAX_WIDTH

    # Resize jika perlu
    if img.width > max_w:
        ratio = max_w / img.width
        new_h = int(img.height * ratio)
        img_proc = img.resize((max_w, new_h), Image.LANCZOS)
    else:
        img_proc = img.copy()

    # Tentukan format output
    ext_lower = src.suffix.lower()
    keep_png = ext_lower == ".png" and has_alpha(img_proc)

    if dry_run:
        return stat

    # Backup original sebelum overwrite
    bkp = backup_path(src)
    bkp.parent.mkdir(parents=True, exist_ok=True)
    if not bkp.exists():
        shutil.copy2(src, bkp)

    # Re-encode in place
    try:
        if keep_png:
            # PNG dengan transparency: keep PNG, optimize
            # Konversi P (palette) → RGBA untuk konsistensi
            if img_proc.mode == "P":
                img_proc = img_proc.convert("RGBA")
            img_proc.save(src, "PNG", optimize=PNG_OPTIMIZE)
        else:
            # Convert ke RGB (drop alpha kalau ada — wajib untuk JPEG)
            if img_proc.mode != "RGB":
                # PNG opaque tanpa alpha → convert to RGB
                if has_alpha(img_proc):
                    bg = Image.new("RGB", img_proc.size, (255, 255, 255))
                    bg.paste(img_proc, mask=img_proc.split()[-1] if img_proc.mode in ("RGBA", "LA") else None)
                    img_proc = bg
                else:
                    img_proc = img_proc.convert("RGB")
            # Save sebagai JPEG (overwrite original, even if originally PNG)
            # Tapi: kalau original PNG dan tidak ada alpha, kita TIDAK ubah extension
            # supaya path lama tidak rusak. Save as JPEG dengan ext PNG (browser tidak care).
            # Lebih aman: save sebagai JPEG ke extension asli.
            if ext_lower == ".png":
                # Save sebagai PNG saja dengan optimize (browser load PNG fine)
                img_proc.save(src, "PNG", optimize=PNG_OPTIMIZE)
            else:
                img_proc.save(src, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        stat["new_jpeg"] = src.stat().st_size

        # Generate WebP sibling
        webp_path = src.with_suffix(src.suffix + ".webp") if False else src.with_suffix(".webp")
        # Pakai .with_suffix biasa supaya foo.jpg → foo.webp
        webp_path = src.with_suffix(".webp")
        # Untuk WebP, pakai img_proc (yang sudah di-resize)
        img_for_webp = img_proc
        if img_for_webp.mode == "P":
            img_for_webp = img_for_webp.convert("RGBA")
        img_for_webp.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
        stat["new_webp"] = webp_path.stat().st_size

    except Exception as e:
        stat["skipped"] = True
        stat["skip_reason"] = f"error saat save: {e}"
        return stat

    return stat


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Hanya tampilkan plan, tidak ubah file")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    print(f"Working dir: {project_root}")
    print(f"Dry run: {args.dry_run}")
    print(f"Settings: JPEG q{JPEG_QUALITY}, WebP q{WEBP_QUALITY}, max width {MAX_WIDTH}px (logo {MAX_WIDTH_LOGO}px)")
    print()

    files = []
    for root in ROOTS:
        root_path = project_root / root
        if not root_path.exists():
            continue
        for ext in IMG_EXT:
            files.extend(root_path.rglob(f"*{ext}"))
    # Unique + sort by size desc
    files = sorted(set(files), key=lambda p: p.stat().st_size, reverse=True)
    print(f"Total candidate file: {len(files)}")
    print()

    total_orig = 0
    total_new = 0
    total_webp = 0
    skipped = []
    processed = []

    for f in files:
        rel = f.relative_to(project_root)
        stat = process_image(f, dry_run=args.dry_run)
        if stat["skipped"]:
            skipped.append((rel, stat["skip_reason"]))
            continue
        total_orig += stat["orig"]
        if stat["new_jpeg"]:
            total_new += stat["new_jpeg"]
        if stat["new_webp"]:
            total_webp += stat["new_webp"]
        processed.append((rel, stat))
        new_jpeg_str = kb(stat["new_jpeg"]) if stat["new_jpeg"] else "-"
        new_webp_str = kb(stat["new_webp"]) if stat["new_webp"] else "-"
        print(f"  {kb(stat['orig']):>10} → {new_jpeg_str:>10} | webp {new_webp_str:>10}  {rel}")

    print()
    print("=" * 70)
    print(f"Processed: {len(processed)} file")
    print(f"Skipped:   {len(skipped)} file")
    if skipped:
        for rel, reason in skipped:
            print(f"  SKIP: {rel} ({reason})")
    print()
    print(f"Total ORIGINAL (sebelum):    {kb(total_orig)}")
    print(f"Total JPEG/PNG (re-encoded): {kb(total_new)}  (reduksi {(1-total_new/total_orig)*100:.1f}%)")
    print(f"Total WebP (sibling):        {kb(total_webp)}  (reduksi {(1-total_webp/total_orig)*100:.1f}%)")
    print()
    print("Backup original ada di: media_backup/, static_backup/")


if __name__ == "__main__":
    main()
