#!/usr/bin/env python
"""Utilitas command-line Django untuk tugas administratif."""
import os
import sys


def main():
    """Jalankan tugas administratif."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Tidak dapat mengimpor Django. Pastikan Django sudah terinstal dan "
            "tersedia di variabel environment PYTHONPATH Anda. Apakah Anda lupa "
            "mengaktifkan virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
