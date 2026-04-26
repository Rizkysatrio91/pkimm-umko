"""Service layer: template Word → PDF (docx2pdf) + Excel (openpyxl)."""
import os
import tempfile
from io import BytesIO

import openpyxl
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from django.conf import settings
from django.utils import timezone
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

NAMA_BULAN = [
    'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
    'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',
]

DOCX_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
PDF_TYPE  = 'application/pdf'


class LaporanService:
    """Generate laporan dari template Word → PDF/DOCX + Excel."""

    TEMPLATE_PATH = os.path.join(
        settings.BASE_DIR, 'templates', 'laporan_template', 'Template_Laporan.docx'
    )

    # ══════════════════════════════════════════════════════════════
    # Helper placeholder
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def _replace_in_paragraphs(cls, paragraphs, ph: str, value: str):
        """Ganti placeholder di list paragraphs, tangani multi-run."""
        for para in paragraphs:
            full = ''.join(r.text for r in para.runs)
            if ph not in full:
                continue
            new_text = full.replace(ph, str(value))
            for i, run in enumerate(para.runs):
                run.text = new_text if i == 0 else ''
                run.font.name = 'Times New Roman'
                run.font.color.rgb = RGBColor(0, 0, 0)
                run.font.highlight_color = None

    @classmethod
    def _replace(cls, doc: Document, ph: str, value: str):
        """Ganti placeholder di seluruh dokumen (paragraf + sel tabel)."""
        cls._replace_in_paragraphs(doc.paragraphs, ph, value)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    cls._replace_in_paragraphs(cell.paragraphs, ph, value)

    @classmethod
    def _fill_common(cls, doc: Document, judul: str, jenis: str, periode: str, user):
        tanggal = timezone.now().strftime('%d %B %Y')
        cls._replace(doc, '{{JUDUL_LAPORAN}}',    judul)
        cls._replace(doc, '{{JENIS_LAPORAN}}',    jenis)
        cls._replace(doc, '{{PERIODE}}',          periode)
        cls._replace(doc, '{{TANGGAL_CETAK}}',    tanggal)
        cls._replace(doc, '{{NAMA_PENCETAK}}',    user.username)
        cls._replace(doc, '{{JABATAN_PENCETAK}}', 'Administrator')
        cls._replace(doc, '{{CATATAN_LAPORAN}}',  '')

    # ══════════════════════════════════════════════════════════════
    # Helper tabel
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def _find_data_table(cls, doc: Document):
        """Cari tabel data (yang berisi placeholder baris contoh)."""
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    t = cell.text
                    if '{{NAMA_KADER_1}}' in t or '{{TABEL_DATA}}' in t or '{{NIM_1}}' in t:
                        return table
        return None

    @classmethod
    def _clear_template_rows(cls, table):
        """Hapus SEMUA baris selain header (baris 0)."""
        for row in list(table.rows)[1:]:
            table._tbl.remove(row._tr)

    @classmethod
    def _update_header_row(cls, table, headers: list):
        """Update teks sel header tanpa mengubah formatting."""
        if not table.rows:
            return
        hdr = table.rows[0]
        for j, text in enumerate(headers):
            if j >= len(hdr.cells):
                break
            para = hdr.cells[j].paragraphs[0]
            if para.runs:
                para.runs[0].text = text
                for run in para.runs[1:]:
                    run.text = ''
            else:
                para.add_run(text)

    @classmethod
    def _set_cell_shading(cls, cell, fill_hex: str):
        tc_pr = cell._element.get_or_add_tcPr()
        for old in tc_pr.findall(qn('w:shd')):
            tc_pr.remove(old)
        shd = tc_pr.makeelement(qn('w:shd'), {
            qn('w:val'):   'clear',
            qn('w:color'): 'auto',
            qn('w:fill'):  fill_hex,
        })
        tc_pr.append(shd)

    @classmethod
    def _add_data_row(cls, table, data: list, row_index: int):
        """Tambah baris data dengan font Times New Roman 10pt + hitam + zebra stripe."""
        row = table.add_row()
        for j, value in enumerate(data):
            if j >= len(row.cells):
                break
            cell = row.cells[j]
            cell.text = ''
            run = cell.paragraphs[0].add_run(str(value))
            run.font.size = Pt(10)
            run.font.name = 'Times New Roman'
            run.font.color.rgb = RGBColor(0, 0, 0)
            if row_index % 2 == 0:
                cls._set_cell_shading(cell, 'F2E4E7')

    # ══════════════════════════════════════════════════════════════
    # Konversi PDF
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def _to_docx_bytes(cls, doc: Document) -> bytes:
        buf = BytesIO()
        doc.save(buf)
        return buf.getvalue()

    @classmethod
    def _convert_to_pdf(cls, docx_bytes: bytes):
        """Konversi docx ke PDF via LibreOffice headless. Return None jika gagal."""
        import subprocess
        tmp_docx = tmp_pdf = None
        try:
            tmp_dir = tempfile.mkdtemp()
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False, dir=tmp_dir) as f:
                f.write(docx_bytes)
                tmp_docx = f.name
            result = subprocess.run(
                ['libreoffice', '--headless', '--convert-to', 'pdf',
                 '--outdir', tmp_dir, tmp_docx],
                capture_output=True, timeout=60,
                env={**os.environ, 'HOME': tmp_dir},
            )
            tmp_pdf = tmp_docx[:-5] + '.pdf'
            if result.returncode == 0 and os.path.exists(tmp_pdf) and os.path.getsize(tmp_pdf) > 0:
                with open(tmp_pdf, 'rb') as f:
                    return f.read()
            return None
        except Exception:
            return None
        finally:
            import shutil
            if tmp_dir and os.path.exists(tmp_dir):
                try:
                    shutil.rmtree(tmp_dir)
                except Exception:
                    pass

    @classmethod
    def _build_response(cls, doc: Document) -> tuple:
        """Kembalikan (bytes, content_type, extension). PDF jika berhasil, DOCX sebagai fallback."""
        docx_bytes = cls._to_docx_bytes(doc)
        pdf_bytes = cls._convert_to_pdf(docx_bytes)
        if pdf_bytes:
            return (pdf_bytes, PDF_TYPE, 'pdf')
        return (docx_bytes, DOCX_TYPE, 'docx')

    # ══════════════════════════════════════════════════════════════
    # Helper Excel
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _hdr_font():
        return Font(name='Times New Roman', bold=True, color='FFFFFF', size=11)

    @staticmethod
    def _hdr_fill():
        return PatternFill(start_color='5B1525', end_color='5B1525', fill_type='solid')

    @staticmethod
    def _thin_border():
        s = Side(style='thin')
        return Border(left=s, right=s, top=s, bottom=s)

    @staticmethod
    def _stripe_fill():
        return PatternFill(start_color='F2E4E7', end_color='F2E4E7', fill_type='solid')

    @staticmethod
    def _data_font(bold=False, size=10):
        return Font(name='Times New Roman', size=size, bold=bold, color='000000')

    @classmethod
    def _excel_title_block(cls, ws, title: str, periode: str, col_count: int):
        last = openpyxl.utils.get_column_letter(col_count)
        ws.merge_cells(f'A1:{last}1')
        ws['A1'] = title
        ws['A1'].font = Font(name='Times New Roman', bold=True, size=14, color='000000')
        ws['A1'].alignment = Alignment(horizontal='center')
        ws.merge_cells(f'A2:{last}2')
        ws['A2'] = f'Periode: {periode}'
        ws['A2'].font = Font(name='Times New Roman', size=11, color='000000')
        ws['A2'].alignment = Alignment(horizontal='center')
        ws.merge_cells(f'A3:{last}3')
        ws['A3'] = f'Dicetak: {timezone.now().strftime("%d %B %Y")}'
        ws['A3'].font = Font(name='Times New Roman', size=9, color='444444')

    @classmethod
    def _excel_headers(cls, ws, row: int, headers: list):
        for col, h in enumerate(headers, 1):
            c = ws.cell(row=row, column=col, value=h)
            c.font = cls._hdr_font()
            c.fill = cls._hdr_fill()
            c.alignment = Alignment(horizontal='center')
            c.border = cls._thin_border()

    @classmethod
    def _excel_save(cls, wb) -> bytes:
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    @classmethod
    def _set_col_widths(cls, ws, widths: list):
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # ══════════════════════════════════════════════════════════════
    # LAPORAN KADER
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def generate_rekap_kader_pdf(cls, queryset, periode: str, user) -> tuple:
        doc = Document(cls.TEMPLATE_PATH)
        cls._fill_common(doc, 'LAPORAN REKAP DATA KADER',
                         'Rekap Data Kader PK IMM FTIK UMKO', periode, user)
        total    = queryset.count()
        aktif    = queryset.exclude(jabatan_struktural='calon').count()
        nonaktif = queryset.filter(jabatan_struktural='calon').count()
        cls._replace(doc, '{{TOTAL_KADER}}',    str(total))
        cls._replace(doc, '{{TOTAL_AKTIF}}',    str(aktif))
        cls._replace(doc, '{{TOTAL_NONAKTIF}}', str(nonaktif))

        table = cls._find_data_table(doc)
        if table:
            cls._clear_template_rows(table)
            cls._update_header_row(table, ['No', 'Nama Lengkap', 'NPM', 'Program Studi', 'Jenis Kelamin', 'Status'])
            for i, k in enumerate(queryset, 1):
                cls._add_data_row(table, [
                    str(i), k.nama_lengkap, k.npm, k.program_studi,
                    'Laki-laki' if k.jenis_kelamin == 'L' else 'Perempuan',
                    k.jabatan_struktural.title(),
                ], i)
        return cls._build_response(doc)

    @classmethod
    def generate_rekap_kader_excel(cls, queryset, periode: str, user) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Data Kader'
        headers = ['No', 'Nama Lengkap', 'NPM', 'Program Studi', 'Jenis Kelamin', 'Fakultas', 'Angkatan', 'Status']
        cls._excel_title_block(ws, 'LAPORAN REKAP DATA KADER — PK IMM FTIK UMKO', periode, len(headers))
        cls._excel_headers(ws, 5, headers)
        border = cls._thin_border()
        stripe = cls._stripe_fill()
        for i, k in enumerate(queryset, 1):
            r = i + 5
            for col, val in enumerate(
                [i, k.nama_lengkap, k.npm, k.program_studi,
                 'Laki-laki' if k.jenis_kelamin == 'L' else 'Perempuan',
                 k.fakultas, k.angkatan, k.jabatan_struktural.title()], 1
            ):
                c = ws.cell(row=r, column=col, value=val)
                c.font = cls._data_font()
                c.border = border
                if i % 2 == 0:
                    c.fill = stripe
        sr = queryset.count() + 7
        ws.cell(row=sr, column=1, value=f'Total: {queryset.count()}').font = cls._data_font(bold=True)
        aktif = queryset.exclude(jabatan_struktural='calon').count()
        ws.cell(row=sr, column=4, value=f'Aktif: {aktif}').font = cls._data_font(bold=True)
        cls._set_col_widths(ws, [5, 25, 15, 22, 15, 22, 10, 15])
        return cls._excel_save(wb)

    # ══════════════════════════════════════════════════════════════
    # LAPORAN PENDAFTAR DAD
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def generate_rekap_pendaftar_pdf(cls, queryset, periode: str, user) -> tuple:
        doc = Document(cls.TEMPLATE_PATH)
        cls._fill_common(doc, 'LAPORAN REKAP PENDAFTAR DAD',
                         'Rekap Pendaftar Darul Arqom Dasar PK IMM FTIK UMKO', periode, user)
        lolos   = queryset.filter(status_verifikasi='lolos_administrasi').count()
        ditolak = queryset.filter(status_verifikasi='ditolak').count()
        cls._replace(doc, '{{TOTAL_KADER}}',    str(queryset.count()))
        cls._replace(doc, '{{TOTAL_AKTIF}}',    str(lolos))
        cls._replace(doc, '{{TOTAL_NONAKTIF}}', str(ditolak))

        table = cls._find_data_table(doc)
        if table:
            cls._clear_template_rows(table)
            cls._update_header_row(table, ['No', 'Nama', 'NPM', 'Program Studi', 'Jenis Kelamin', 'Status Verifikasi'])
            for i, p in enumerate(queryset.select_related('id_biodata'), 1):
                bio = p.id_biodata
                cls._add_data_row(table, [
                    str(i),
                    bio.nama_lengkap if bio else '-',
                    bio.npm if bio else '-',
                    bio.program_studi if bio else '-',
                    ('Laki-laki' if bio.jenis_kelamin == 'L' else 'Perempuan') if bio else '-',
                    p.get_status_verifikasi_display(),
                ], i)
        return cls._build_response(doc)

    @classmethod
    def generate_rekap_pendaftar_excel(cls, queryset, periode: str, user) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Pendaftar DAD'
        headers = ['No', 'No Registrasi', 'Nama', 'NPM', 'Program Studi', 'Jenis Kelamin',
                   'Status Verifikasi', 'Tgl Daftar']
        cls._excel_title_block(ws, 'LAPORAN REKAP PENDAFTAR DAD — PK IMM FTIK UMKO', periode, len(headers))
        cls._excel_headers(ws, 5, headers)
        border = cls._thin_border()
        stripe = cls._stripe_fill()
        for i, p in enumerate(queryset.select_related('id_biodata'), 1):
            r = i + 5
            bio = p.id_biodata
            for col, val in enumerate([
                i, p.no_registrasi,
                bio.nama_lengkap if bio else '-',
                bio.npm if bio else '-',
                bio.program_studi if bio else '-',
                ('Laki-laki' if bio.jenis_kelamin == 'L' else 'Perempuan') if bio else '-',
                p.get_status_verifikasi_display(),
                p.tgl_daftar.strftime('%d/%m/%Y') if p.tgl_daftar else '-',
            ], 1):
                c = ws.cell(row=r, column=col, value=val)
                c.font = cls._data_font()
                c.border = border
                if i % 2 == 0:
                    c.fill = stripe
        sr = queryset.count() + 7
        ws.cell(row=sr, column=1, value=f'Total: {queryset.count()}').font = cls._data_font(bold=True)
        lolos = queryset.filter(status_verifikasi='lolos_administrasi').count()
        ws.cell(row=sr, column=4, value=f'Lolos: {lolos}').font = cls._data_font(bold=True)
        cls._set_col_widths(ws, [5, 20, 25, 15, 22, 15, 20, 12])
        return cls._excel_save(wb)

    # ══════════════════════════════════════════════════════════════
    # LAPORAN KELULUSAN DAD
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def generate_rekap_kelulusan_pdf(cls, queryset, periode: str, user) -> tuple:
        doc = Document(cls.TEMPLATE_PATH)
        cls._fill_common(doc, 'LAPORAN REKAP KELULUSAN DAD',
                         'Rekap Kelulusan Darul Arqom Dasar PK IMM FTIK UMKO', periode, user)
        lulus = queryset.filter(id_pendaftaran__status_kelulusan='lulus').count()
        tidak = queryset.filter(id_pendaftaran__status_kelulusan='tidak_lulus').count()
        cls._replace(doc, '{{TOTAL_KADER}}',    str(queryset.count()))
        cls._replace(doc, '{{TOTAL_AKTIF}}',    str(lulus))
        cls._replace(doc, '{{TOTAL_NONAKTIF}}', str(tidak))

        table = cls._find_data_table(doc)
        if table:
            cls._clear_template_rows(table)
            cls._update_header_row(table, ['No', 'Nama', 'NPM', 'Jenis Kelamin', 'Total Akhir', 'Status Kelulusan'])
            for i, r in enumerate(
                queryset.select_related('id_pendaftaran__id_biodata').order_by('peringkat'), 1
            ):
                pend = r.id_pendaftaran
                bio  = pend.id_biodata if pend else None
                cls._add_data_row(table, [
                    str(i),
                    bio.nama_lengkap if bio else '-',
                    bio.npm if bio else '-',
                    ('Laki-laki' if bio.jenis_kelamin == 'L' else 'Perempuan') if bio else '-',
                    str(r.total_akhir or '0'),
                    pend.get_status_kelulusan_display() if pend else '-',
                ], i)
        return cls._build_response(doc)

    @classmethod
    def generate_rekap_kelulusan_excel(cls, queryset, periode: str, user) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Kelulusan DAD'
        headers = ['Peringkat', 'Nama', 'NPM', 'Jenis Kelamin', 'Skor Aktivitas',
                   'Nilai Interview', 'Total Akhir', 'Status Kelulusan']
        cls._excel_title_block(ws, 'LAPORAN REKAP KELULUSAN DAD — PK IMM FTIK UMKO', periode, len(headers))
        cls._excel_headers(ws, 5, headers)
        border = cls._thin_border()
        stripe = cls._stripe_fill()
        for i, r in enumerate(
            queryset.select_related('id_pendaftaran__id_biodata').order_by('peringkat'), 1
        ):
            row  = i + 5
            pend = r.id_pendaftaran
            bio  = pend.id_biodata if pend else None
            for col, val in enumerate([
                r.peringkat or '-',
                bio.nama_lengkap if bio else '-',
                bio.npm if bio else '-',
                ('Laki-laki' if bio.jenis_kelamin == 'L' else 'Perempuan') if bio else '-',
                float(r.total_skor_aktivitas or 0),
                float(r.nilai_interview or 0),
                float(r.total_akhir or 0),
                pend.get_status_kelulusan_display() if pend else '-',
            ], 1):
                c = ws.cell(row=row, column=col, value=val)
                c.font = cls._data_font()
                c.border = border
                if i % 2 == 0:
                    c.fill = stripe
        sr = queryset.count() + 7
        ws.cell(row=sr, column=1, value=f'Total: {queryset.count()}').font = cls._data_font(bold=True)
        lulus = queryset.filter(id_pendaftaran__status_kelulusan='lulus').count()
        ws.cell(row=sr, column=5, value=f'Lulus: {lulus}').font = cls._data_font(bold=True)
        cls._set_col_widths(ws, [10, 25, 15, 15, 15, 15, 13, 18])
        return cls._excel_save(wb)

    # ══════════════════════════════════════════════════════════════
    # DETAIL PER KADER / PENDAFTAR / KELULUSAN
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def _docx_add_title(cls, doc, text: str, size: int = 14):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(size)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0x5B, 0x15, 0x25)

    @classmethod
    def _docx_add_subtitle(cls, doc, text: str):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(11)
        r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

    @classmethod
    def _docx_add_section(cls, doc, text: str):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(12)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0x5B, 0x15, 0x25)

    @classmethod
    def _docx_add_kv_table(cls, doc, rows: list):
        """Tabel 2 kolom (label: value)."""
        if not rows:
            return
        table = doc.add_table(rows=len(rows), cols=2)
        table.autofit = False
        for i, (label, value) in enumerate(rows):
            row = table.rows[i]
            c1 = row.cells[0]
            c2 = row.cells[1]
            c1.width = Cm(5.5)
            c2.width = Cm(10.5)
            c1.text = ''
            c2.text = ''
            r1 = c1.paragraphs[0].add_run(str(label))
            r1.font.name = 'Times New Roman'
            r1.font.size = Pt(10)
            r1.font.bold = True
            r2 = c2.paragraphs[0].add_run(str(value) if value not in (None, '') else '-')
            r2.font.name = 'Times New Roman'
            r2.font.size = Pt(10)
            for cell in (c1, c2):
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                cls._set_cell_shading(cell, 'FFFFFF' if i % 2 else 'FDF8F0')

    @classmethod
    def _docx_add_list_table(cls, doc, headers: list, rows: list):
        """Tabel data umum dengan header + baris-baris."""
        table = doc.add_table(rows=1 + len(rows), cols=len(headers))
        hdr = table.rows[0]
        for j, h in enumerate(headers):
            cell = hdr.cells[j]
            cell.text = ''
            r = cell.paragraphs[0].add_run(h)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)
            r.font.bold = True
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            cls._set_cell_shading(cell, '5B1525')
        for i, row_data in enumerate(rows, 1):
            row = table.rows[i]
            for j, val in enumerate(row_data):
                cell = row.cells[j]
                cell.text = ''
                r = cell.paragraphs[0].add_run(str(val) if val not in (None, '') else '-')
                r.font.name = 'Times New Roman'
                r.font.size = Pt(10)
                if i % 2 == 0:
                    cls._set_cell_shading(cell, 'F2E4E7')

    # ─── Helper: extract info dari objek ─────────────────────────────

    @staticmethod
    def _biodata_rows(bio):
        if not bio:
            return []
        jk = 'Laki-laki' if bio.jenis_kelamin == 'L' else ('Perempuan' if bio.jenis_kelamin == 'P' else '-')
        ttl = ''
        if bio.tempat_lahir or bio.tgl_lahir:
            ttl = f"{bio.tempat_lahir or '-'}, {bio.tgl_lahir.strftime('%d %B %Y') if bio.tgl_lahir else '-'}"
        return [
            ('Nama Lengkap', bio.nama_lengkap),
            ('NPM', bio.npm),
            ('Program Studi', bio.program_studi),
            ('Fakultas', bio.fakultas),
            ('Angkatan', bio.angkatan),
            ('Jenis Kelamin', jk),
            ('Tempat, Tanggal Lahir', ttl or '-'),
            ('Alamat Domisili', bio.alamat_domisili or '-'),
            ('No. HP', bio.no_hp or '-'),
            ('Nama Ayah', bio.nama_ayah or '-'),
            ('Nama Ibu', bio.nama_ibu or '-'),
            ('No. HP Orang Tua', bio.no_hp_ortu or '-'),
            ('Jabatan Struktural', bio.get_jabatan_struktural_display() if hasattr(bio, 'get_jabatan_struktural_display') else bio.jabatan_struktural),
            ('Periode Jabatan', bio.periode_jabatan or '-'),
            ('Biodata Lengkap', 'Ya' if bio.is_biodata_complete else 'Belum'),
            ('Akun Terhubung', bio.id_user.username if bio.id_user else '-'),
            ('Email Akun', bio.id_user.email if bio.id_user else '-'),
        ]

    @staticmethod
    def _pendaftaran_rows(pendaftaran):
        if not pendaftaran:
            return []
        kelompok = pendaftaran.id_kelompok
        return [
            ('No. Registrasi', pendaftaran.no_registrasi),
            ('Periode DAD', pendaftaran.id_periode.nama_periode if pendaftaran.id_periode else '-'),
            ('Tgl Daftar', pendaftaran.tgl_daftar.strftime('%d %B %Y %H:%M') if pendaftaran.tgl_daftar else '-'),
            ('Status Verifikasi', pendaftaran.get_status_verifikasi_display()),
            ('Tgl Verifikasi', pendaftaran.tgl_verifikasi.strftime('%d %B %Y %H:%M') if pendaftaran.tgl_verifikasi else '-'),
            ('Identik (SSO ↔ Biodata)', 'Ya' if pendaftaran.is_identic else 'Tidak'),
            ('Nama SSO', pendaftaran.api_nama_sso or '-'),
            ('Status Mahasiswa (SSO)', pendaftaran.api_status_mahasiswa or '-'),
            ('Program Studi (SSO)', pendaftaran.api_program_studi or '-'),
            ('Kelompok / Kelas', f"Kelas {kelompok.nama_kelompok}" if kelompok else 'Belum diassign'),
            ('Tahap Saat Ini', pendaftaran.tahap_display['label']),
            ('Status Kelulusan', pendaftaran.get_status_kelulusan_display()),
        ]

    @staticmethod
    def _interview_rows(interview):
        if not interview:
            return []
        return [
            ('Al-Quran — Makhraj & Tajwid', f"{interview.qur_makhraj_tajwid}"),
            ('Al-Quran — Tulis Surat', f"{interview.qur_tulis_surat}"),
            ('Al-Quran — Kandungan Surat', f"{interview.qur_kandungan_surat}"),
            ('Hafalan — 5 Surat Pendek', f"{interview.hafalan_5_pendek}"),
            ('Hafalan — 2 Pengkaderan', f"{interview.hafalan_2_pengkaderan}"),
            ('Hafalan — 1 Favorit', f"{interview.hafalan_1_favorit}"),
            ('Ideologi — Umum', f"{interview.ideologi_umum}"),
            ('Ideologi — Muhammadiyah', f"{interview.ideologi_muhammadiyah}"),
            ('Ideologi — IMM', f"{interview.ideologi_imm}"),
            ('Dialektika — Tujuan', f"{interview.dialektika_tujuan}"),
            ('Dialektika — Minat', f"{interview.dialektika_minat}"),
            ('Dialektika — Bakat', f"{interview.dialektika_bakat}"),
            ('Kesiapan — Ikut Penuh', f"{interview.kesiapan_ikut_penuh}"),
            ('Kesiapan — Persiapan', f"{interview.kesiapan_persiapan}"),
            ('Kesiapan — Konsekuensi', f"{interview.kesiapan_konsekuensi}"),
            ('Rata-rata Akhir', f"{interview.rata_rata}"),
            ('Status Interview', interview.get_status_interview_display() or '-'),
            ('Catatan', interview.catatan or '-'),
            ('Tgl Penilaian', interview.tgl_penilaian.strftime('%d %B %Y %H:%M') if interview.tgl_penilaian else '-'),
        ]

    @staticmethod
    def _aktivitas_headers():
        return ['Hari', 'Keaktifan', 'Kedisiplinan', 'Kontribusi', 'Skor Harian', 'Catatan']

    @staticmethod
    def _aktivitas_rows(aktivitas_qs):
        rows = []
        for a in aktivitas_qs:
            rows.append([
                f"Hari {a.hari_ke}",
                f"{a.poin_keaktifan}",
                f"{a.poin_kedisiplinan}",
                f"{a.poin_kontribusi}",
                f"{a.skor_harian}",
                a.catatan or '-',
            ])
        return rows

    @staticmethod
    def _absensi_headers():
        return ['Hari', 'Sesi', 'Jam', 'Kelompok', 'Waktu Scan']

    @staticmethod
    def _absensi_rows(absensi_qs):
        rows = []
        for ab in absensi_qs:
            rundown = ab.id_qr.id_rundown
            rows.append([
                f"Hari {rundown.hari_ke}",
                rundown.materi,
                f"{rundown.jam_mulai.strftime('%H:%M')}–{rundown.jam_selesai.strftime('%H:%M')}",
                f"Kelas {ab.id_qr.id_kelompok.nama_kelompok}",
                ab.waktu_scan.strftime('%d %B %Y %H:%M'),
            ])
        return rows

    @staticmethod
    def _kelulusan_rows(rekap):
        if not rekap:
            return []
        return [
            ('Total Skor Aktivitas (3 Hari)', f"{rekap.total_skor_aktivitas}"),
            ('Nilai Interview', f"{rekap.nilai_interview}"),
            ('Total Akhir', f"{rekap.total_akhir}"),
            ('Peringkat', str(rekap.peringkat) if rekap.peringkat else '-'),
            ('Terakhir Diperbarui', rekap.updated_at.strftime('%d %B %Y %H:%M') if rekap.updated_at else '-'),
        ]

    # ─── Builder DOCX untuk detail ───────────────────────────────────

    @classmethod
    def _make_section_heading_para(cls, doc: Document, text: str):
        """Buat paragraf heading section (warna maroon, bold)."""
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(12)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0x5B, 0x15, 0x25)
        return p

    @classmethod
    def _make_kv_table(cls, doc: Document, rows: list):
        """Buat tabel 2 kolom (label: value). Return table."""
        if not rows:
            rows = [('—', 'Data tidak tersedia')]
        table = doc.add_table(rows=len(rows), cols=2)
        table.autofit = False
        for i, (label, value) in enumerate(rows):
            row = table.rows[i]
            c1 = row.cells[0]
            c2 = row.cells[1]
            c1.width = Cm(5.5)
            c2.width = Cm(10.5)
            c1.text = ''
            c2.text = ''
            r1 = c1.paragraphs[0].add_run(str(label))
            r1.font.name = 'Times New Roman'
            r1.font.size = Pt(10)
            r1.font.bold = True
            r2 = c2.paragraphs[0].add_run(str(value) if value not in (None, '') else '-')
            r2.font.name = 'Times New Roman'
            r2.font.size = Pt(10)
            for cell in (c1, c2):
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                cls._set_cell_shading(cell, 'FFFFFF' if i % 2 else 'FDF8F0')
        return table

    @classmethod
    def _make_list_table(cls, doc: Document, headers: list, rows: list):
        """Buat tabel data dengan header + baris. Return table."""
        table = doc.add_table(rows=1 + len(rows), cols=len(headers))
        hdr = table.rows[0]
        for j, h in enumerate(headers):
            cell = hdr.cells[j]
            cell.text = ''
            r = cell.paragraphs[0].add_run(h)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)
            r.font.bold = True
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            cls._set_cell_shading(cell, '5B1525')
        for i, row_data in enumerate(rows, 1):
            row = table.rows[i]
            for j, val in enumerate(row_data):
                cell = row.cells[j]
                cell.text = ''
                r = cell.paragraphs[0].add_run(str(val) if val not in (None, '') else '-')
                r.font.name = 'Times New Roman'
                r.font.size = Pt(10)
                if i % 2 == 0:
                    cls._set_cell_shading(cell, 'F2E4E7')
        return table

    @classmethod
    def _append_sections_to_doc(cls, doc: Document, sections: list):
        """Append sections di akhir body doc."""
        for sec in sections:
            cls._make_section_heading_para(doc, sec['heading'])
            if sec['type'] == 'kv':
                cls._make_kv_table(doc, sec.get('rows') or [])
            elif sec['type'] == 'table':
                rows = sec.get('rows') or []
                if not rows:
                    p = doc.add_paragraph()
                    r = p.add_run('Data tidak tersedia.')
                    r.font.name = 'Times New Roman'
                    r.font.size = Pt(10)
                    r.font.italic = True
                else:
                    cls._make_list_table(doc, sec['headers'], rows)
            doc.add_paragraph()

    @classmethod
    def _insert_sections_before(cls, doc: Document, anchor_elem, sections: list):
        """Insert sections di body SEBELUM anchor_elem (XML element).

        Trik: buat elemen via python-docx (append ke akhir body), lalu pindahkan
        via lxml addprevious() ke posisi target — urutan terjaga.
        """
        for sec in sections:
            heading = cls._make_section_heading_para(doc, sec['heading'])
            anchor_elem.addprevious(heading._element)

            if sec['type'] == 'kv':
                table = cls._make_kv_table(doc, sec.get('rows') or [])
                anchor_elem.addprevious(table._element)
            elif sec['type'] == 'table':
                rows = sec.get('rows') or []
                if not rows:
                    p = doc.add_paragraph()
                    r = p.add_run('Data tidak tersedia.')
                    r.font.name = 'Times New Roman'
                    r.font.size = Pt(10)
                    r.font.italic = True
                    anchor_elem.addprevious(p._element)
                else:
                    table = cls._make_list_table(doc, sec['headers'], rows)
                    anchor_elem.addprevious(table._element)

            spacer = doc.add_paragraph()
            anchor_elem.addprevious(spacer._element)

    @classmethod
    def _build_detail_docx(cls, title: str, subject: str, jenis: str, sections: list, user) -> Document:
        """Build docx detail memakai Template_Laporan.docx (dengan kop surat resmi).

        Kop surat (logo IMM + logo UMKO + teks Pimpinan Komisariat + basmalah) berada
        di Word section header dan otomatis ikut. Body template (rekap-specific) diganti:
        - Hapus paragraf 'Periode: X', heading rekap, 'Tabel berikut...', 'Total Kader...'
        - Hapus tabel data rekap (berisi placeholder {{NAMA_KADER_1}} dst)
        - Sisipkan baris subject (nama/no registrasi) di bawah judul
        - Sisipkan sections detail sebelum paragraf 'CATATAN'
        """
        doc = Document(cls.TEMPLATE_PATH)
        tanggal = timezone.now().strftime('%d %B %Y')

        cls._replace(doc, '{{JUDUL_LAPORAN}}',    title)
        cls._replace(doc, '{{JENIS_LAPORAN}}',    jenis)
        cls._replace(doc, '{{PERIODE}}',          '-')
        cls._replace(doc, '{{TANGGAL_CETAK}}',    tanggal)
        cls._replace(doc, '{{NAMA_PENCETAK}}',    user.username)
        cls._replace(doc, '{{JABATAN_PENCETAK}}', 'Administrator')
        cls._replace(doc, '{{CATATAN_LAPORAN}}',  '')
        cls._replace(doc, '{{TOTAL_KADER}}',      '-')
        cls._replace(doc, '{{TOTAL_AKTIF}}',      '-')
        cls._replace(doc, '{{TOTAL_NONAKTIF}}',   '-')

        rekap_section_titles = {'DATA KADER', 'DATA PENDAFTAR DAD', 'DATA KELULUSAN DAD'}
        paragraphs_to_remove = []
        for p in doc.paragraphs:
            t = p.text.strip()
            if (
                t.startswith('Periode:')
                or t in rekap_section_titles
                or t == 'Tabel berikut diisi otomatis dari database sistem:'
                or t.startswith('Total Kader:')
            ):
                paragraphs_to_remove.append(p)
        for p in paragraphs_to_remove:
            p._element.getparent().remove(p._element)

        data_table = cls._find_data_table(doc)
        if data_table is not None:
            data_table._element.getparent().remove(data_table._element)

        if subject:
            title_para = None
            for p in doc.paragraphs:
                if title in p.text:
                    title_para = p
                    break
            if title_para is not None:
                subject_para = doc.add_paragraph()
                subject_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = subject_para.add_run(subject)
                r.font.name = 'Times New Roman'
                r.font.size = Pt(11)
                r.font.italic = True
                r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
                title_para._element.addnext(subject_para._element)

        anchor_p = None
        for p in doc.paragraphs:
            if p.text.strip() == 'CATATAN':
                anchor_p = p
                break

        if anchor_p is not None:
            cls._insert_sections_before(doc, anchor_p._element, sections)
        else:
            cls._append_sections_to_doc(doc, sections)

        return doc

    # ─── Builder Excel untuk detail ──────────────────────────────────

    @classmethod
    def _build_detail_excel(cls, title: str, subtitle: str, sections: list, user) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Detail'
        ws.merge_cells('A1:D1')
        ws['A1'] = title
        ws['A1'].font = Font(name='Times New Roman', bold=True, size=14, color='5B1525')
        ws['A1'].alignment = Alignment(horizontal='center')
        ws.merge_cells('A2:D2')
        ws['A2'] = subtitle
        ws['A2'].font = Font(name='Times New Roman', size=11, color='444444')
        ws['A2'].alignment = Alignment(horizontal='center')
        ws.merge_cells('A3:D3')
        ws['A3'] = f"Dicetak: {timezone.now().strftime('%d %B %Y %H:%M')} oleh {user.username}"
        ws['A3'].font = Font(name='Times New Roman', size=9, color='666666')
        ws['A3'].alignment = Alignment(horizontal='center')

        row = 5
        border = cls._thin_border()
        stripe = cls._stripe_fill()

        for sec in sections:
            ws.cell(row=row, column=1, value=sec['heading']).font = Font(
                name='Times New Roman', bold=True, size=12, color='5B1525'
            )
            row += 1
            if sec['type'] == 'kv':
                rows = sec.get('rows') or [('—', 'Data tidak tersedia')]
                for i, (label, value) in enumerate(rows):
                    c1 = ws.cell(row=row, column=1, value=str(label))
                    c2 = ws.cell(row=row, column=2, value=str(value) if value not in (None, '') else '-')
                    c1.font = cls._data_font(bold=True)
                    c2.font = cls._data_font()
                    c1.border = border
                    c2.border = border
                    if i % 2:
                        c1.fill = stripe
                        c2.fill = stripe
                    row += 1
            elif sec['type'] == 'table':
                headers = sec['headers']
                for j, h in enumerate(headers, 1):
                    c = ws.cell(row=row, column=j, value=h)
                    c.font = cls._hdr_font()
                    c.fill = cls._hdr_fill()
                    c.alignment = Alignment(horizontal='center')
                    c.border = border
                row += 1
                data_rows = sec.get('rows') or []
                if not data_rows:
                    ws.cell(row=row, column=1, value='Data tidak tersedia.').font = Font(
                        name='Times New Roman', italic=True, size=10
                    )
                    row += 1
                else:
                    for i, row_data in enumerate(data_rows, 1):
                        for j, val in enumerate(row_data, 1):
                            c = ws.cell(row=row, column=j, value=str(val) if val not in (None, '') else '-')
                            c.font = cls._data_font()
                            c.border = border
                            if i % 2 == 0:
                                c.fill = stripe
                        row += 1
            row += 1

        ws.column_dimensions['A'].width = 28
        ws.column_dimensions['B'].width = 40
        ws.column_dimensions['C'].width = 18
        ws.column_dimensions['D'].width = 22
        ws.column_dimensions['E'].width = 18
        ws.column_dimensions['F'].width = 30
        return cls._excel_save(wb)

    # ─── Detail Kader ────────────────────────────────────────────────

    @classmethod
    def generate_detail_kader_pdf(cls, biodata, user) -> tuple:
        sections = [
            {'type': 'kv', 'heading': 'Data Pribadi Kader', 'rows': cls._biodata_rows(biodata)},
        ]
        pendaftaran = getattr(biodata, 'pendaftaran', None)
        if pendaftaran:
            sections.append({
                'type': 'kv',
                'heading': 'Riwayat Pendaftaran DAD',
                'rows': cls._pendaftaran_rows(pendaftaran),
            })
        subject = biodata.nama_lengkap if biodata else '-'
        doc = cls._build_detail_docx(
            'DETAIL DATA KADER',
            subject,
            'Detail Data Kader PK IMM FTIK UMKO',
            sections, user,
        )
        return cls._build_response(doc)

    @classmethod
    def generate_detail_kader_excel(cls, biodata, user) -> bytes:
        sections = [
            {'type': 'kv', 'heading': 'Data Pribadi Kader', 'rows': cls._biodata_rows(biodata)},
        ]
        pendaftaran = getattr(biodata, 'pendaftaran', None)
        if pendaftaran:
            sections.append({
                'type': 'kv',
                'heading': 'Riwayat Pendaftaran DAD',
                'rows': cls._pendaftaran_rows(pendaftaran),
            })
        return cls._build_detail_excel(
            'DETAIL DATA KADER — PK IMM FTIK UMKO',
            biodata.nama_lengkap if biodata else '-',
            sections, user,
        )

    # ─── Detail Pendaftar DAD ────────────────────────────────────────

    @classmethod
    def _pendaftar_sections(cls, pendaftaran):
        from apps.pendaftaran.models import AbsensiDAD
        from apps.penilaian.models import NilaiAktivitas, NilaiInterview

        bio = pendaftaran.id_biodata
        interview = NilaiInterview.objects.filter(id_pendaftaran=pendaftaran).first()
        aktivitas_qs = NilaiAktivitas.objects.filter(id_pendaftaran=pendaftaran).order_by('hari_ke')
        absensi_qs = AbsensiDAD.objects.filter(
            id_pendaftaran=pendaftaran,
        ).select_related('id_qr__id_rundown', 'id_qr__id_kelompok').order_by(
            'id_qr__id_rundown__hari_ke', 'id_qr__id_rundown__urutan',
        )

        return [
            {'type': 'kv', 'heading': 'Biodata Peserta', 'rows': cls._biodata_rows(bio)},
            {'type': 'kv', 'heading': 'Pendaftaran DAD', 'rows': cls._pendaftaran_rows(pendaftaran)},
            {'type': 'kv', 'heading': 'Nilai Interview', 'rows': cls._interview_rows(interview)},
            {
                'type': 'table',
                'heading': 'Penilaian Aktivitas Harian',
                'headers': cls._aktivitas_headers(),
                'rows': cls._aktivitas_rows(aktivitas_qs),
            },
            {
                'type': 'table',
                'heading': 'Riwayat Absensi',
                'headers': cls._absensi_headers(),
                'rows': cls._absensi_rows(absensi_qs),
            },
        ]

    @classmethod
    def generate_detail_pendaftar_pdf(cls, pendaftaran, user) -> tuple:
        sections = cls._pendaftar_sections(pendaftaran)
        bio = pendaftaran.id_biodata
        subject = f"{bio.nama_lengkap} — {pendaftaran.no_registrasi}" if bio else pendaftaran.no_registrasi
        doc = cls._build_detail_docx(
            'DETAIL PENDAFTAR DAD',
            subject,
            'Detail Pendaftar Darul Arqom Dasar PK IMM FTIK UMKO',
            sections, user,
        )
        return cls._build_response(doc)

    @classmethod
    def generate_detail_pendaftar_excel(cls, pendaftaran, user) -> bytes:
        sections = cls._pendaftar_sections(pendaftaran)
        bio = pendaftaran.id_biodata
        subtitle = f"{bio.nama_lengkap} — {pendaftaran.no_registrasi}" if bio else pendaftaran.no_registrasi
        return cls._build_detail_excel('DETAIL PENDAFTAR DAD — PK IMM FTIK UMKO', subtitle, sections, user)

    # ─── Detail Kelulusan ────────────────────────────────────────────

    @classmethod
    def generate_detail_kelulusan_pdf(cls, rekap, user) -> tuple:
        pendaftaran = rekap.id_pendaftaran
        sections = cls._pendaftar_sections(pendaftaran)
        sections.append({
            'type': 'kv',
            'heading': 'Rekap Kelulusan & Peringkat',
            'rows': cls._kelulusan_rows(rekap),
        })
        bio = pendaftaran.id_biodata
        subject = f"{bio.nama_lengkap} — Peringkat {rekap.peringkat or '-'}" if bio else f"Peringkat {rekap.peringkat or '-'}"
        doc = cls._build_detail_docx(
            'DETAIL KELULUSAN DAD',
            subject,
            'Detail Kelulusan Darul Arqom Dasar PK IMM FTIK UMKO',
            sections, user,
        )
        return cls._build_response(doc)

    @classmethod
    def generate_detail_kelulusan_excel(cls, rekap, user) -> bytes:
        pendaftaran = rekap.id_pendaftaran
        sections = cls._pendaftar_sections(pendaftaran)
        sections.append({
            'type': 'kv',
            'heading': 'Rekap Kelulusan & Peringkat',
            'rows': cls._kelulusan_rows(rekap),
        })
        bio = pendaftaran.id_biodata
        subtitle = f"{bio.nama_lengkap} — Peringkat {rekap.peringkat or '-'}" if bio else f"Peringkat {rekap.peringkat or '-'}"
        return cls._build_detail_excel('DETAIL KELULUSAN DAD — PK IMM FTIK UMKO', subtitle, sections, user)
