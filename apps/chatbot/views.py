"""Views untuk app chatbot — semua CBV."""
import json
import logging
import re

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView
from pgvector.django import CosineDistance

from apps.chatbot.forms import DatasetChatbotForm, DokumenPengetahuanForm
from apps.chatbot.models import (
    ChunkPengetahuan,
    DatasetChatbot,
    DokumenPengetahuan,
    RiwayatChat,
    StatusDokumen,
)
from apps.chatbot.services import PDFIngestService
from core.budget_limiter import BudgetLimiter
from core.constants import JenisChatbot
from core.exceptions import OpenAIServiceError
from core.mixins import AdminRequiredMixin, CalonKaderRequiredMixin
from core.rate_limiter import RateLimiter
from core.security import issue_chat_token, verify_chat_token
from core.services import OpenAIService

logger = logging.getLogger(__name__)


# ─── Chatbot Publik ───────────────────────────────────────────────────────

def _issue_token_for(request) -> str:
    """Helper: terbitkan signed token chat untuk klien yang sedang merender halaman."""
    ip = RateLimiter.get_client_ip(request)
    ua = request.META.get('HTTP_USER_AGENT', '')
    return issue_chat_token(ip, ua)


class ChatbotPublikView(View):
    """Antarmuka chatbot publik (tanpa login)."""

    template_name = 'chatbot/chatbot_publik.html'

    def get(self, request):
        return render(request, self.template_name, {
            'chatbot_config': {
                'jenis': 'umum',
                'quick_topics': [
                    'Ideologi IMM',
                    'Sejarah IMM',
                    'Struktur Organisasi',
                    'Pendaftaran DAD',
                ],
                'api_url': reverse('chatbot:api_send'),
                'chat_token': _issue_token_for(request),
            },
        })


class ChatbotKaderView(CalonKaderRequiredMixin, View):
    """Chatbot untuk calon kader yang sudah login (konteks pendaftaran)."""

    template_name = 'chatbot/chatbot_kader.html'

    def get(self, request):
        return render(request, self.template_name, {
            'chatbot_config': {
                'jenis': 'pendaftaran',
                'quick_topics': [
                    'Cara Daftar DAD',
                    'Berkas yang Dibutuhkan',
                    'Jadwal Kegiatan',
                ],
                'api_url': reverse('chatbot:api_send'),
                'chat_token': _issue_token_for(request),
            },
        })


# ─── Chatbot API ──────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class ChatbotAPIView(View):
    """
    API endpoint chatbot.
    Alur: Rate Limit → Sapaan → Cari Dataset → Kirim ke OpenAI dengan Knowledge → Jawab

    Keamanan:
      - CSRF dimatikan karena public chatbot (anon) tidak punya token, TAPI
        diproteksi dengan cek same-origin (Origin/Referer header) agar situs
        jahat tidak bisa memicu request cross-origin yang membakar budget OpenAI.
      - Payload JSON dibatasi 32 KB — pesan chat seharusnya jauh lebih kecil.
    """

    # Batas ukuran body JSON. Chat seharusnya <5 KB; 32 KB sudah sangat longgar.
    MAX_BODY_BYTES = 32 * 1024

    # Batas panjang pesan dari user. Pesan chat normal jauh di bawah ini.
    # Membatasi panjang = membatasi token OpenAI yang terbakar per request.
    MAX_PESAN_CHARS = 800

    # Minimum jeda antar request dari IP yang sama (detik). 1.0 cukup untuk
    # ngobrol natural tapi membunuh skenario k6 dengan 10 VUs konkuren.
    MIN_INTERVAL_PER_IP = 1.0
    # Minimum jeda antar request dari sesi yang sama. Sesi (sesi_id) ini
    # kunci anti-flood per percakapan, terlepas IP.
    MIN_INTERVAL_PER_SESSION = 1.5

    SAPAAN_KEYWORDS = [
        'halo', 'hai', 'hi', 'hey', 'assalamualaikum', 'assalamu',
        'apa kabar', 'apakabar', 'selamat pagi', 'selamat siang',
        'selamat malam', 'selamat sore', 'pagi', 'siang', 'sore', 'malam',
        'permisi', 'terima kasih', 'makasih', 'thanks', 'terimakasih',
        'waalaikumsalam', 'ok', 'oke', 'baik', 'siap', 'hallo', 'haloo',
    ]

    SAPAAN_RESPONSE = {
        'umum': (
            "Waalaikumsalam! Halo, saya Asisten Virtual PK IMM FTIK UMKO. "
            "Saya siap membantu menjawab pertanyaan seputar ke-IMM-an. "
            "Silakan tanyakan apa saja!"
        ),
        'pendaftaran': (
            "Waalaikumsalam! Halo Kaders, saya Asisten Pendaftaran DAD "
            "PK IMM FTIK UMKO. Silakan tanyakan tentang pendaftaran DAD!"
        ),
    }

    KATA_KUNCI_IMM = [
        'imm', 'dad', 'darul arqam', 'kader', 'komisariat', 'umko',
        'muhammadiyah', 'pimpinan', 'pendaftaran', 'registrasi',
    ]

    STOPWORDS = {
        'apa', 'siapa', 'kapan', 'dimana', 'bagaimana', 'mengapa',
        'kenapa', 'berapa', 'yang', 'dan', 'atau', 'di', 'ke', 'dari',
        'ini', 'itu', 'adalah', 'dengan', 'untuk', 'pada', 'tidak',
        'ada', 'saya', 'anda', 'kamu', 'bisa', 'boleh', 'mau',
        'tolong', 'coba', 'dong', 'ya', 'nih', 'kan', 'sih', 'lah',
        'the', 'is', 'what', 'who', 'how', 'a', 'an', 'in', 'of',
    }

    def _is_sapaan(self, pesan: str) -> bool:
        """
        Cek apakah pesan HANYA sapaan biasa.
        'halo' = sapaan. 'halo siapa ketua umum' = BUKAN sapaan.
        """
        p = pesan.strip().lower()
        kata = p.split()

        if len(kata) > 3:
            return False

        # Semua kata dalam pesan harus merupakan kata sapaan
        for k in kata:
            if not any(k == s or k.startswith(s) for s in self.SAPAAN_KEYWORDS):
                return False
        return True

    # Threshold cosine distance untuk vector search RAG. CosineDistance
    # = 1 - cos_similarity, range 0 (identik) – 2 (berlawanan).
    # Distance ≤ 0.55 = Cosine Similarity ≥ 0.45.
    # 0.8 sebelumnya terlalu longgar (similarity 20%) → chunk tidak relevan masuk.
    # 0.5 terlalu ketat untuk query pendek seperti "pasal 7" (short query vs
    # long chunk text → similarity rendah). 0.55 adalah keseimbangan: cukup ketat
    # untuk menolak noise, cukup longgar untuk query pendek berbasis dokumen.
    # Pasal/BAB eksplisit ditangani keyword search (distance=0.0) — ini untuk
    # query semantik seperti "apa tujuan IMM" atau "syarat menjadi anggota".
    RAG_DISTANCE_THRESHOLD = 0.55
    RAG_TOP_K = 5  # ambil 5 chunk terdekat per query

    # Regex untuk deteksi pertanyaan spesifik tentang Pasal/BAB tertentu.
    # Saat user tanya "pasal 7", keyword-match jauh lebih reliable daripada
    # vector search yang cenderung ngeluarkan distance >0.5 untuk query pendek.
    PASAL_REGEX = re.compile(r'\bpasal\s+(\d+)', re.IGNORECASE)
    BAB_REGEX = re.compile(r'\bbab\s+([ivxlcdm\d]+)', re.IGNORECASE)

    def _find_matching_chunks(self, pesan: str, jenis: str) -> list:
        """Hybrid search RAG: keyword (pasal/bab) + vector (semantic).

        Strategi:
          1. Keyword match dulu — kalau user tanya "pasal 7" / "bab III",
             cari chunk yang teks/metadata-nya berisi pattern tersebut.
             Ini recall TINGGI untuk pertanyaan eksplisit.
          2. Vector search untuk pertanyaan natural / konseptual.
          3. Dedupe by id_chunk — keyword diprioritaskan (distance=0).

        Return list[dict] (teks, seksi, judul_dokumen, distance).
        """
        base_qs = ChunkPengetahuan.objects.filter(
            id_dokumen__jenis_chatbot=jenis,
            id_dokumen__is_active=True,
            id_dokumen__status=StatusDokumen.READY,
        ).select_related('id_dokumen')

        if not base_qs.exists():
            return []

        results: list[dict] = []
        seen_ids: set[int] = set()

        def _push(chunk: ChunkPengetahuan, distance: float) -> None:
            if chunk.id_chunk in seen_ids:
                return
            results.append({
                'teks': chunk.teks,
                'seksi': chunk.metadata_seksi,
                'judul_dokumen': chunk.id_dokumen.judul,
                'distance': distance,
            })
            seen_ids.add(chunk.id_chunk)

        # === Step 1: keyword search untuk "pasal X" / "bab X" ===
        # PENTING: PostgreSQL iregex menggunakan POSIX regex yang TIDAK mendukung
        # \b (word boundary). Solusi: gunakan icontains untuk DB query lalu
        # filter Python-side dengan re (yang mendukung \b dengan benar).
        pasal_match = self.PASAL_REGEX.search(pesan)
        if pasal_match:
            pasal_num = pasal_match.group(1)
            exact_pasal = re.compile(
                rf'\bpasal\s+{re.escape(pasal_num)}\b', re.IGNORECASE
            )
            # icontains: cepat, safe di PostgreSQL
            candidates = base_qs.filter(
                Q(teks__icontains=f'pasal {pasal_num}') |
                Q(metadata_seksi__icontains=f'pasal {pasal_num}')
            ).order_by('id_chunk')[:20]
            for c in candidates:
                # Python-side: pastikan presisi (hindari "pasal 7" match "pasal 71")
                if exact_pasal.search(c.teks) or exact_pasal.search(c.metadata_seksi or ''):
                    _push(c, 0.0)

        bab_match = self.BAB_REGEX.search(pesan)
        if bab_match:
            bab_num = bab_match.group(1)
            exact_bab = re.compile(
                rf'\bbab\s+{re.escape(bab_num)}\b', re.IGNORECASE
            )
            candidates = base_qs.filter(
                Q(teks__icontains=f'bab {bab_num}') |
                Q(metadata_seksi__icontains=f'bab {bab_num}')
            ).order_by('id_chunk')[:20]
            for c in candidates:
                if exact_bab.search(c.teks) or exact_bab.search(c.metadata_seksi or ''):
                    _push(c, 0.0)

        # === Step 2: vector search untuk semantic similarity ===
        # Strategi 2 lapis:
        #   (a) Filter dengan threshold ketat → ambil yang sangat relevan
        #   (b) Kalau (a) kurang dari 2 chunk DAN keyword search juga kosong,
        #       fallback paksa ambil top-3 terdekat tanpa threshold supaya
        #       pertanyaan natural ("apa kewajiban anggota") tetap dapat
        #       konteks meski phrasing-nya beda jauh dari teks di PDF.
        has_embeddings = base_qs.filter(embedding__isnull=False).exists()
        if has_embeddings:
            try:
                query_vec = OpenAIService().embed_text(pesan)
                vector_qs = (
                    base_qs.filter(embedding__isnull=False)
                    .annotate(distance=CosineDistance('embedding', query_vec))
                    .order_by('distance')
                )
                # (a) hasil dalam threshold
                tight = list(vector_qs.filter(
                    distance__lte=self.RAG_DISTANCE_THRESHOLD,
                )[:self.RAG_TOP_K])
                for c in tight:
                    _push(c, float(c.distance))

                # (b) Fallback: aktif kalau results masih kosong setelah
                # keyword + vector search. Cek hasil AKTUAL (bukan pola query)
                # karena keyword search bisa saja tidak menemukan apapun meski
                # pola pasal/bab terdeteksi (misal: nomor pasal tidak ada di KB).
                keyword_found = any(r['distance'] == 0.0 for r in results)
                if len(results) == 0 or (not keyword_found and len(results) < 2):
                    top_fallback = list(vector_qs[:2])
                    for c in top_fallback:
                        if float(c.distance) < 0.7:
                            _push(c, float(c.distance))
            except OpenAIServiceError:
                logger.exception('Gagal embed query untuk RAG; pakai keyword saja')

        # Cap total hasil — keyword + vector. Cukup untuk konteks AI tanpa
        # membuat prompt terlalu panjang.
        return results[:self.RAG_TOP_K + 3]

    def _find_matching_datasets(self, pesan: str, jenis: str, sesi_id: str = '') -> list:
        """
        Cari dataset yang relevan dengan pencarian FLEKSIBEL (keyword-based).

        Metode (dari paling akurat ke paling longgar):
        1. Keyword lengkap ada di pesan → skor TINGGI
        2. Kata-kata keyword cocok dengan kata-kata pesan → skor proporsional
        3. Kata-kata user ditemukan di respon_jawaban → skor tambahan kecil

        Jika pesan sangat pendek (≤2 kata bermakna), konteks diperkaya dengan
        pesan user sebelumnya dari sesi yang sama — sehingga follow-up seperti
        "FTIK" setelah "siapa ketua umum IMM" tetap dapat dicocokkan.

        Catatan: ini search untuk DatasetChatbot (entry manual admin). Untuk
        pencarian PDF/RAG, lihat ``_find_matching_chunks``.
        """
        pesan_lower = pesan.strip().lower()
        kata_user = [k for k in pesan_lower.split() if k not in self.STOPWORDS and len(k) >= 2]

        # Konteks follow-up: gabungkan pesan pendek dengan pesan sebelumnya
        if len(kata_user) <= 2 and sesi_id:
            last_msg = (
                RiwayatChat.objects.filter(sesi_id=sesi_id)
                .order_by('-waktu_chat')
                .values_list('pesan_user', flat=True)
                .first()
            )
            if last_msg:
                last_lower = last_msg.strip().lower()
                extra_kata = [k for k in last_lower.split() if k not in self.STOPWORDS and len(k) >= 2]
                kata_user = list(dict.fromkeys(kata_user + extra_kata))
                pesan_lower = (pesan_lower + ' ' + last_lower).strip()

        datasets = DatasetChatbot.objects.filter(jenis_chatbot=jenis, is_active=True)
        scored = []

        for dataset in datasets:
            all_keywords = [kw.strip().lower() for kw in dataset.intent_keyword.split(',') if kw.strip()]
            total_score = 0

            for keyword_phrase in all_keywords:
                phrase_score = 0

                # Metode 1: keyword lengkap ada di pesan (paling akurat)
                if keyword_phrase in pesan_lower:
                    phrase_score += len(keyword_phrase.split()) * 5
                else:
                    # Metode 2: cocokkan per kata, buang stopword
                    kata_keyword = [k for k in keyword_phrase.split() if k not in self.STOPWORDS and len(k) >= 2]

                    if kata_keyword:
                        cocok = 0
                        for kk in kata_keyword:
                            for ku in kata_user:
                                if kk == ku:
                                    cocok += 2
                                    break
                                elif kk in ku or ku in kk:
                                    cocok += 1
                                    break

                        if cocok > 0:
                            persen_cocok = cocok / (len(kata_keyword) * 2)
                            # Minimal 30% kata harus cocok agar dianggap relevan
                            if persen_cocok >= 0.3:
                                phrase_score += cocok

                total_score += phrase_score

            # Metode 3: bonus jika kata-kata user ditemukan di respon_jawaban
            if dataset.respon_jawaban:
                respon_lower = dataset.respon_jawaban.lower()
                for ku in kata_user:
                    if len(ku) >= 4 and ku in respon_lower:
                        total_score += 0.5

            if total_score > 0:
                scored.append((dataset, total_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [ds for ds, _ in scored]

    def _build_knowledge_text(
        self,
        matching_datasets: list,
        matching_chunks: list,
        jenis: str,
    ) -> str:
        """
        Bangun teks knowledge untuk dikirim ke OpenAI.
        Gabungkan: dataset manual (admin) + chunk RAG (PDF) + ringkasan topik.

        Catatan: instruksi_ai tidak lagi dikirim ke OpenAI — system prompt
        global di OpenAIService sudah menangani gaya jawab & batasan topik.
        Field-nya tetap ada di DB (sesuai skripsi Tabel 3.19) tapi diabaikan.
        """
        parts = []
        idx = 1

        # Instruksi eksplisit ke AI — tanpa ini, system prompt utama (yang
        # ketat) kadang membuat AI menolak meski chunk RELEVAN sudah dikirim,
        # dengan alasan "belum spesifik". Header ini memastikan AI memprioritaskan
        # konten dari knowledge base resmi.
        if matching_chunks or matching_datasets:
            parts.append(
                "[INSTRUKSI PENGGUNAAN KNOWLEDGE BASE]\n"
                "Konten di bawah ini berasal dari knowledge base RESMI PK IMM "
                "(dokumen yang sudah di-upload admin & dataset terverifikasi).\n"
                "ATURAN:\n"
                "1. Jika ada bagian yang relevan dengan pertanyaan user, GUNAKAN "
                "sebagai dasar jawaban dan kutip isinya secara akurat.\n"
                "2. Kutip nomor pasal/BAB PERSIS seperti tertulis "
                "(contoh: 'Pasal 7 AD menyatakan...').\n"
                "3. JANGAN tambahkan fakta yang tidak tertulis di konten di bawah ini.\n"
                "4. Jika konten yang ada tidak secara langsung menjawab pertanyaan, "
                "katakan tidak memiliki informasi — JANGAN mengarang dari asumsi."
            )

        # 1. Chunk RAG (PDF) — biasanya lebih kaya konteks daripada dataset
        # manual, jadi taruh di atas. Maks RAG_TOP_K (sudah dibatasi di caller).
        for c in matching_chunks:
            header = f"[Pengetahuan {idx} — dari dokumen: {c['judul_dokumen']}"
            if c['seksi']:
                header += f" / {c['seksi']}"
            header += "]"
            parts.append(f"{header}\n{c['teks']}")
            idx += 1

        # 2. Dataset manual (admin) — maks 5 teratas yang relevan.
        for ds in matching_datasets[:5]:
            if ds.respon_jawaban and ds.respon_jawaban.strip():
                parts.append(
                    f"[Pengetahuan {idx} — topik: {ds.intent_keyword}]\n"
                    f"{ds.respon_jawaban}"
                )
                idx += 1

        # Ringkasan semua topik DIHAPUS — pengiriman semua dataset (meski tidak
        # relevan) menambahkan noise ke prompt dan membuat model menjawab dari
        # ringkasan yang pendek (120 char) daripada jawaban lengkap yang matched.
        # Model sudah mendapat dataset yang paling relevan di bagian (2) di atas.

        return "\n\n".join(parts)

    def _get_chat_history(self, sesi_id: str) -> list:
        """Ambil 3 riwayat chat terakhir untuk konteks OpenAI."""
        if not sesi_id:
            return []
        recent = RiwayatChat.objects.filter(sesi_id=sesi_id).order_by('-waktu_chat')[:3]
        history = []
        for chat in reversed(list(recent)):
            history.append({"role": "user", "content": chat.pesan_user})
            history.append({"role": "assistant", "content": chat.respon_bot})
        return history

    def _save_chat(self, user, dataset, sesi_id, pesan, respon, is_found):
        """Simpan riwayat chat ke database."""
        RiwayatChat.objects.create(
            id_user=user,
            id_dataset=dataset,
            sesi_id=sesi_id,
            pesan_user=pesan,
            respon_bot=respon,
            is_found=is_found,
        )

    def _notify_admin(self, user, pesan):
        """Kirim notifikasi ke admin untuk pertanyaan yang belum terjawab."""
        from apps.accounts.models import User as UserModel
        from apps.notifikasi.models import Notifikasi
        from core.constants import TipeNotifikasi
        pengirim = 'Publik' if user is None else user.username
        for admin in UserModel.objects.filter(role='admin', is_active=True):
            Notifikasi.objects.create(
                id_user=admin,
                judul='Pertanyaan Chatbot Belum Terjawab',
                pesan=(
                    f'Pertanyaan dari {pengirim}: "{pesan}"\n\n'
                    'Chatbot tidak dapat menjawab. '
                    'Silakan tambahkan pengetahuan baru di Dataset Chatbot.'
                ),
                tipe=TipeNotifikasi.CHATBOT,
            )

    def _is_same_origin(self, request) -> bool:
        """Pastikan request berasal dari domain aplikasi sendiri.

        STRICT: untuk endpoint chatbot publik kita WAJIB ada Origin header
        atau minimal Referer dengan host yang sama. Browser yang sah selalu
        mengirim Origin pada POST cross-site/same-site. Klien CLI seperti
        curl/k6 yang lupa mengirim Origin akan ditolak — ini fitur, bukan
        bug, karena mencegah skrip masal langsung hit endpoint.

        Untuk pengembangan lokal/health-check via curl, jalankan dari
        loopback atau pakai endpoint admin yang berbeda.
        """
        from urllib.parse import urlparse

        allowed_host = request.get_host()
        origin = request.META.get('HTTP_ORIGIN', '').strip()
        referer = request.META.get('HTTP_REFERER', '').strip()

        # Wajib ada salah satu (Origin lebih kuat)
        if not origin and not referer:
            return False

        for header in (origin, referer):
            if not header:
                continue
            try:
                host = urlparse(header).netloc
            except ValueError:
                return False
            if host and host != allowed_host:
                return False
        return True

    def post(self, request):
        # 1. Cek same-origin sebelum apapun (murah, tidak sentuh DB/OpenAI)
        if not self._is_same_origin(request):
            return JsonResponse(
                {'success': False, 'error': 'Permintaan tidak diizinkan.'},
                status=403,
            )

        # 2. Batasi ukuran body supaya tidak ada DoS via JSON besar
        body = request.body
        if len(body) > self.MAX_BODY_BYTES:
            return JsonResponse(
                {'success': False, 'error': 'Pesan terlalu panjang.'},
                status=413,
            )

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Format data tidak valid.'})

        pesan = data.get('pesan', '').strip()
        sesi_id = data.get('sesi_id', '').strip()
        jenis = data.get('jenis', 'umum')
        chat_token = data.get('chat_token', '').strip()
        honeypot = data.get('website', '')  # field jebakan; harus selalu kosong

        if not pesan:
            return JsonResponse({'success': False, 'error': 'Pesan tidak boleh kosong.'})

        # 3. Honeypot — bot otomatis cenderung mengisi semua field. User asli
        # tidak pernah melihat field ini (CSS hidden + tabindex=-1).
        if honeypot:
            return JsonResponse(
                {'success': False, 'error': 'Permintaan tidak diizinkan.'},
                status=403,
            )

        # 4. Batas panjang pesan
        if len(pesan) > self.MAX_PESAN_CHARS:
            return JsonResponse(
                {'success': False,
                 'error': f'Pesan terlalu panjang (maks {self.MAX_PESAN_CHARS} karakter).'},
                status=413,
            )

        # 5. Verifikasi signed token. Bot yang langsung POST ke API tanpa
        # me-render halaman dulu tidak akan punya token ini.
        ua = request.META.get('HTTP_USER_AGENT', '')
        client_ip = RateLimiter.get_client_ip(request)
        if not verify_chat_token(chat_token, client_ip, ua):
            return JsonResponse(
                {'success': False,
                 'error': 'Sesi chat kadaluarsa. Silakan refresh halaman.'},
                status=403,
            )

        user = request.user if request.user.is_authenticated else None

        # 6. MIN INTERVAL — bunuh request konkuren dari k6/skrip massal.
        # Per IP: tidak boleh ada 2 request <1 dtk dari IP yang sama.
        too_fast, retry_secs = RateLimiter.check_min_interval(
            f"chat_iv_ip_{client_ip}", self.MIN_INTERVAL_PER_IP,
        )
        if too_fast:
            return JsonResponse(
                {'success': False, 'error': 'Terlalu cepat. Silakan tunggu sebentar.'},
                status=429,
            )
        # Per session: anti-flood per percakapan
        if sesi_id:
            too_fast, _ = RateLimiter.check_min_interval(
                f"chat_iv_ses_{sesi_id}", self.MIN_INTERVAL_PER_SESSION,
            )
            if too_fast:
                return JsonResponse(
                    {'success': False, 'error': 'Terlalu cepat. Silakan tunggu sebentar.'},
                    status=429,
                )

        # === LANGKAH 1: RATE LIMIT ===
        is_limited, limit_msg, retry_seconds = RateLimiter.check_chatbot_limit(request, jenis)
        if is_limited:
            respon = f"{limit_msg} Terima kasih atas pengertiannya!"
            return JsonResponse({'success': True, 'respon': respon, 'rate_limited': True, 'retry_seconds': retry_seconds})

        # === LANGKAH 2: SAPAAN → GRATIS (tanpa OpenAI) ===
        if self._is_sapaan(pesan):
            respon = self.SAPAAN_RESPONSE.get(jenis, self.SAPAAN_RESPONSE['umum'])
            self._save_chat(user, None, sesi_id, pesan, respon, True)
            return JsonResponse({'success': True, 'respon': respon})

        # === LANGKAH 3: CARI DATASET MANUAL (keyword) + CHUNK RAG (vector) ===
        matching_datasets = self._find_matching_datasets(pesan, jenis, sesi_id)
        first_match = matching_datasets[0] if matching_datasets else None

        # Vector search ke chunk PDF. Kalau OpenAI embedding gagal atau belum
        # ada dokumen → return [] (graceful fallback ke dataset manual saja).
        matching_chunks = self._find_matching_chunks(pesan, jenis)

        # === LANGKAH 4: CEK BUDGET ===
        has_budget = BudgetLimiter.can_use_ai(BudgetLimiter.COST_CHATBOT)

        if not has_budget:
            if first_match and first_match.respon_jawaban and first_match.respon_jawaban.strip():
                respon = first_match.respon_jawaban
                self._save_chat(user, first_match, sesi_id, pesan, respon, True)
            else:
                respon = "Mohon maaf, layanan AI sedang maintenance. Silakan coba lagi nanti atau hubungi pengurus PK IMM FTIK UMKO."
                self._save_chat(user, None, sesi_id, pesan, respon, False)
            return JsonResponse({'success': True, 'respon': respon})

        # === LANGKAH 5: KIRIM KE OPENAI DENGAN KNOWLEDGE (dataset + RAG) ===
        try:
            knowledge = self._build_knowledge_text(matching_datasets, matching_chunks, jenis)
            chat_history = self._get_chat_history(sesi_id)
            service = OpenAIService()
            # Identifier opaque untuk OpenAI abuse detection (tidak kirim PII)
            if user is not None:
                user_id = f"user_{user.id_user}"
            else:
                user_id = f"ip_{RateLimiter.get_client_ip(request)}"
            respon = service.chatbot_response(
                knowledge, pesan, jenis=jenis, chat_history=chat_history, user_id=user_id,
            )

            BudgetLimiter.add_cost(BudgetLimiter.COST_CHATBOT)

            # Deteksi template penolakan yang dihasilkan AI.
            # Prompt IMM baru memakai "belum memiliki informasi" + "pertanyaan Anda
            # akan kami sampaikan kepada admin" — ini sinyal pasti pertanyaan IMM
            # yang valid tapi datanya belum ada di knowledge base.
            FRASA_TOLAK = [
                'belum memiliki informasi',
                'belum memiliki pengetahuan',
                'pertanyaan anda akan kami sampaikan',
                'tidak bisa membantu untuk hal tersebut',
            ]
            is_unanswerable = any(f in respon.lower() for f in FRASA_TOLAK)

            # Semua pertanyaan yang ditolak AI (dengan template di atas) pasti
            # pertanyaan IMM yang belum ada knowledge-nya — AI sudah menolak topik
            # non-IMM dengan template berbeda ("hanya dapat membantu menjawab...").
            # Tidak perlu notif kalau RAG sudah menyediakan chunk relevan
            # (artinya knowledge sudah ada, AI yang gagal pakai).
            should_notify = is_unanswerable and not first_match and not matching_chunks

            self._save_chat(user, first_match, sesi_id, pesan, respon, not is_unanswerable)

            if should_notify:
                self._notify_admin(user, pesan)

            return JsonResponse({'success': True, 'respon': respon})

        except Exception:
            if first_match and first_match.respon_jawaban and first_match.respon_jawaban.strip():
                respon = first_match.respon_jawaban
                self._save_chat(user, first_match, sesi_id, pesan, respon, True)
            else:
                respon = 'Maaf, layanan sedang tidak tersedia. Silakan coba lagi nanti.'
                self._save_chat(user, None, sesi_id, pesan, respon, False)
            return JsonResponse({'success': True, 'respon': respon})


# ─── Admin: CRUD Dataset Chatbot ──────────────────────────────────────────

class DatasetListView(AdminRequiredMixin, ListView):
    """Daftar entri dataset chatbot dengan filtering."""

    model = DatasetChatbot
    template_name = 'chatbot/dataset_list.html'
    context_object_name = 'dataset_list'
    paginate_by = 10

    def get_queryset(self):
        qs = DatasetChatbot.objects.all()
        jenis = self.request.GET.get('jenis')
        status = self.request.GET.get('status')
        search = self.request.GET.get('q')
        if jenis:
            qs = qs.filter(jenis_chatbot=jenis)
        if status == 'aktif':
            qs = qs.filter(is_active=True)
        elif status == 'nonaktif':
            qs = qs.filter(is_active=False)
        if search:
            qs = qs.filter(
                Q(intent_keyword__icontains=search) | Q(respon_jawaban__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['jenis_filter'] = self.request.GET.get('jenis', '')
        ctx['status_filter'] = self.request.GET.get('status', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['unanswered_questions'] = RiwayatChat.objects.filter(
            is_found=False
        ).order_by('-waktu_chat')[:20]
        return ctx


class DatasetCreateView(AdminRequiredMixin, View):
    """Buat entri dataset baru."""

    template_name = 'chatbot/dataset_form.html'

    def get(self, request):
        keyword = request.GET.get('keyword', '')
        initial = {'intent_keyword': keyword} if keyword else {}
        form = DatasetChatbotForm(initial=initial)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = DatasetChatbotForm(request.POST)
        if form.is_valid():
            dataset = form.save(commit=False)
            dataset.created_by = request.user
            dataset.save()
            messages.success(request, 'Dataset chatbot berhasil ditambahkan.')
            return redirect('chatbot_admin:dataset_list')
        return render(request, self.template_name, {'form': form})


class DatasetUpdateView(AdminRequiredMixin, View):
    """Edit entri dataset yang sudah ada."""

    template_name = 'chatbot/dataset_form.html'

    def get(self, request, pk):
        dataset = get_object_or_404(DatasetChatbot, id_dataset=pk)
        form = DatasetChatbotForm(instance=dataset)
        return render(request, self.template_name, {'form': form, 'dataset': dataset, 'is_edit': True})

    def post(self, request, pk):
        dataset = get_object_or_404(DatasetChatbot, id_dataset=pk)
        form = DatasetChatbotForm(request.POST, instance=dataset)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dataset chatbot berhasil diperbarui.')
            return redirect('chatbot_admin:dataset_list')
        return render(request, self.template_name, {'form': form, 'dataset': dataset, 'is_edit': True})


class DatasetDeleteView(AdminRequiredMixin, View):
    """Hapus entri dataset."""

    def post(self, request, pk):
        dataset = get_object_or_404(DatasetChatbot, id_dataset=pk)
        dataset.delete()
        messages.success(request, 'Dataset chatbot berhasil dihapus.')
        return redirect('chatbot_admin:dataset_list')


class DeleteUnansweredView(AdminRequiredMixin, View):
    """Hapus satu pertanyaan belum terjawab dari riwayat chat."""

    def post(self, request, pk):
        chat = RiwayatChat.objects.filter(id_chat=pk, is_found=False).first()
        if chat:
            chat.delete()
        return redirect('chatbot_admin:dataset_list')


class UnansweredDetailView(AdminRequiredMixin, View):
    """API: riwayat percakapan satu sesi sampai pertanyaan belum terjawab.

    Admin pakai ini untuk melihat konteks sebelum menjawab/menambah dataset.
    Return JSON: { pesan_target, waktu_target, username, chats: [...] }
    """

    MAX_MESSAGES = 20

    def get(self, request, pk):
        target = get_object_or_404(RiwayatChat, id_chat=pk, is_found=False)
        riwayat = (
            RiwayatChat.objects
            .filter(sesi_id=target.sesi_id, waktu_chat__lte=target.waktu_chat)
            .order_by('-waktu_chat')[:self.MAX_MESSAGES]
        )
        chats = []
        for c in reversed(list(riwayat)):
            chats.append({
                'id_chat': c.id_chat,
                'pesan_user': c.pesan_user,
                'respon_bot': c.respon_bot,
                'waktu': c.waktu_chat.strftime('%d %b %Y %H:%M'),
                'is_target': c.id_chat == target.id_chat,
                'is_found': c.is_found,
            })
        return JsonResponse({
            'success': True,
            'pesan_target': target.pesan_user,
            'waktu_target': target.waktu_chat.strftime('%d %b %Y %H:%M'),
            'username': target.id_user.username if target.id_user else 'Publik',
            'total_sesi': RiwayatChat.objects.filter(sesi_id=target.sesi_id).count(),
            'chats': chats,
        })


class DeleteAllUnansweredView(AdminRequiredMixin, View):
    """Hapus semua pertanyaan belum terjawab."""

    def post(self, request):
        RiwayatChat.objects.filter(is_found=False).delete()
        messages.success(request, 'Semua pertanyaan belum terjawab telah dihapus.')
        return redirect('chatbot_admin:dataset_list')


# ─── Admin: CRUD Dokumen Pengetahuan (RAG) ────────────────────────────────

class DokumenListView(AdminRequiredMixin, ListView):
    """Daftar dokumen PDF pengetahuan untuk RAG."""

    model = DokumenPengetahuan
    template_name = 'chatbot/dokumen_list.html'
    context_object_name = 'dokumen_list'
    paginate_by = 10

    def get_queryset(self):
        qs = DokumenPengetahuan.objects.all()
        jenis = self.request.GET.get('jenis')
        status = self.request.GET.get('status')
        search = self.request.GET.get('q')
        if jenis:
            qs = qs.filter(jenis_chatbot=jenis)
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(judul__icontains=search)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['jenis_filter'] = self.request.GET.get('jenis', '')
        ctx['status_filter'] = self.request.GET.get('status', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class DokumenUploadView(AdminRequiredMixin, View):
    """Upload PDF baru → otomatis di-ingest (synchronous)."""

    template_name = 'chatbot/dokumen_form.html'

    def get(self, request):
        form = DokumenPengetahuanForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = DokumenPengetahuanForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        dokumen = form.save(commit=False)
        dokumen.created_by = request.user
        dokumen.status = StatusDokumen.PENDING
        dokumen.save()

        # Synchronous ingest. Untuk PDF besar (~100 halaman) bisa 30-90 detik.
        # Kalau gagal, status sudah di-set FAILED + error_message di service —
        # kita tinggal tampilkan pesan ke admin.
        try:
            jumlah = PDFIngestService().ingest(dokumen)
            messages.success(
                request,
                f'Dokumen berhasil di-upload & diproses ({jumlah} chunk).',
            )
        except OpenAIServiceError as e:
            messages.error(
                request,
                f'Dokumen tersimpan tapi gagal embedding: {e}. '
                f'Anda bisa hapus & upload ulang setelah masalah teratasi.',
            )
        except Exception as e:
            logger.exception('Ingest PDF gagal')
            messages.error(
                request,
                f'Dokumen tersimpan tapi gagal diproses: {e}. '
                f'Cek format PDF (harus text-based, bukan scan).',
            )
        return redirect('chatbot_admin:dokumen_list')


class DokumenToggleActiveView(AdminRequiredMixin, View):
    """Toggle is_active untuk mengaktifkan/menonaktifkan dokumen di RAG."""

    def post(self, request, pk):
        dokumen = get_object_or_404(DokumenPengetahuan, id_dokumen=pk)
        dokumen.is_active = not dokumen.is_active
        dokumen.save(update_fields=['is_active', 'updated_at'])
        status_text = 'diaktifkan' if dokumen.is_active else 'dinonaktifkan'
        messages.success(request, f'Dokumen "{dokumen.judul}" {status_text}.')
        return redirect('chatbot_admin:dokumen_list')


class DokumenReingestView(AdminRequiredMixin, View):
    """Proses ulang dokumen (kalau gagal atau ingin re-embed dengan setting baru)."""

    def post(self, request, pk):
        dokumen = get_object_or_404(DokumenPengetahuan, id_dokumen=pk)
        try:
            jumlah = PDFIngestService().ingest(dokumen)
            messages.success(request, f'Dokumen berhasil diproses ulang ({jumlah} chunk).')
        except Exception as e:
            messages.error(request, f'Gagal proses ulang: {e}')
        return redirect('chatbot_admin:dokumen_list')


class DokumenDeleteView(AdminRequiredMixin, View):
    """Hapus dokumen + file PDF + semua chunk-nya."""

    def post(self, request, pk):
        dokumen = get_object_or_404(DokumenPengetahuan, id_dokumen=pk)
        # Hapus file fisik PDF supaya tidak menumpuk di disk.
        if dokumen.file_pdf:
            dokumen.file_pdf.delete(save=False)
        # Cascade akan hapus ChunkPengetahuan otomatis (FK on_delete=CASCADE).
        dokumen.delete()
        messages.success(request, 'Dokumen pengetahuan berhasil dihapus.')
        return redirect('chatbot_admin:dokumen_list')
