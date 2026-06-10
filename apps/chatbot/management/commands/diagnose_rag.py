"""Diagnostik retrieval RAG (read-only).

Menampilkan chunk yang BENAR-BENAR terambil untuk sebuah pertanyaan, langsung
dari database — supaya kita tahu pasti apakah pengetahuan ketemu atau tidak,
tanpa menebak. Tidak memanggil OpenAI untuk chat (hanya embedding query bila
vector search aktif), tidak mengubah data apa pun.

Contoh:
  python manage.py diagnose_rag "apa isi dari bab II ad art"
  python manage.py diagnose_rag "pasal 7" --jenis umum
  python manage.py diagnose_rag "" --list   # daftar dokumen + contoh metadata
"""
from django.core.management.base import BaseCommand

from apps.chatbot.models import ChunkPengetahuan, DokumenPengetahuan, StatusDokumen
from apps.chatbot.views import ChatbotAPIView


class Command(BaseCommand):
    help = 'Diagnostik retrieval RAG: tampilkan chunk yang terambil untuk sebuah query.'

    def add_arguments(self, parser):
        parser.add_argument('pesan', nargs='?', default='', help='Pertanyaan user')
        parser.add_argument('--jenis', default='umum', help='umum | pendaftaran')
        parser.add_argument('--list', action='store_true',
                            help='Tampilkan daftar dokumen & contoh metadata chunk')

    def handle(self, *args, **opts):
        jenis = opts['jenis']

        if opts['list']:
            self._list_dokumen(jenis)
            return

        pesan = opts['pesan']
        if not pesan:
            self.stdout.write(self.style.WARNING(
                'Beri pertanyaan, mis: python manage.py diagnose_rag "isi bab II ad art"'
            ))
            return

        view = ChatbotAPIView()
        chunks = view._find_matching_chunks(pesan, jenis)

        self.stdout.write(self.style.HTTP_INFO(f'Query : {pesan!r}  (jenis={jenis})'))
        self.stdout.write(f'Chunk terambil: {len(chunks)}')
        if not chunks:
            self.stdout.write(self.style.ERROR(
                'TIDAK ADA chunk terambil → AI akan menjawab "belum memiliki informasi". '
                'Cek: dokumen aktif & status READY? metadata memuat BAB? (pakai --list)'
            ))
            return

        for i, c in enumerate(chunks, 1):
            tag = 'keyword' if c['distance'] == 0.0 else f"vector d={c['distance']:.3f}"
            self.stdout.write(self.style.SUCCESS(
                f"\n[{i}] {tag} | seksi={c['seksi']!r} | dok={c['judul_dokumen']!r}"
            ))
            cuplik = ' '.join(c['teks'].split())[:240]
            self.stdout.write(f'    {cuplik}')

    def _list_dokumen(self, jenis: str):
        docs = DokumenPengetahuan.objects.filter(jenis_chatbot=jenis)
        self.stdout.write(self.style.HTTP_INFO(f'Dokumen jenis={jenis}:'))
        for d in docs:
            self.stdout.write(
                f"  - {d.judul!r} | status={d.status} | aktif={d.is_active} "
                f"| chunk={d.jumlah_chunk}"
            )
            sample = ChunkPengetahuan.objects.filter(id_dokumen=d).order_by('urutan')
            for c in sample[:8]:
                self.stdout.write(f"      [urutan {c.urutan}] seksi={c.metadata_seksi!r}")
        # Catatan ringkas keanggotaan READY
        ready = docs.filter(status=StatusDokumen.READY, is_active=True).count()
        self.stdout.write(f'\nDokumen aktif & READY: {ready}')
