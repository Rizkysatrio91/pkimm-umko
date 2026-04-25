"""Views untuk app chatbot — semua CBV."""
import json

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView

from apps.chatbot.forms import DatasetChatbotForm
from apps.chatbot.models import DatasetChatbot, RiwayatChat
from core.budget_limiter import BudgetLimiter
from core.constants import JenisChatbot
from core.mixins import AdminRequiredMixin, CalonKaderRequiredMixin
from core.rate_limiter import RateLimiter
from core.services import OpenAIService


# ─── Chatbot Publik ───────────────────────────────────────────────────────

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

    def _find_matching_datasets(self, pesan: str, jenis: str, sesi_id: str = '') -> list:
        """
        Cari dataset yang relevan dengan pencarian FLEKSIBEL.

        Metode (dari paling akurat ke paling longgar):
        1. Keyword lengkap ada di pesan → skor TINGGI
        2. Kata-kata keyword cocok dengan kata-kata pesan → skor proporsional
        3. Kata-kata user ditemukan di respon_jawaban → skor tambahan kecil

        Jika pesan sangat pendek (≤2 kata bermakna), konteks diperkaya dengan
        pesan user sebelumnya dari sesi yang sama — sehingga follow-up seperti
        "FTIK" setelah "siapa ketua umum IMM" tetap dapat dicocokkan.
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

    def _build_knowledge_text(self, matching_datasets: list, jenis: str) -> str:
        """
        Bangun teks knowledge untuk dikirim ke OpenAI.
        Gabungkan dataset yang cocok + ringkasan semua topik.
        """
        parts = []

        # Dataset yang paling relevan (maks 5 teratas)
        for i, ds in enumerate(matching_datasets[:5]):
            part = f"[Pengetahuan {i + 1} — topik: {ds.intent_keyword}]"
            if ds.respon_jawaban and ds.respon_jawaban.strip():
                part += f"\n{ds.respon_jawaban}"
            if ds.instruksi_ai and ds.instruksi_ai.strip():
                part += f"\nInstruksi: {ds.instruksi_ai}"
            parts.append(part)

        # Ringkasan semua dataset agar OpenAI tahu topik apa saja yang tersedia
        all_datasets = DatasetChatbot.objects.filter(jenis_chatbot=jenis, is_active=True)
        if all_datasets.exists():
            ringkasan_lines = []
            for ds in all_datasets:
                if ds.respon_jawaban:
                    ringkasan_lines.append(f"- {ds.intent_keyword}: {ds.respon_jawaban[:120]}")
            if ringkasan_lines:
                parts.append("[Daftar Semua Topik yang Tersedia]\n" + "\n".join(ringkasan_lines))

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

        Mencegah cross-site request dari situs jahat yang mencoba
        membakar kuota OpenAI lewat browser user. Kita izinkan request
        tanpa Origin/Referer (mis. curl, health check) — yang diblokir
        hanya kalau header ADA dan host-nya bukan host aplikasi.
        """
        allowed_host = request.get_host()
        origin = request.META.get('HTTP_ORIGIN', '')
        referer = request.META.get('HTTP_REFERER', '')
        for header in (origin, referer):
            if not header:
                continue
            try:
                from urllib.parse import urlparse
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
        sesi_id = data.get('sesi_id', '')
        jenis = data.get('jenis', 'umum')

        if not pesan:
            return JsonResponse({'success': False, 'error': 'Pesan tidak boleh kosong.'})

        user = request.user if request.user.is_authenticated else None

        # === LANGKAH 1: RATE LIMIT ===
        is_limited, limit_msg, retry_seconds = RateLimiter.check_chatbot_limit(request, jenis)
        if is_limited:
            respon = f"{limit_msg} Terima kasih atas pengertiannya!"
            return JsonResponse({'success': True, 'respon': respon})

        # === LANGKAH 2: SAPAAN → GRATIS (tanpa OpenAI) ===
        if self._is_sapaan(pesan):
            respon = self.SAPAAN_RESPONSE.get(jenis, self.SAPAAN_RESPONSE['umum'])
            self._save_chat(user, None, sesi_id, pesan, respon, True)
            return JsonResponse({'success': True, 'respon': respon})

        # === LANGKAH 3: CARI DATASET YANG COCOK (dengan konteks sesi) ===
        matching_datasets = self._find_matching_datasets(pesan, jenis, sesi_id)
        first_match = matching_datasets[0] if matching_datasets else None

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

        # === LANGKAH 5: KIRIM KE OPENAI DENGAN KNOWLEDGE DARI DATASET ===
        try:
            knowledge = self._build_knowledge_text(matching_datasets, jenis)
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
            should_notify = is_unanswerable and not first_match

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
