"""
Ramai Dibahas: emiten yang lagi banyak diomongin di Stream Stockbit dan
forum Telegram. Bahan PEMANTAUAN, bukan sinyal beli -- belum pernah diuji.

KENAPA HATI-HATI (lihat riset berita akuisisi): kabar yang ramai biasanya
ketemu SETELAH harga lari (pre-return +18%), dan beli sesudah berita
menurunkan win rate. Karena itu tabel menampilkan "sudah naik 5 hari"
di sebelah jumlah obrolan, dan ramai_dibahas_harian.csv mencatat bacaan
harian supaya nanti bisa diuji maju -- jangan dianggap terbukti sebelum itu.

SUMBER
  Stockbit  halaman publik stockbit.com/symbol/<EMITEN> sudah memuat 30
            post terbaru tanpa login (lewat rute data Next.js, ~0,3 detik
            per emiten). Tiap post membawa `topics` = daftar emiten yang
            di-tag, jadi tidak perlu menebak ticker dari teks.
            BATAS: cuma 30 post terakhir per emiten. Emiten yang ramai
            menghabiskan 30 post dalam beberapa jam -> jumlahnya JENUH.
            Untuk itu laju = 30 / rentang waktu 30 post itu, diskalakan ke
            24 jam (kolom "~perkiraan"). Menarik lebih sering (mis. tiap jam
            saat bursa buka) mengisi celahnya karena post ditumpuk per id.
  Telegram  (a) channel PUBLIK lewat pratinjau t.me/s/<nama>, tanpa login.
            (b) GRUP (forum diskusi biasanya grup, bukan channel) lewat
                Telethon dengan akun Telegram sendiri -- opsional, perlu
                TELEGRAM_API_ID & TELEGRAM_API_HASH (my.telegram.org) di
                .env BDM lalu sekali `python -m website.ramai_dibahas
                --login-telegram`.
            Ticker ditebak dari teks: $BBCA/#BBCA selalu dihitung; bbca/BBCA
            polos (huruf besar ATAU kecil) dihitung kalau ada di semesta
            Summary dan bukan kata umum (AMBIGU: naik, pada, beli, cuan, ...).
            Huruf kecil ikut dihitung karena di grup obrolan (Group Belajar
            Saham+, 15 Okt) tak satu pun pesan memakai $ dan ticker ditulis
            `bbca`, `dssa`. AMBIGU diambil dari data: kode emiten yang paling
            sering muncul huruf kecil TANPA $ di ~20 ribu post Stockbit --
            di sana ticker asli hampir selalu di-tag $, jadi sisanya kata biasa.
            Pesan yang sama diteruskan ke banyak grup dihitung sekali.
            Post/pesan yang menyebut > MAKS_TAG emiten (rekap IHSG dari portal
            berita, spam tag) dibuang -- ~4% baris di tarikan pertama.

Cara pakai: tombol "Tarik sekarang" di /ramai-dibahas, atau
    python -m website.ramai_dibahas            (dari <project>/)
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import argparse
import asyncio
import hashlib
import json
import logging
import os
import pickle
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .config import DAILY_PATH

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
SUMBER_FILE = str(_runtime_file('', 'ramai_dibahas_sumber.json'))
SEBUTAN_FILE = str(_runtime_file('', 'ramai_dibahas_sebutan.pkl'))
HARIAN_FILE = str(_runtime_file('', 'ramai_dibahas_harian.csv'))
TG_SESSION = str(_runtime_file('', 'ramai_dibahas_telegram'))      # Telethon menambah .session
BDM_ENV = str(_RUNTIME_DIR / "secrets" / "provider.env")
SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')

SIMPAN_HARI = 30          # sebutan lebih tua dari ini dibuang dari tumpukan
TG_MUNDUR_JAM = 48        # Telegram ditarik mundur sejauh ini tiap kali
TG_MAKS_HALAMAN = 15      # per channel publik, 20 pesan per halaman
PEKERJA = 6
JENDELA_JAM = 24
MAKS_TAG = 5              # post/pesan yang menyebut > ini emiten = rekap pasar / spam tag, tidak dihitung
BASELINE_HARI = 7
TTL = 600
WIB = 'Asia/Jakarta'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'}

# Kode emiten yang juga kata biasa -- polos (tanpa $/#) tidak dihitung,
# huruf besar maupun kecil. Baris 1-3: dari data Stockbit (lihat docstring);
# sisanya kata Indonesia/Inggris lain yang kebetulan kode emiten.
AMBIGU = set('''
NAIK PADA BELI AREA SATU SINI MAIN CUAN BAIK LABA UANG BANK DATA KING BUKA AMAN TRUS ENAK AKSI POLA BACA
EMAS AGAR CASH MARI GOOD INDO ASLI AYAM REAL LIVE BLUE DAYA GUNA BEST PLAN VIVA OBAT COAL RAJA HOKI AUTO
IKAN NASI RELI PADI KOTA BULL GOLD KOPI JAYA HALO ZONE PURA BUAH GULA MANG NICE FILM MEJA AWAN JELI GEMS
BABY BAJA BALI BATA BEEF BEER BIKE BIRD BOAT BOLA BOSS BUDI CARE CARS CHIP CITA CITY COIN DEAL DEFI DEWI
DUCK EAST EDGE FAST FIRE FISH FOOD GAMA GOLF HERO HOME HOPE IDEA JAVA JAWA JATI KAYU KOIN LAJU LAND LEAD
LIFE LINK LION LUCK LUCY MARK MAYA MEGA META MINA MINE MUTU NANO NINE OILS PACK PALM PART POOL PORT PURE
RATU RISE ROCK RODA ROTI SAFE SAGE SAME SOUL STAR SURE SURI TAXI TECH TOOL TOYS TRUE TRUK UNIT VISI WINE
WINS ZINC WIFI YELO NUSA AIMS DADA FORE YOII
'''.split())
POLA_TAG = re.compile(r'[$#]([A-Za-z]{4})(?![A-Za-z])')
POLA_POLOS = re.compile(r'(?<![A-Za-z0-9$#])([A-Za-z]{4})(?![A-Za-z0-9])')

# Sentimen = kamus kata, bukan model. Dibangun dari kata yang paling sering
# di ~27 ribu post tumpukan (25 Okt 2026) + kamus riset_sentimen_obrolan.
# Kasar: sarkasme dan pertanyaan ("kapan naik?") tidak terbaca, dan ~70%
# post tidak memuat kata mana pun (netral). Riset komen negatif -> IHSG
# (19 Okt) GAGAL -- negativitas cuma ikut harga hari itu -- jadi skor ini
# deskripsi suasana, bukan sinyal. Sengaja TIDAK dipakai: tp (= "tapi"),
# buy/sell (template bot laporan KSEI), tembus/cabut/suspend (dua arah),
# down ("avg down" = nambah beli), cl/sl (ikut muncul di template trading plan).
SENT_POS = set('''
naik naikin kenaikan ara arakan cuan profit untung rebound mantul terbang ijo hijau bullish akumulasi akum borong
serok haka hajar gas meroket melesat breakout uptrend gacor moon pantul mantap mantab menguat rally reli bagus
menarik kuat murah diskon mumpung tampung jemput positif berhasil semangat sehat alhamdulillah ath moncer
'''.split())
SENT_NEG = set('''
turun anjlok longsor ambruk ambrol jeblok nyungsep rontok crash dump dumping merah memerah kebakaran berdarah
bloodbath arb nyangkut boncos rugi loss cutloss panik panic takut hancur ancur rungkad nangis terjun koreksi bearish
guyur diguyur distribusi kabur nyerah stres stress sedih amblas ambles tenggelam downtrend breakdown jebol minus
nyangsang mewek kapok trauma kiamat resesi krisis collapse nyesel nyesal apes sial zonk tipu scam pompom junam
jualan buang badai parah kalah miskin nyelam amburadul tertekan ambyar
'''.split())
# "naikkk", "gasss", "cuannn": dicocokkan juga setelah huruf berulang diringkas.
_RINGKAS = lambda w: re.sub(r'(.)\1+', r'\1', w)
SENT_KATA = {**{_RINGKAS(w): -1 for w in SENT_NEG}, **{w: -1 for w in SENT_NEG},
             **{_RINGKAS(w): 1 for w in SENT_POS}, **{w: 1 for w in SENT_POS}}
SENT_NEGASI = set('tidak tak gak ga nggak ngga enggak gk ndak belum blm bukan jangan jgn gausah'.split())
SENT_EMO = {e: -1 for e in '😭😱💀🩸📉😢😰😩😫🥲🤬😡'}
SENT_EMO.update({e: 1 for e in '🚀📈🔥💰🤑😍🥳'})
POLA_KATA = re.compile(r'[a-z]+')
HARI = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']

KOLOM = ['sumber', 'kanal', 'post_id', 'waktu', 'ticker', 'penulis', 'suka', 'balas',
         'tayang', 'sidik', 'cuplikan', 'url']

_STATUS = {'jalan': False, 'tahap': '', 'selesai': 0, 'total': 0, 'mulai': None, 'galat': None}
_KUNCI = threading.Lock()
_CACHE = {'ts': 0, 'data': None}


# ------------------------------------------------------------------ bantu
def _sekarang():
    return pd.Timestamp.now(tz=WIB).tz_localize(None)


def _semesta():
    if not os.path.isdir(SUMMARY_DIR):
        return set()
    return {n[:-len('_Summary.csv')] for n in os.listdir(SUMMARY_DIR) if n.endswith('_Summary.csv')}


def _env():
    """os.environ menang atas .env BDM (tempat STOCKBIT_TOKEN juga disimpan)."""
    cfg = {}
    if os.path.exists(BDM_ENV):
        with open(BDM_ENV, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg.update({k: v for k, v in os.environ.items() if k.startswith('TELEGRAM_')})
    return cfg


def _rapikan_kanal(s):
    s = s.strip()
    s = re.sub(r'^(https?://)?(t\.me|telegram\.me)/(s/)?', '', s)
    return s.lstrip('@').strip('/').strip()


def baca_sumber():
    try:
        with open(SUMBER_FILE, encoding='utf-8') as fh:
            d = json.load(fh)
    except Exception:
        d = {}
    return {'telegram_publik': d.get('telegram_publik', []), 'telegram_grup': d.get('telegram_grup', [])}


def simpan_sumber(publik, grup):
    """`publik` -> nama channel saja; `grup` disimpan apa adanya (bisa judul grup)."""
    publik = [k for k in dict.fromkeys(_rapikan_kanal(x) for x in publik) if k]
    grup = [g for g in dict.fromkeys(x.strip() for x in grup) if g]
    with open(SUMBER_FILE, 'w', encoding='utf-8') as fh:
        json.dump({'telegram_publik': publik, 'telegram_grup': grup}, fh, ensure_ascii=False, indent=1)
    return baca_sumber()


def cari_ticker(teks, semesta):
    """Emiten yang disebut di teks bebas (Telegram). Urutan pertama muncul."""
    hasil = []
    for m in POLA_TAG.finditer(teks):
        t = m.group(1).upper()
        if t in semesta:
            hasil.append(t)
    for m in POLA_POLOS.finditer(teks):
        t = m.group(1).upper()
        if t in semesta and t not in AMBIGU:
            hasil.append(t)
    return list(dict.fromkeys(hasil))


def _sidik(teks):
    norm = re.sub(r'\s+', ' ', re.sub(r'https?://\S+', '', teks.lower())).strip()[:300]
    return hashlib.md5(norm.encode('utf-8')).hexdigest()[:12]


def sentimen(teks):
    """+1 positif, -1 negatif, 0 netral/seimbang. Dua kata sesudah negasi dibalik ("gak naik" = negatif)."""
    t = POLA_TAG.sub(' ', str(teks or '')).lower()      # $CUAN itu emiten, bukan "cuan"
    skor, balik = 0, 0          # balik = sisa kata yang masih kena negasi ("gak mungkin rontok")
    for w in POLA_KATA.findall(t):
        k = SENT_KATA.get(w) or SENT_KATA.get(_RINGKAS(w))
        if k:
            skor += -k if balik else k
            balik = 0
        balik = 2 if w in SENT_NEGASI else max(balik - 1, 0)
    skor += sum(t.count(e) * k for e, k in SENT_EMO.items())
    return (skor > 0) - (skor < 0)


def _angka_tayang(s):
    s = (s or '').strip().upper().replace(',', '.')
    try:
        if s.endswith('K'):
            return int(float(s[:-1]) * 1e3)
        if s.endswith('M'):
            return int(float(s[:-1]) * 1e6)
        return int(float(s))
    except ValueError:
        return None


def _progres(tahap=None, tambah=0, total=None):
    with _KUNCI:
        if tahap is not None:
            _STATUS['tahap'] = tahap
        if total is not None:
            _STATUS['total'], _STATUS['selesai'] = total, 0
        _STATUS['selesai'] += tambah


# --------------------------------------------------------------- Stockbit
_lokal = threading.local()


def _scraper():
    if not hasattr(_lokal, 's'):
        import cloudscraper
        _lokal.s = cloudscraper.create_scraper()
    return _lokal.s


def _build_id():
    r = _scraper().get('https://stockbit.com/symbol/BBCA', timeout=30)
    r.raise_for_status()
    m = re.search(r'"buildId":"([^"]+)"', r.text)
    if not m:
        raise RuntimeError('buildId Stockbit tidak ketemu -- tata letak halaman berubah?')
    return m.group(1)


def _post_stockbit(ticker, build):
    """30 post terbaru di stream emiten. None kalau gagal (build basi -> 404)."""
    url = 'https://stockbit.com/_next/data/%s/symbol/%s.json' % (build, ticker)
    for coba in range(3):
        try:
            r = _scraper().get(url, timeout=30, headers={'Accept': 'application/json'})
        except Exception:
            time.sleep(2 * (coba + 1))
            continue
        if r.status_code == 429:
            time.sleep(5 * (coba + 1))
            continue
        if r.status_code == 404:
            return None
        if not r.ok:
            return []
        try:
            return (r.json().get('pageProps') or {}).get('posts') or []
        except ValueError:
            return []
    return []


def _baris_stockbit(posts, semesta):
    baris = []
    for p in posts:
        try:
            waktu = pd.Timestamp(p['created'])
        except Exception:
            continue
        teks = (p.get('content_original') or p.get('content') or '').strip()
        topik = list(dict.fromkeys(t.upper() for t in (p.get('topics') or []) if t and t.upper() in semesta))
        if len(topik) > MAKS_TAG:
            continue
        for t in topik:
            baris.append({
                'sumber': 'stockbit', 'kanal': 'Stockbit', 'post_id': 'sb:%s' % p.get('postid'),
                'waktu': waktu, 'ticker': t, 'penulis': p.get('username') or '',
                'suka': int(p.get('likes') or 0), 'balas': int(p.get('replies') or 0), 'tayang': None,
                'sidik': _sidik(teks), 'cuplikan': teks[:280],
                'url': 'https://stockbit.com/post/%s' % p.get('postid'),
            })
    return baris


def tarik_stockbit(semesta):
    """Semua emiten di semesta. -> (baris sebutan, jangkauan per emiten)."""
    daftar = sorted(semesta)
    _progres('Stockbit', total=len(daftar))
    build = [_build_id()]
    jangkauan, baris = {}, []

    def satu(t):
        posts = _post_stockbit(t, build[0])
        if posts is None:          # build berganti di tengah jalan
            build[0] = _build_id()
            posts = _post_stockbit(t, build[0]) or []
        _progres(tambah=1)
        return t, posts

    with ThreadPoolExecutor(PEKERJA) as ex:
        for t, posts in ex.map(satu, daftar):
            waktu = [pd.Timestamp(p['created']) for p in posts if p.get('created')]
            jangkauan[t] = {'n': len(posts), 'tertua': min(waktu) if waktu else None}
            baris.extend(_baris_stockbit(posts, semesta))
    return baris, jangkauan


# --------------------------------------------------- Telegram channel publik
def _halaman_channel(kanal, sebelum=None):
    import requests
    from .html_parser import parse_html, fetch_html
    url = 'https://t.me/s/%s' % kanal + ('?before=%d' % sebelum if sebelum else '')
    soup = parse_html(fetch_html(url, timeout=(4, 12), headers=UA))
    pesan = []
    for m in soup.css('.tgme_widget_message[data-post]'):
        kunci = m.attributes['data-post']
        jam = m.css_first('time[datetime]')
        if not jam:
            continue
        isi = m.css_first('.tgme_widget_message_text')
        tayang = m.css_first('.tgme_widget_message_views')
        pesan.append({
            'id': int(kunci.rsplit('/', 1)[1]),
            'waktu': pd.Timestamp(jam.attributes['datetime']).tz_convert(WIB).tz_localize(None),
            'teks': isi.text(separator=' ', strip=True) if isi else '',
            'tayang': _angka_tayang(tayang.text()) if tayang else None,
            'url': 'https://t.me/%s' % kunci,
        })
    return pesan


def _baris_telegram(sumber, kanal, post_id, waktu, teks, penulis, tayang, url, semesta):
    tk = cari_ticker(teks, semesta)
    if len(tk) > MAKS_TAG:
        return []
    sidik = _sidik(teks)
    return [{'sumber': sumber, 'kanal': kanal, 'post_id': post_id, 'waktu': waktu, 'ticker': t,
             'penulis': penulis, 'suka': 0, 'balas': 0, 'tayang': tayang, 'sidik': sidik,
             'cuplikan': teks[:280], 'url': url} for t in tk]


def tarik_telegram_publik(kanal_list, semesta, sejak):
    baris, status = [], {}
    _progres('Telegram publik', total=len(kanal_list))
    for kanal in kanal_list:
        try:
            sebelum, n_pesan, ada = None, 0, True
            for _ in range(TG_MAKS_HALAMAN):
                pesan = _halaman_channel(kanal, sebelum)
                if pesan is None:
                    ada = False
                    break
                if not pesan:
                    break
                for p in pesan:
                    if p['waktu'] >= sejak:
                        n_pesan += 1
                        baris.extend(_baris_telegram('telegram', kanal, 'tg:%s/%d' % (kanal, p['id']), p['waktu'],
                                                     p['teks'], kanal, p['tayang'], p['url'], semesta))
                if min(p['waktu'] for p in pesan) < sejak:
                    break
                sebelum = min(p['id'] for p in pesan)
                time.sleep(0.5)
            status[kanal] = ({'status': 'ok', 'pesan': n_pesan} if ada else
                             {'status': 'bukan channel publik -- kalau ini grup, pindahkan ke daftar Grup'})
        except Exception as exc:
            status[kanal] = {'status': 'gagal: %s' % exc}
        _progres(tambah=1)
    return baris, status


# ------------------------------------------------------- Telegram grup (Telethon)
def _kredensial_tg():
    e = _env()
    return e.get('TELEGRAM_API_ID', '').strip(), e.get('TELEGRAM_API_HASH', '').strip()


def tarik_telegram_grup(grup_list, semesta, sejak):
    if not grup_list:
        return [], {}
    try:
        from telethon import TelegramClient
    except ImportError:
        return [], {g: {'status': 'Telethon belum terpasang: pip install telethon'} for g in grup_list}
    api_id, api_hash = _kredensial_tg()
    if not api_id or not api_hash:
        return [], {g: {'status': 'TELEGRAM_API_ID / TELEGRAM_API_HASH belum ada di %s' % BDM_ENV} for g in grup_list}
    if not os.path.exists(TG_SESSION + '.session'):
        return [], {g: {'status': 'belum login: python -m website.ramai_dibahas --login-telegram'} for g in grup_list}
    sejak_utc = pd.Timestamp(sejak).tz_localize(WIB).tz_convert('UTC')
    _progres('Telegram grup', total=len(grup_list))

    async def jalan():
        baris, status = [], {}
        # Session Telethon = berkas SQLite. Dua proses (mis. dua Flask main.py,
        # atau CLI + tombol) tidak bisa memakainya bersamaan: 'database is
        # locked'. Tunggu sebentar, lalu menyerah dengan pesan yang terbaca.
        for coba in range(6):
            client = TelegramClient(TG_SESSION, int(api_id), api_hash)
            try:
                await client.connect()
                break
            except sqlite3.OperationalError:
                await asyncio.sleep(5)
        else:
            return [], {g: {'status': 'sesi Telegram sedang dipakai proses lain (dua Flask jalan?) -- coba lagi'}
                        for g in grup_list}
        try:
            if not await client.is_user_authorized():
                return [], {g: {'status': 'sesi login kedaluwarsa: ulangi --login-telegram'} for g in grup_list}
            dialog = None
            for g in grup_list:
                try:
                    try:
                        ent = await client.get_entity(g)
                    except Exception:
                        # Grup privat tanpa username: cocokkan judul di daftar obrolan sendiri.
                        if dialog is None:
                            dialog = [d async for d in client.iter_dialogs()]
                        cocok = [d for d in dialog if (d.name or '').strip().lower() == g.strip().lower()]
                        if not cocok:
                            raise ValueError('tidak ketemu -- pakai @username, link t.me, atau judul persis grupnya')
                        ent = cocok[0].entity
                    nama = getattr(ent, 'username', None) or getattr(ent, 'title', None) or g
                    n = 0
                    async for m in client.iter_messages(ent, limit=5000):
                        if m.date is None:
                            continue
                        if pd.Timestamp(m.date) < sejak_utc:
                            break
                        teks = m.message or ''
                        if not teks:
                            continue
                        n += 1
                        waktu = pd.Timestamp(m.date).tz_convert(WIB).tz_localize(None)
                        un = getattr(ent, 'username', None)
                        url = 'https://t.me/%s/%d' % (un, m.id) if un else ''
                        baris.extend(_baris_telegram('telegram', nama, 'tg:%s/%d' % (ent.id, m.id), waktu, teks,
                                                     str(m.sender_id or ''), getattr(m, 'views', None), url, semesta))
                    status[g] = {'status': 'ok', 'pesan': n}
                except Exception as exc:
                    status[g] = {'status': 'gagal: %s' % exc}
                _progres(tambah=1)
        finally:
            await client.disconnect()
        return baris, status

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(jalan())
    finally:
        loop.close()


def login_telegram():
    api_id, api_hash = _kredensial_tg()
    if not api_id or not api_hash:
        raise SystemExit('Isi dulu TELEGRAM_API_ID dan TELEGRAM_API_HASH (dari my.telegram.org -> API development '
                         'tools) di %s' % BDM_ENV)
    from telethon.sync import TelegramClient
    with TelegramClient(TG_SESSION, int(api_id), api_hash) as client:     # minta nomor HP & kode OTP di konsol
        me = client.get_me()
        print('Login Telegram OK sebagai %s. Sesi tersimpan di %s.session' % (me.username or me.first_name, TG_SESSION))


# ---------------------------------------------------------------- tumpukan
def _muat():
    try:
        with open(SEBUTAN_FILE, 'rb') as fh:
            return pickle.load(fh)
    except Exception:
        return {'sebutan': pd.DataFrame(columns=KOLOM), 'jangkauan': {}, 'kanal': {},
                'ditarik': None, 'pertama': None}


def _simpan(st):
    tmp = SEBUTAN_FILE + '.tmp'
    with open(tmp, 'wb') as fh:
        pickle.dump(st, fh)
    os.replace(tmp, SEBUTAN_FILE)


def kumpulkan(stockbit=True, telegram=True):
    """Tarik semua sumber, tumpuk ke SEBUTAN_FILE, catat bacaan hari ini."""
    kini = _sekarang()
    semesta = _semesta()
    if not semesta:
        raise RuntimeError('Folder Summary kosong: %s' % SUMMARY_DIR)
    sumber = baca_sumber()
    st = _muat()
    baru, catatan = [], {}

    if stockbit:
        b, jangkauan = tarik_stockbit(semesta)
        baru += b
        st['jangkauan'] = {t: dict(j, ditarik=kini) for t, j in jangkauan.items()}
        catatan['Stockbit'] = {'status': 'ok', 'pesan': len({x['post_id'] for x in b})}
    if telegram:
        sejak = kini - pd.Timedelta(hours=TG_MUNDUR_JAM)
        b, s = tarik_telegram_publik(sumber['telegram_publik'], semesta, sejak)
        baru += b
        catatan.update({'@' + k: v for k, v in s.items()})
        b, s = tarik_telegram_grup(sumber['telegram_grup'], semesta, sejak)
        baru += b
        catatan.update(s)

    _progres('Menyimpan')
    df = pd.concat([x for x in (st['sebutan'], pd.DataFrame(baru, columns=KOLOM)) if not x.empty] or
                   [pd.DataFrame(columns=KOLOM)], ignore_index=True)
    # Yang terbaru menang: angka suka/balas/tayang ikut diperbarui.
    df = df.drop_duplicates(['post_id', 'ticker'], keep='last')
    df = df[df.groupby('post_id')['ticker'].transform('size') <= MAKS_TAG]
    df = df[pd.to_datetime(df['waktu']) >= kini - pd.Timedelta(days=SIMPAN_HARI)]
    st['sebutan'] = df.reset_index(drop=True)
    st['kanal'] = dict(st.get('kanal') or {}, **{k: dict(v, ditarik=kini) for k, v in catatan.items()})
    st['ditarik'] = kini
    st['pertama'] = st.get('pertama') or kini
    _simpan(st)
    _catat_harian(st, kini)
    _CACHE['ts'] = 0
    return {'baris_baru': len(baru), 'total': len(df), 'sumber': catatan}


def _jalan_latar(stockbit, telegram):
    try:
        kumpulkan(stockbit=stockbit, telegram=telegram)
    except Exception as exc:
        logger.exception('Gagal menarik Ramai Dibahas')
        with _KUNCI:
            _STATUS['galat'] = str(exc)
    finally:
        with _KUNCI:
            _STATUS['jalan'] = False
            _STATUS['tahap'] = ''


def mulai_tarik(stockbit=True, telegram=True):
    """Dipanggil dari tombol halaman: jalan di thread latar, satu sekaligus."""
    with _KUNCI:
        if _STATUS['jalan']:
            return False
        _STATUS.update(jalan=True, tahap='Mulai', selesai=0, total=0, galat=None, mulai=_sekarang())
    threading.Thread(target=_jalan_latar, args=(stockbit, telegram), daemon=True).start()
    return True


def status_tarik():
    with _KUNCI:
        s = dict(_STATUS)
    s['mulai'] = s['mulai'].strftime('%H:%M:%S') if s['mulai'] is not None else None
    return s


# ---------------------------------------------------------------- hitung
def _ringkas(df, jangkauan, kini):
    """Satu baris per emiten untuk jendela 24 jam terakhir."""
    awal = kini - pd.Timedelta(hours=JENDELA_JAM)
    w = df[df['waktu'] >= awal]
    if w.empty:
        return pd.DataFrame()
    sb = w[w['sumber'] == 'stockbit']
    tg = w[w['sumber'] == 'telegram']
    g = pd.DataFrame({
        'sb': sb.groupby('ticker')['post_id'].nunique(),
        'sb_penulis': sb.groupby('ticker')['penulis'].nunique(),
        'sb_respon': (sb['suka'].astype(float) + sb['balas'].astype(float)).groupby(sb['ticker']).sum(),
        'tg': tg.groupby('ticker')['sidik'].nunique(),
        'tg_kanal': tg.groupby('ticker')['kanal'].nunique(),
    }, index=sorted(set(w['ticker']))).astype(float).fillna(0)

    # Jenuh: 30 post halaman emiten itu semuanya jatuh di dalam 24 jam.
    jenuh, perkiraan = {}, {}
    for t in g.index:
        j = jangkauan.get(t) or {}
        if j.get('n', 0) >= 30 and j.get('tertua') is not None and j['tertua'] > awal:
            rentang = max((j['ditarik'] - j['tertua']).total_seconds() / 3600, 0.25)
            jenuh[t] = True
            perkiraan[t] = max(g.at[t, 'sb'], round(30 * JENDELA_JAM / rentang))
    g['sb_jenuh'] = [t in jenuh for t in g.index]
    g['sb_kira'] = [perkiraan.get(t, g.at[t, 'sb']) for t in g.index]
    g['total'] = g['sb_kira'] + g['tg']

    # Jurnal harian mencatat sentimen 24 jam yang sama dengan jumlah obrolannya.
    return g.join(_hitung_sentimen(w, g.index))


def _hitung_sentimen(w, index):
    """Per emiten, dari post yang TERBACA (bukan perkiraan laju), unik seperti kolom sb/tg."""
    g = pd.DataFrame(index=index)
    for pre, sumber, kunci in (('sb', 'stockbit', 'post_id'), ('tg', 'telegram', 'sidik')):
        x = w[w['sumber'] == sumber]
        s = x['cuplikan'].map(sentimen)
        g[pre + '_pos'] = x[s > 0].groupby('ticker')[kunci].nunique().reindex(index).fillna(0)
        g[pre + '_neg'] = x[s < 0].groupby('ticker')[kunci].nunique().reindex(index).fillna(0)
    g['pos'] = g['sb_pos'] + g['tg_pos']
    g['neg'] = g['sb_neg'] + g['tg_neg']
    g['skor'] = _skor(g['pos'], g['neg'])
    g['skor_sb'] = _skor(g['sb_pos'], g['sb_neg'])
    g['skor_tg'] = _skor(g['tg_pos'], g['tg_neg'])
    return g


def _jendela_sentimen(kini):
    """Senin 00:00 s/d sekarang di hari bursa; Sabtu/Minggu -> Senin-Jumat yang baru lewat.
    Libur bursa tidak dikecualikan."""
    senin = kini.normalize() - pd.Timedelta(days=kini.weekday())
    sabtu = senin + pd.Timedelta(days=5)
    return senin, min(kini, sabtu), kini >= sabtu


def _skor(pos, neg):
    """-100 (semua yang berpendapat negatif) .. +100 (semua positif); kosong kalau tak ada yang berpendapat."""
    return 100 * (pos - neg) / (pos + neg).where(pos + neg > 0)


def _suasana(w, awal, akhir):
    """Ringkasan sentimen satu jendela per sumber, tiap post/pesan dihitung sekali walau menyebut banyak emiten."""
    out = {'hari': []}
    u = pd.concat([w[w['sumber'] == 'stockbit'].drop_duplicates('post_id'),
                   w[w['sumber'] == 'telegram'].drop_duplicates('sidik')])
    s = u['cuplikan'].map(sentimen)
    for h in pd.date_range(awal, akhir - pd.Timedelta(seconds=1), freq='D'):
        m = u['waktu'].dt.normalize() == h
        pos, neg = int((s[m] > 0).sum()), int((s[m] < 0).sum())
        out['hari'].append({'tgl': '%s %d' % (HARI[h.weekday()], h.day), 'n': int(m.sum()),
                            'skor': _num(100 * (pos - neg) / (pos + neg), 0) if pos + neg else None})
    for nama, sumber, kunci in (('Stockbit', 'stockbit', 'post_id'), ('Telegram', 'telegram', 'sidik')):
        x = u[u['sumber'] == sumber]
        s = x['cuplikan'].map(sentimen)
        n, pos, neg = len(x), int((s > 0).sum()), int((s < 0).sum())
        skor = 100 * (pos - neg) / (pos + neg) if pos + neg else None
        out[nama] = {'n': n, 'pos': pos, 'neg': neg, 'netral': n - pos - neg, 'skor': _num(skor, 0),
                     'pos_pct': _num(100 * pos / n, 0) if n else None, 'neg_pct': _num(100 * neg / n, 0) if n else None}
    return out


def _baseline(df, kini):
    """Rata-rata sebutan per hari di 7 hari SEBELUM jendela 24 jam."""
    akhir = kini - pd.Timedelta(hours=JENDELA_JAM)
    awal = akhir - pd.Timedelta(days=BASELINE_HARI)
    b = df[(df['waktu'] >= awal) & (df['waktu'] < akhir)]
    if b.empty:
        return pd.Series(dtype=float)
    sb = b[b['sumber'] == 'stockbit'].groupby('ticker')['post_id'].nunique()
    tg = b[b['sumber'] == 'telegram'].groupby('ticker')['sidik'].nunique()
    return sb.add(tg, fill_value=0) / BASELINE_HARI


def _harga(tickers):
    from .tembus_basis import _baca_summary
    out = {}
    for t in tickers:
        df = _baca_summary(os.path.join(SUMMARY_DIR, '%s_Summary.csv' % t))
        if df is None or len(df) < 6:
            continue
        c = df['Close']
        nilai = (df['Close'] * df['Volume']).tail(20).median()
        out[t] = {'close': float(c.iloc[-1]), 'tgl': c.index[-1].strftime('%d %b'),
                  'r1': float((c.iloc[-1] / c.iloc[-2] - 1) * 100),
                  'r5': float((c.iloc[-1] / c.iloc[-6] - 1) * 100),
                  'nilai_m': float(nilai / 1e9)}
    return out


def _catat_harian(st, kini):
    """Bacaan hari ini (ditimpa kalau ditarik lagi di hari yang sama) -- bahan uji maju nanti.

    Sejak 27 Okt 2026 emiten yang NOL obrolan ikut dicatat (total 0, peringkat
    kosong), supaya yang sepi bisa diuji maju juga -- asal Stockbit-nya ditarik
    di tarikan ini; tarikan Telegram saja tidak menulis baris nol. Dua kolom
    baru untuk mengukur seberapa sepi: sb_ambil = jumlah post yang ada di
    halaman emiten (maks 30), sb_umur_jam = umur post tertua di antaranya.
    Uji arsip Telegram (riset_pola_naik/sepi_dibahas.py) GAGAL, tapi proksinya
    kasar -- jurnal ini uji yang lebih tajam.
    """
    g = _ringkas(st['sebutan'], st['jangkauan'], kini)
    jang = {t: j for t, j in (st.get('jangkauan') or {}).items() if j.get('ditarik') == kini}
    if g.empty and not jang:
        return
    nol = sorted(set(jang) - set(g.index))
    if nol:
        g = pd.concat([g, pd.DataFrame(0.0, index=nol, columns=g.columns if len(g.columns) else ['total'])])
        g['sb_jenuh'] = g['sb_jenuh'].eq(True) if 'sb_jenuh' in g.columns else False
        g.loc[nol, [c for c in ('skor', 'skor_sb', 'skor_tg') if c in g.columns]] = np.nan
    g['sb_ambil'] = [jang[t]['n'] if t in jang else np.nan for t in g.index]
    g['sb_umur_jam'] = [round((kini - jang[t]['tertua']).total_seconds() / 3600, 1)
                        if t in jang and jang[t].get('tertua') is not None else np.nan for t in g.index]
    g = g.sort_values(['total', 'sb_umur_jam'], ascending=[False, True])
    rek = g.reset_index().rename(columns={'index': 'ticker'})
    rek.insert(0, 'jam', kini.strftime('%H:%M'))
    rek.insert(0, 'tanggal', kini.strftime('%Y-%m-%d'))
    ada = int((rek['total'] > 0).sum())
    rek['peringkat'] = list(range(1, ada + 1)) + [np.nan] * (len(rek) - ada)
    if os.path.exists(HARIAN_FILE):
        lama = pd.read_csv(HARIAN_FILE, dtype={'tanggal': str})
        lama = lama[lama['tanggal'] != rek['tanggal'].iloc[0]]
        rek = pd.concat([lama, rek], ignore_index=True)
    rek.to_csv(HARIAN_FILE, index=False)


def _num(v, d=2):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v != v or v in (float('inf'), float('-inf')) else round(v, d)


def scan(force=False):
    if not force and _CACHE['data'] is not None and time.time() - _CACHE['ts'] < TTL:
        d = dict(_CACHE['data'])
        d['tarik'] = status_tarik()
        return d
    st = _muat()
    sumber = baca_sumber()
    tg_siap = {'telethon': _ada_telethon(), 'kredensial': all(_kredensial_tg()),
               'sesi': os.path.exists(TG_SESSION + '.session')}
    dasar = {'available': True, 'sumber': sumber, 'tg_siap': tg_siap, 'tarik': status_tarik(),
             'kanal': [{'nama': k, 'status': v.get('status'), 'pesan': v.get('pesan'),
                        'ditarik': v['ditarik'].strftime('%d %b %H:%M') if v.get('ditarik') is not None else None}
                       for k, v in (st.get('kanal') or {}).items()]}
    if st.get('ditarik') is None or st['sebutan'].empty:
        return dict(dasar, kosong=True, message='Belum pernah ditarik. Tekan "Tarik sekarang" (~1-2 menit).')

    kini = _sekarang()
    df = st['sebutan'].copy()
    df['waktu'] = pd.to_datetime(df['waktu'])
    g = _ringkas(df, st['jangkauan'], kini)
    if g.empty:
        return dict(dasar, kosong=True, message='Tidak ada obrolan di 24 jam terakhir. Tarik ulang?')

    riwayat_hari = (kini - st['pertama']).total_seconds() / 86400
    base = _baseline(df, kini).reindex(g.index).fillna(0)
    g['base'] = base
    g['lonjak'] = (g['total'] + 1) / (g['base'] + 1)
    g = g.sort_values('total', ascending=False).head(100)
    harga = _harga(list(g.index))

    # Sentimen per emiten memakai jendela Senin-Jumat, bukan 24 jam (lihat _jendela_sentimen).
    s_awal, s_akhir, s_lewat = _jendela_sentimen(kini)
    sent = _hitung_sentimen(df[(df['waktu'] >= s_awal) & (df['waktu'] < s_akhir)], g.index)
    g[sent.columns] = sent

    awal = kini - pd.Timedelta(hours=JENDELA_JAM)
    w = df[(df['waktu'] >= awal) & df['ticker'].isin(g.index)].sort_values('waktu', ascending=False)
    contoh = {t: [{'sumber': r.kanal, 'waktu': r.waktu.strftime('%d %b %H:%M'), 'penulis': r.penulis,
                   'teks': r.cuplikan, 'url': r.url, 'suka': int(r.suka), 'balas': int(r.balas),
                   'sent': sentimen(r.cuplikan)}
                  for r in x.drop_duplicates('sidik').head(6).itertuples()]
              for t, x in w.groupby('ticker')}

    baris = []
    for t, r in g.iterrows():
        h = harga.get(t, {})
        baris.append({
            'stock': t, 'total': int(r['total']), 'sb': int(r['sb']), 'sb_jenuh': bool(r['sb_jenuh']),
            'sb_kira': int(r['sb_kira']), 'sb_penulis': int(r['sb_penulis']), 'sb_respon': int(r['sb_respon']),
            'tg': int(r['tg']), 'tg_kanal': int(r['tg_kanal']),
            'base': _num(r['base'], 1), 'lonjak': _num(r['lonjak'], 1),
            'close': _num(h.get('close'), 0), 'r1': _num(h.get('r1')), 'r5': _num(h.get('r5')),
            'nilai_m': _num(h.get('nilai_m'), 1), 'harga_tgl': h.get('tgl'),
            'pos': int(r['pos']), 'neg': int(r['neg']), 'skor': _num(r['skor'], 0),
            'skor_sb': _num(r['skor_sb'], 0), 'skor_tg': _num(r['skor_tg'], 0),
            'sb_pos': int(r['sb_pos']), 'sb_neg': int(r['sb_neg']), 'tg_pos': int(r['tg_pos']), 'tg_neg': int(r['tg_neg']),
            'contoh': contoh.get(t, []),
        })
    hasil = dict(dasar, kosong=False, baris=baris, n_emiten=int(len(_ringkas(df, st['jangkauan'], kini))),
                 ditarik=st['ditarik'].strftime('%d %b %Y %H:%M'),
                 basi_jam=_num((kini - st['ditarik']).total_seconds() / 3600, 1),
                 riwayat_hari=_num(riwayat_hari, 1), baseline_siap=riwayat_hari >= BASELINE_HARI + 1,
                 suasana=_suasana(df[(df['waktu'] >= s_awal) & (df['waktu'] < s_akhir)], s_awal, s_akhir),
                 sentimen_jendela='%s %s – %s %s' % (HARI[s_awal.weekday()], s_awal.strftime('%d %b'),
                                                      HARI[(s_akhir - pd.Timedelta(seconds=1)).weekday()],
                                                      (s_akhir - pd.Timedelta(seconds=1)).strftime('%d %b'))
                                  + (' (minggu lalu, akhir pekan)' if s_lewat else ' (minggu berjalan)'),
                 dibangun=kini.strftime('%H:%M'))
    _CACHE.update(ts=time.time(), data=hasil)
    return hasil


def _ada_telethon():
    try:
        import telethon  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Tarik obrolan Stockbit & Telegram untuk menu Ramai Dibahas.')
    ap.add_argument('--login-telegram', action='store_true', help='login akun Telegram sekali (untuk grup)')
    ap.add_argument('--tanpa-stockbit', action='store_true')
    ap.add_argument('--tanpa-telegram', action='store_true')
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    if a.login_telegram:
        login_telegram()
    else:
        t0 = time.time()
        hasil = kumpulkan(stockbit=not a.tanpa_stockbit, telegram=not a.tanpa_telegram)
        print('Selesai %.0f detik: %d sebutan baru, %d di tumpukan.' % (time.time() - t0, hasil['baris_baru'], hasil['total']))
        for k, v in hasil['sumber'].items():
            print('  %-30s %s%s' % (k, v.get('status'), ' (%s pesan)' % v['pesan'] if v.get('pesan') is not None else ''))
