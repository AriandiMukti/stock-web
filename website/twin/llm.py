"""
Lapisan Claude yang OPSIONAL untuk twin. Mati dengan sendirinya (dan
halaman bilang kenapa) kalau tidak ada kredensial Anthropic.

DUA PEMAKAIAN
1. Penerjemah skenario: teks bebas ("rumor akuisisi BBRI oleh asing, lalu
   dibantah 3 hari kemudian") -> daftar event berskema yang sama dengan
   preset di skenario.py. Hasilnya SELALU ditampilkan dulu di editor event
   untuk diperiksa -- tidak langsung dijalankan.
2. Agen pemimpin: beberapa pemain besar (satu dana asing, satu institusi
   lokal, tiap bandar) berkonsultasi ke Claude tiap K hari bursa dengan
   ringkasan kondisi pasar, lalu memilih sikap dari daftar tertutup. Ribuan
   agen lain tetap memakai aturan.

HARGA KEJUJURAN AGEN PEMIMPIN
Keputusan model bahasa tidak bisa diulang persis, jadi dunia baseline dan
skenario TIDAK lagi identik di luar skenarionya -- selisihnya ikut memuat
"suasana hati" pemimpin. Itu sebabnya jumlah run dibatasi, konsultasi
jarang, dan halaman menandai run semacam ini. Tiap konsultasi juga
berbayar; perkiraan jumlah panggilan ditulis di log sebelum mulai.

TEKNIS
Model claude-opus-5-5, keluaran JSON terstruktur lewat output_config.format
(model ini tidak menerima tool_choice paksa), effort ditulis eksplisit,
fallback sisi server "default" untuk penolakan keamanan.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

MODEL = 'claude-opus-5-5'
BETA_FALLBACK = 'server-side-fallback-2026-07-01'
TIMEOUT_DETIK = 120.0

# sikap yang boleh dipilih pemimpin -- daftar tertutup, dipetakan ke perilaku
SIKAP_DANA = ('beli_kuat', 'beli', 'netral', 'jual', 'jual_kuat')
NILAI_SIKAP = {'beli_kuat': 2.0, 'beli': 1.0, 'netral': 0.0, 'jual': -1.0, 'jual_kuat': -2.0}
SIKAP_BANDAR = ('tunggu', 'akumulasi', 'markup', 'distribusi', 'buang')


# --------------------------------------------------------------- status
def _ada_kredensial():
    if os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN'):
        return True, 'variabel lingkungan'
    if os.environ.get('ANTHROPIC_PROFILE'):
        return True, 'profil %s' % os.environ['ANTHROPIC_PROFILE']
    # profil `ant auth login` disimpan di ~/.config/anthropic/
    dasar = os.path.join(os.path.expanduser('~'), '.config', 'anthropic')
    if os.path.isdir(dasar) and any(os.scandir(dasar)):
        return True, 'profil ant auth login'
    return False, None


def status():
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return {'aktif': False, 'model': MODEL, 'alasan': 'Paket anthropic belum terpasang (pip install anthropic).'}
    ada, sumber = _ada_kredensial()
    if not ada:
        return {'aktif': False, 'model': MODEL,
                'alasan': 'Belum ada kredensial Claude. Set ANTHROPIC_API_KEY di lingkungan server '
                          '(atau jalankan `ant auth login`), lalu muat ulang halaman.'}
    return {'aktif': True, 'model': MODEL, 'alasan': 'Kredensial dari %s.' % sumber}


# --------------------------------------------------------------- panggil
class GalatLLM(RuntimeError):
    """Galat yang pesannya aman ditampilkan ke pengguna apa adanya."""


def _klien():
    import anthropic
    return anthropic.Anthropic(timeout=TIMEOUT_DETIK, max_retries=2)


def panggil_json(system, pengguna, skema, effort='medium', max_tokens=16000):
    """Satu permintaan ke Claude dengan keluaran JSON berskema. Return dict.

    Diganti oleh tes (lihat _uji_tiruan) -- semua pemakaian di modul ini
    lewat fungsi ini, jadi satu tempat untuk ditiru."""
    import anthropic
    st = status()
    if not st['aktif']:
        raise GalatLLM(st['alasan'])
    try:
        resp = _klien().beta.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            betas=[BETA_FALLBACK],
            fallbacks='default',
            system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
            messages=[{'role': 'user', 'content': pengguna}],
            output_config={'effort': effort,
                           'format': {'type': 'json_schema', 'schema': skema}},
        )
    except anthropic.AuthenticationError:
        raise GalatLLM('Kunci API Claude ditolak (tidak sah atau kedaluwarsa).')
    except anthropic.PermissionDeniedError:
        raise GalatLLM('Kunci API Claude tidak punya izin untuk model %s.' % MODEL)
    except anthropic.NotFoundError:
        raise GalatLLM('Model %s tidak ditemukan untuk akun ini.' % MODEL)
    except anthropic.RateLimitError:
        raise GalatLLM('Batas laju Claude tercapai. Coba lagi sebentar lagi.')
    except anthropic.BadRequestError as exc:
        raise GalatLLM('Permintaan ke Claude ditolak: %s' % getattr(exc, 'message', exc))
    except anthropic.APIStatusError as exc:
        raise GalatLLM('Server Claude bermasalah (%s). Coba lagi nanti.' % exc.status_code)
    except anthropic.APITimeoutError:
        raise GalatLLM('Claude tidak menjawab dalam %.0f detik.' % TIMEOUT_DETIK)
    except anthropic.APIConnectionError:
        raise GalatLLM('Tidak bisa menghubungi Claude (jaringan).')

    if resp.stop_reason == 'refusal':
        kat = getattr(getattr(resp, 'stop_details', None), 'category', None)
        raise GalatLLM('Claude menolak permintaan ini%s.' % (' (kategori %s)' % kat if kat else ''))
    if resp.stop_reason == 'max_tokens':
        raise GalatLLM('Jawaban Claude terpotong (max_tokens). Persingkat teks skenarionya.')
    teks = next((b.text for b in resp.content if b.type == 'text'), None)
    if not teks:
        raise GalatLLM('Claude tidak mengembalikan teks.')
    try:
        return json.loads(teks)
    except ValueError:
        raise GalatLLM('Jawaban Claude bukan JSON yang sah.')


# --------------------------------------------------- penerjemah skenario
def _skema_skenario():
    from .skenario import JENIS
    return {
        'type': 'object',
        'properties': {
            'judul': {'type': 'string', 'description': 'Judul pendek skenario, maks 8 kata.'},
            'ringkasan': {'type': 'string', 'description': 'Satu-dua kalimat: apa yang disimulasikan.'},
            'events': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'hari': {'type': 'integer', 'description': 'Hari bursa ke-berapa (0 = hari pertama rekaman).'},
                        'jenis': {'type': 'string', 'enum': list(JENIS.keys())},
                        'target': {'type': 'string', 'description': "'semua', 'sektor:<nama sektor>', atau satu kode saham dari daftar."},
                        'besar': {'type': 'number'},
                        'durasi': {'type': 'integer', 'description': 'Lama efek dalam hari bursa (>= 1).'},
                        'bantah_hari': {'type': 'integer', 'description': 'Khusus rumor_akuisisi: dibantah sekian hari setelahnya; 0 = tidak dibantah.'},
                        'pola': {'type': 'string', 'enum': ['asumsi', 'jan2026', 'jun2026'],
                                 'description': "Khusus msci: 'jan2026'/'jun2026' memutar ulang episode MSCI nyata; selain msci isi 'asumsi'."},
                        'alasan': {'type': 'string', 'description': 'Kenapa besaran ini dipilih, satu kalimat.'},
                    },
                    'required': ['hari', 'jenis', 'target', 'besar', 'durasi', 'bantah_hari', 'pola', 'alasan'],
                    'additionalProperties': False,
                },
            },
            'asumsi': {'type': 'array', 'items': {'type': 'string'},
                       'description': 'Asumsi yang terpaksa dibuat karena teksnya tidak menyebutkan.'},
        },
        'required': ['judul', 'ringkasan', 'events', 'asumsi'],
        'additionalProperties': False,
    }


def _system_penerjemah():
    from .skenario import JENIS
    jenis = '\n'.join('- %s (%s): besar = %s. %s' % (k, v['label'], v['besar'], v['arti']) for k, v in JENIS.items())
    return (
        'Kamu menerjemahkan skenario pasar saham Indonesia yang ditulis bebas menjadi jadwal '
        'guncangan untuk sebuah "digital twin" Bursa Efek Indonesia: simulasi berbasis agen '
        '(ritel, institusi lokal, asing, bandar, pedagang cepat) yang membandingkan dunia tanpa '
        'skenario dengan dunia yang diberi skenario.\n\n'
        'Jenis guncangan yang tersedia (pakai HANYA ini):\n' + jenis + '\n\n'
        'Aturan:\n'
        '- Satu kejadian di teks bisa menjadi beberapa event (mis. kenaikan bunga + asing keluar).\n'
        '- Hari 0 adalah hari pertama yang direkam. Kalau teks tidak menyebut waktu, mulai di hari 10 '
        'supaya ada pembanding sebelum guncangan.\n'
        '- Target hanya boleh "semua", "sektor:<nama sektor persis dari daftar>", "@msci" (perkiraan '
        'anggota indeks MSCI, untuk jenis msci), atau kode saham dari daftar yang diberikan. Saham yang tidak ada di daftar tidak bisa disimulasikan: tulis '
        'di asumsi, jangan diganti diam-diam.\n'
        '- Besaran harus sebanding dengan bahasa teks: "sedikit" kecil, "besar-besaran"/"anjlok" besar. '
        'Pakai satuan yang tertulis di tiap jenis.\n'
        '- Jangan mengarang kejadian yang tidak disebut. Kalau teksnya ambigu, pilih tafsiran paling '
        'wajar dan catat di asumsi.\n'
        '- Ini alat bagaimana-jika, bukan ramalan: jangan menambahkan klaim tentang arah pasar asli.'
    )


def terjemahkan(teks, kodes, hari):
    """Teks bebas -> {'judul','ringkasan','events','asumsi','peringatan'}.
    Event sudah diperiksa dengan aturan yang sama dengan preset."""
    from . import kalibrasi
    from .skenario import siapkan
    teks = (teks or '').strip()
    if len(teks) > 4000:
        raise GalatLLM('Teks skenario terlalu panjang (maks 4.000 karakter).')
    kodes = [k.strip().upper() for k in kodes if k.strip()] or list(kalibrasi.BAWAAN)
    sektor = kalibrasi.peta_sektor()
    daftar = '\n'.join('- %s (sektor %s)' % (k, sektor.get(k, '-')) for k in kodes)
    pengguna = ('Saham yang disimulasikan:\n%s\n\nPanjang simulasi: %d hari bursa (hari 0-%d).\n\n'
                'Skenario:\n"""%s"""' % (daftar, hari, hari - 1, teks))
    t0 = time.time()
    hasil = panggil_json(_system_penerjemah(), pengguna, _skema_skenario(), effort='medium')

    # periksa dengan aturan preset (profil ringan: cukup sektor & kapitalisasi)
    events = []
    for ev in hasil.get('events') or []:
        ev = dict(ev)
        if not ev.get('bantah_hari'):
            ev.pop('bantah_hari', None)
        if ev.get('jenis') != 'msci':
            ev.pop('pola', None)
        events.append(ev)
    prof = _profil_ringan(kodes, sektor)
    bersih, peringatan = siapkan(events, prof, kodes, hari)
    for e in bersih:
        e.pop('target_kode', None)
        e.pop('id', None)
    return {
        'judul': hasil.get('judul') or 'Skenario dari teks',
        'ringkasan': hasil.get('ringkasan') or '',
        'events': bersih,
        'asumsi': hasil.get('asumsi') or [],
        'peringatan': peringatan,
        'model': MODEL,
        'detik': round(time.time() - t0, 1),
    }


def _profil_ringan(kodes, sektor):
    """Cukup untuk siapkan(): sektor & kapitalisasi (untuk penanda @besar dkk)."""
    from . import kalibrasi
    ksei = kalibrasi.ksei_terbaru() or {'securities': {}}
    saham = {}
    for k in kodes:
        rec = ksei['securities'].get(k) or {}
        saham[k] = {'sektor': sektor.get(k, '-'), 'adv_nilai': 1.0,
                    'pemilik': {'mcap': float(rec.get('sec_num') or 0) * float(rec.get('price') or 0)}}
    return {'saham': saham}


# ------------------------------------------------------- agen pemimpin
def _skema_dana(kodes):
    return {
        'type': 'object',
        'properties': {
            'sikap': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'kode': {'type': 'string', 'enum': list(kodes)},
                        'sikap': {'type': 'string', 'enum': list(SIKAP_DANA)},
                    },
                    'required': ['kode', 'sikap'],
                    'additionalProperties': False,
                },
            },
            'alasan': {'type': 'string', 'description': 'Satu-dua kalimat.'},
        },
        'required': ['sikap', 'alasan'],
        'additionalProperties': False,
    }


SKEMA_BANDAR = {
    'type': 'object',
    'properties': {
        'langkah': {'type': 'string', 'enum': list(SIKAP_BANDAR)},
        'alasan': {'type': 'string', 'description': 'Satu-dua kalimat.'},
    },
    'required': ['langkah', 'alasan'],
    'additionalProperties': False,
}

PERAN = {
    'asing': ('Kamu adalah manajer dana asing besar yang memegang saham-saham Indonesia di dalam '
              'sebuah simulasi pasar. Kamu memutuskan sikap untuk beberapa hari bursa ke depan per '
              'saham. Sikapmu dieksekusi bertahap; dana sebesarmu menggerakkan harga.'),
    'institusi': ('Kamu adalah manajer investasi lokal besar (dana pensiun/reksa dana) di dalam sebuah '
                  'simulasi pasar. Kamu memutuskan sikap untuk beberapa hari bursa ke depan per saham, '
                  'dengan mandat jangka panjang dan batas risiko.'),
    'bandar': ('Kamu adalah bandar di satu saham lapis bawah di dalam sebuah simulasi pasar. Kamu '
               'memutuskan langkah berikutnya dalam siklusmu: tunggu, akumulasi diam-diam, markup '
               '(angkat harga), distribusi (jual ke pengejar), atau buang (keluar cepat).'),
}


def putuskan_pemimpin(daftar):
    """daftar: [{'jenis','ringkasan','kodes'}] -> daftar keputusan dengan urutan
    sama. Dijalankan paralel (paling banyak 4 sekaligus). Galat satu pemimpin
    tidak menghentikan yang lain: keputusannya None dan pemimpin itu kembali
    ke aturan bawaan sampai konsultasi berikutnya."""
    def satu(item):
        jenis = item['jenis']
        system = (PERAN[jenis] + '\n\nYang kamu terima adalah ringkasan kondisi simulasi, bukan pasar '
                  'asli. Jawab hanya dengan keputusan berskema. Tidak ada informasi lain yang tersedia.')
        skema = SKEMA_BANDAR if jenis == 'bandar' else _skema_dana(item['kodes'])
        try:
            return panggil_json(system, json.dumps(item['ringkasan'], ensure_ascii=False),
                                skema, effort='low', max_tokens=4000)
        except GalatLLM as exc:
            return {'galat': str(exc)}
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(daftar)))) as ex:
        return list(ex.map(satu, daftar))
