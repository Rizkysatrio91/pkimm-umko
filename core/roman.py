"""Konversi & pencocokan numeral Romawi ↔ Arab.

Dipakai agar penomoran BAB di dokumen (umumnya Romawi: "BAB II") tetap cocok
dengan ketikan user yang bebas (Arab "bab 2" atau Romawi "bab ii"), maupun
sebaliknya. Generik untuk dokumen apa pun — tidak ada hardcode AD/ART.

Dipakai oleh:
  - apps.chatbot.services (chunker PDF saat ingest)
  - apps.chatbot.views (pencarian keyword RAG)
"""

_ROMAN_MAP = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
_ROMAN_PAIRS = [
    (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
    (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
    (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'),
]


def roman_to_int(roman: str) -> int:
    """Konversi numeral Romawi → int. Return 0 kalau bukan Romawi valid."""
    roman = (roman or '').upper().strip()
    if not roman or not all(c in _ROMAN_MAP for c in roman):
        return 0
    total = 0
    prev = 0
    for c in reversed(roman):
        v = _ROMAN_MAP[c]
        total = total - v if v < prev else total + v
        prev = v
    return total


def int_to_roman(num: int) -> str:
    """Konversi int (1–3999) → numeral Romawi. Return '' kalau di luar rentang."""
    if num <= 0 or num >= 4000:
        return ''
    parts = []
    for value, sym in _ROMAN_PAIRS:
        while num >= value:
            parts.append(sym)
            num -= value
    return ''.join(parts)


def bab_number_variants(token: str) -> set[str]:
    """Hasilkan semua bentuk setara (huruf kecil) dari satu nomor BAB.

    Contoh:
      "2"   → {"2", "ii"}
      "ii"  → {"ii", "2"}
      "IV"  → {"iv", "4"}

    Dengan ini pencarian "bab 2" tetap menemukan dokumen yang menulis
    "BAB II", dan sebaliknya — tanpa peduli gaya penomoran dokumen sumber.
    """
    token = (token or '').strip()
    if not token:
        return set()
    variants = {token.lower()}
    if token.isdigit():
        roman = int_to_roman(int(token))
        if roman:
            variants.add(roman.lower())
    else:
        n = roman_to_int(token)
        if n:
            variants.add(str(n))
    return variants
