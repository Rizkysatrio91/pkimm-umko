"""Service untuk ingest dokumen PDF ke chunk pengetahuan (RAG).

Alur:
  1. Parse PDF dengan PyMuPDF → list halaman (teks + nomor halaman)
  2. Cleaning: buang nomor halaman, header/footer berulang, normalisasi unicode
  3. Chunking section-aware (BAB/Pasal) — fallback ke sentence-based
  4. Embed tiap chunk → simpan ke ChunkPengetahuan

Di-design synchronous (admin tunggu di halaman upload). Untuk PDF 100 halaman
biasanya selesai 30-90 detik (kebanyakan waktu di OpenAI embeddings).
"""
import logging
import re
import unicodedata
from collections import Counter

import fitz  # PyMuPDF

from apps.chatbot.models import ChunkPengetahuan, DokumenPengetahuan, StatusDokumen
from core.exceptions import OpenAIServiceError
from core.services import OpenAIService

logger = logging.getLogger(__name__)


class PDFIngestService:
    """Pipeline ingest PDF → chunk + embedding."""

    # Maksimum karakter per chunk. ~500 token untuk teks Indonesia
    # (1 token ≈ 3-4 char untuk bahasa Indonesia).
    MAX_CHUNK_CHARS = 1500
    MIN_CHUNK_CHARS = 80  # chunk lebih pendek dari ini di-skip (terlalu noise)
    # Target ukuran chunk setelah merge — Pasal pendek (1-2 kalimat) digabung
    # hingga mencapai ukuran ini, supaya konteks-nya lebih kaya untuk vector
    # search. Tanpa merge, dokumen AD/ART jadi banyak chunk pendek (<200 char)
    # yang sulit di-match dengan embedding query pendek.
    TARGET_CHUNK_CHARS = 600

    # Regex section heading khas dokumen organisasi (AD/ART, panduan, dll).
    SECTION_PATTERNS = [
        re.compile(r'^\s*BAB\s+[IVXLCDM\d]+', re.IGNORECASE),
        re.compile(r'^\s*PASAL\s+\d+', re.IGNORECASE),
        re.compile(r'^\s*Pasal\s+\d+'),
        re.compile(r'^\s*Bab\s+[IVXLCDM\d]+'),
        re.compile(r'^\s*BAGIAN\s+[IVXLCDM\d]+', re.IGNORECASE),
    ]

    # ─── Public API ──────────────────────────────────────────────────────

    def ingest(self, dokumen: DokumenPengetahuan) -> int:
        """Proses 1 dokumen PDF jadi chunk + embedding. Return jumlah chunk.

        Update status dokumen sepanjang proses. Kalau gagal, status=failed
        dan error_message diisi (caller bisa tampilkan ke admin).
        """
        dokumen.status = StatusDokumen.PROCESSING
        dokumen.error_message = ''
        dokumen.save(update_fields=['status', 'error_message', 'updated_at'])

        # Hapus chunk lama (kalau re-ingest setelah edit).
        ChunkPengetahuan.objects.filter(id_dokumen=dokumen).delete()

        try:
            pages = self._parse_pdf(dokumen.file_pdf.path)
            if not pages:
                raise ValueError('PDF tidak mengandung teks yang bisa diekstrak.')

            cleaned = self._clean_pages(pages)
            full_text = '\n'.join(cleaned)
            chunks = self._chunk_text(full_text)

            if not chunks:
                raise ValueError('Setelah cleaning, tidak ada teks yang bisa dijadikan chunk.')

            # Embed dalam batch (1 request OpenAI per ~50 chunk untuk hemat latency).
            service = OpenAIService()
            embeddings: list[list[float]] = []
            BATCH_SIZE = 50
            for i in range(0, len(chunks), BATCH_SIZE):
                batch = [c['teks'] for c in chunks[i:i + BATCH_SIZE]]
                embeddings.extend(service.embed_batch(batch))

            # Bulk create chunk records.
            objs = [
                ChunkPengetahuan(
                    id_dokumen=dokumen,
                    urutan=i,
                    teks=c['teks'],
                    metadata_seksi=c['seksi'],
                    embedding=emb,
                )
                for i, (c, emb) in enumerate(zip(chunks, embeddings))
            ]
            ChunkPengetahuan.objects.bulk_create(objs)

            dokumen.jumlah_chunk = len(objs)
            dokumen.status = StatusDokumen.READY
            dokumen.save(update_fields=['jumlah_chunk', 'status', 'updated_at'])
            return len(objs)

        except OpenAIServiceError as e:
            dokumen.status = StatusDokumen.FAILED
            dokumen.error_message = f'OpenAI error: {e}'
            dokumen.save(update_fields=['status', 'error_message', 'updated_at'])
            raise
        except Exception as e:
            logger.exception('PDF ingest gagal untuk dokumen %s', dokumen.id_dokumen)
            dokumen.status = StatusDokumen.FAILED
            dokumen.error_message = str(e)[:500]
            dokumen.save(update_fields=['status', 'error_message', 'updated_at'])
            raise

    # ─── Step 1: parsing ─────────────────────────────────────────────────

    def _parse_pdf(self, path: str) -> list[str]:
        """Ekstrak teks per halaman. Return list[halaman_teks]."""
        doc = fitz.open(path)
        try:
            return [page.get_text('text') or '' for page in doc]
        finally:
            doc.close()

    # ─── Step 2: cleaning ────────────────────────────────────────────────

    def _clean_pages(self, pages: list[str]) -> list[str]:
        """Buang noise: nomor halaman, header/footer berulang, normalisasi.

        Strategi:
          1. Normalisasi unicode (NFKC) — perbaiki ligatures & non-breaking space
          2. Deteksi header/footer: baris yang muncul di ≥40% halaman
          3. Per-halaman: buang baris angka saja, baris daftar isi, baris noise
          4. Sambung baris yang terpotong (tanpa tanda baca akhir)
        """
        # Normalisasi tiap halaman.
        normalized = [unicodedata.normalize('NFKC', p) for p in pages]

        # Deteksi header/footer: ambil 2 baris pertama & 2 baris terakhir
        # tiap halaman, hitung frekuensinya. Yang muncul ≥40% halaman = noise.
        edge_lines = Counter()
        n_pages = len(normalized)
        for p in normalized:
            lines = [ln.strip() for ln in p.split('\n') if ln.strip()]
            if not lines:
                continue
            for ln in lines[:2] + lines[-2:]:
                # Hanya pertimbangkan baris pendek (header/footer biasanya pendek).
                if 3 <= len(ln) <= 80:
                    edge_lines[ln] += 1

        threshold = max(2, int(n_pages * 0.4))
        repeated = {ln for ln, count in edge_lines.items() if count >= threshold}

        cleaned_pages = []
        for raw in normalized:
            cleaned = self._clean_single_page(raw, repeated)
            if cleaned:
                cleaned_pages.append(cleaned)
        return cleaned_pages

    def _clean_single_page(self, page_text: str, repeated_lines: set) -> str:
        """Cleaning rule per halaman."""
        result_lines = []
        for raw_line in page_text.split('\n'):
            line = raw_line.strip()
            if not line:
                continue

            # Buang header/footer berulang.
            if line in repeated_lines:
                continue

            # Buang baris yang isinya HANYA angka (nomor halaman).
            if re.fullmatch(r'[\d\s\-–—\.]+', line):
                continue

            # Buang format "Page X of Y", "Halaman X", "- 5 -".
            if re.fullmatch(r'(page|halaman|hal\.?)\s*\d+(\s*(of|dari|/)\s*\d+)?',
                            line, re.IGNORECASE):
                continue
            if re.fullmatch(r'[-–—]\s*\d+\s*[-–—]', line):
                continue

            # Buang baris daftar isi: "BAB I PENDAHULUAN ........ 1"
            # atau "Pasal 1 ............................ 5"
            if re.search(r'\.{4,}\s*\d+\s*$', line):
                continue

            # Buang baris yang >50% bukan huruf/spasi (artefak tabel/gambar).
            letters = sum(1 for c in line if c.isalpha() or c.isspace())
            if len(line) >= 5 and letters / len(line) < 0.5:
                continue

            result_lines.append(line)

        # Sambung baris yang terpotong di tengah kalimat.
        # Heuristik: kalau baris sebelumnya tidak diakhiri tanda baca akhir
        # DAN baris berikutnya dimulai huruf kecil → sambung.
        merged = []
        for line in result_lines:
            if (merged
                    and not re.search(r'[\.\!\?:;]$', merged[-1])
                    and line and line[0].islower()):
                merged[-1] = merged[-1] + ' ' + line
            else:
                merged.append(line)

        return '\n'.join(merged)

    # ─── Step 3: chunking ────────────────────────────────────────────────

    def _chunk_text(self, full_text: str) -> list[dict]:
        """Section-aware chunking. Return list[{'teks': ..., 'seksi': ...}].

        Strategi:
          1. Split per BAB / PASAL (paling natural untuk dokumen IMM)
          2. Gabung Pasal-pasal pendek konsekutif jadi chunk yang lebih kaya
             konteks (target ~TARGET_CHUNK_CHARS) — penting untuk akurasi
             vector search saat query user pendek
          3. Kalau section panjang, split per paragraf
          4. Kalau dokumen tidak punya section, fallback ke split paragraf
        """
        sections = self._split_by_section(full_text)
        if not sections:
            sections = [{'teks': full_text, 'seksi': ''}]

        # Gabung section pendek (mis. tiap Pasal yg cuma 1-2 kalimat) supaya
        # konteks tiap chunk cukup kaya untuk vector search.
        sections = self._merge_short_sections(sections)

        chunks = []
        for sec in sections:
            teks = sec['teks'].strip()
            if not teks:
                continue
            if len(teks) <= self.MAX_CHUNK_CHARS:
                if len(teks) >= self.MIN_CHUNK_CHARS:
                    chunks.append({'teks': teks, 'seksi': sec['seksi']})
                continue
            # Section terlalu panjang — split per paragraf.
            for sub in self._split_long_section(teks):
                if len(sub) >= self.MIN_CHUNK_CHARS:
                    chunks.append({'teks': sub, 'seksi': sec['seksi']})
        return chunks

    def _merge_short_sections(self, sections: list[dict]) -> list[dict]:
        """Gabung section pendek konsekutif sampai mencapai TARGET_CHUNK_CHARS.

        Mempertahankan info seksi: kalau buffer berisi multiple section,
        seksi-nya jadi "{seksi_pertama} - {seksi_terakhir}". Section yang
        sudah cukup besar (>= TARGET) di-flush sendiri tanpa digabung.
        """
        if not sections:
            return []

        merged: list[dict] = []
        buf_teks = ''
        buf_seksi_first = ''
        buf_seksi_last = ''

        def flush() -> None:
            nonlocal buf_teks, buf_seksi_first, buf_seksi_last
            if not buf_teks:
                return
            seksi = buf_seksi_first
            if buf_seksi_last and buf_seksi_last != buf_seksi_first:
                seksi = f"{buf_seksi_first} – {buf_seksi_last}"
            merged.append({'teks': buf_teks, 'seksi': seksi})
            buf_teks = ''
            buf_seksi_first = ''
            buf_seksi_last = ''

        for sec in sections:
            teks = sec['teks'].strip()
            if not teks:
                continue
            seksi = sec.get('seksi', '')

            # Section yang sudah cukup besar — flush buffer dulu, lalu
            # tambahkan section ini sebagai entry sendiri.
            if len(teks) >= self.TARGET_CHUNK_CHARS:
                flush()
                merged.append({'teks': teks, 'seksi': seksi})
                continue

            # Section pendek — append ke buffer.
            if not buf_teks:
                buf_teks = teks
                buf_seksi_first = seksi
                buf_seksi_last = seksi
            else:
                buf_teks = f"{buf_teks}\n\n{teks}"
                buf_seksi_last = seksi

            if len(buf_teks) >= self.TARGET_CHUNK_CHARS:
                flush()

        flush()
        return merged

    def _split_by_section(self, text: str) -> list[dict]:
        """Pecah teks berdasar heading BAB/PASAL.

        Menjaga heading sebagai bagian dari section berikutnya, supaya AI tahu
        konteks-nya. Return [] kalau tidak ada heading sama sekali.
        """
        lines = text.split('\n')
        sections: list[dict] = []
        current_seksi = ''
        current_lines: list[str] = []

        def is_section_heading(line: str) -> bool:
            stripped = line.strip()
            if not stripped or len(stripped) > 100:
                return False
            return any(p.match(stripped) for p in self.SECTION_PATTERNS)

        for line in lines:
            if is_section_heading(line):
                # Tutup section sebelumnya.
                if current_lines:
                    sections.append({
                        'teks': '\n'.join(current_lines).strip(),
                        'seksi': current_seksi,
                    })
                current_seksi = line.strip()[:200]
                current_lines = [line]
            else:
                current_lines.append(line)

        # Tutup section terakhir.
        if current_lines:
            sections.append({
                'teks': '\n'.join(current_lines).strip(),
                'seksi': current_seksi,
            })

        # Kalau cuma 1 section dan tidak ada seksi terdeteksi, anggap tidak
        # ada struktur — return [] supaya caller pakai fallback.
        if len(sections) == 1 and not sections[0]['seksi']:
            return []
        return sections

    def _split_long_section(self, text: str) -> list[str]:
        """Split section panjang per paragraf, gabung sampai mendekati MAX."""
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        if not paragraphs:
            # Tidak ada paragraf jelas — pecah per kalimat.
            paragraphs = [s.strip() for s in re.split(r'(?<=[\.\!\?])\s+', text) if s.strip()]

        chunks = []
        buf = ''
        for para in paragraphs:
            if len(para) > self.MAX_CHUNK_CHARS:
                # Paragraf terlalu panjang — paksa pecah per kalimat.
                if buf:
                    chunks.append(buf.strip())
                    buf = ''
                sentences = [s.strip() for s in re.split(r'(?<=[\.\!\?])\s+', para) if s.strip()]
                for s in sentences:
                    if len(buf) + len(s) + 1 > self.MAX_CHUNK_CHARS and buf:
                        chunks.append(buf.strip())
                        buf = s
                    else:
                        buf = (buf + ' ' + s) if buf else s
                continue

            if len(buf) + len(para) + 2 > self.MAX_CHUNK_CHARS and buf:
                chunks.append(buf.strip())
                buf = para
            else:
                buf = (buf + '\n\n' + para) if buf else para

        if buf.strip():
            chunks.append(buf.strip())
        return chunks
