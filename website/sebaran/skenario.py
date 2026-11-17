"""
Jenis kabar, segmen pelaku, dan data emiten yang menyetel simulasi.

Populasi di sini = KOMUNITAS yang membicarakan satu emiten (Stockbit,
Telegram, grup WA), bukan daftar pemegang saham. Komposisinya digeser
oleh data project bila ada:
  - porsi ritel KSEI    -> banyak/sedikitnya ritel pemula & trader
  - Ramai Dibahas       -> berapa orang yang SUDAH tahu di hari pertama
  - naik 5 hari (Summary) -> FOMO ritel naik, investor makin curiga
  - profil saham (lihat terapkan_profil) -> kapitalisasi, nilai transaksi,
    asing, kepemilikan korporasi, dan ayunan harga menggeser porsi & sikap
    tiap kelompok. SEMUANYA ASUMSI, belum dikalibrasi; tiap aturan menulis
    kalimat "Asumsi: ..." yang ditampilkan di halaman.

Sifat tiap segmen (lihat engine.py):
  share  porsi populasi        bias  sikap awal (-1..1)
  sens   kepekaan pada kabar   stub  keras kepala (0..1)
  act    peluang posting/hari  eps   toleransi beda pendapat
  loyal  menahan diri dari jual   hub   menempati akun paling banyak pengikut
  insider tahu sejak awal, beli duluan, jual saat ritel ramai
"""
try:
    from ..runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import csv
import os


def _seg(key, label, share, bias, sens, stub, act, eps, loyal, hub=False, insider=False, ritel=False):
    return dict(key=key, label=label, share=share, bias=bias, sens=sens, stub=stub, act=act,
                eps=eps, loyal=loyal, hub=hub, insider=insider, ritel=ritel)


SEGMEN = [
    _seg('pemula', 'Ritel pemula', 0.32, 0.05, 1.4, 0.25, 0.12, 0.85, 0.10, ritel=True),
    _seg('trader', 'Trader / scalper', 0.22, 0.0, 1.0, 0.35, 0.22, 0.60, 0.05, ritel=True),
    _seg('investor', 'Investor fundamental', 0.20, 0.0, 0.6, 0.75, 0.06, 0.35, 0.70),
    _seg('pasif', 'Pemegang pasif', 0.14, 0.0, 0.4, 0.60, 0.02, 0.50, 0.80),
    _seg('pompom', 'Influencer / pom-pom', 0.04, 0.10, 0.8, 0.40, 0.55, 0.60, 0.20, hub=True),
    _seg('analis', 'Analis & media', 0.05, 0.0, 0.7, 0.70, 0.35, 0.40, 0.50, hub=True),
    _seg('insider', 'Orang dalam / bandar', 0.03, 0.0, 0.5, 0.90, 0.04, 0.10, 0.0, insider=True),
]


def _clip(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


TAHU = {'key': 'awareness', 'label': 'Yang sudah tahu kabarnya di hari pertama (%)', 'min': 1, 'max': 90, 'default': 10}
RITEL = {'key': 'ritel', 'label': 'Porsi ritel (KSEI, %)', 'min': 0, 'max': 100, 'default': 45}
NAIK5 = {'key': 'naik5', 'label': 'Sudah naik 5 hari terakhir (%)', 'min': -50, 'max': 100, 'default': 0}
UMUM = [TAHU, RITEL, NAIK5]


# ------------------------------------------------------------ jenis kabar
def _rec_rumor(s):
    r = []
    if s['late_buy'] > 0.3:
        r.append(f"{s['late_buy']:.0%} pembelian ritel terjadi SETELAH obrolan memuncak. Kalau baru tahu dari grup, kemungkinan besar Anda sudah telat.")
    if s['params']['kredibilitas'] <= 4:
        r.append("Kredibilitas rumor rendah. Cek keterbukaan informasi IDX dan laporan kepemilikan (KSEI) sebelum percaya.")
    if not s['ada_event_resmi']:
        r.append("Uji event 'Bantahan emiten' di tengah simulasi: begitulah rumor akuisisi biasanya berakhir kalau tidak benar.")
    return r


def _rec_pompom(s):
    r = []
    if s['insider_sell_round'] is not None:
        r.append(f"Orang dalam mulai jual di hari ke-{s['insider_sell_round']}, saat ritel masih ramai membeli. Pola klasik distribusi: keramaian adalah likuiditas untuk keluar.")
    if s['cutloss'] > 0.15:
        r.append(f"{s['cutloss']:.0%} ritel yang ikut beli akhirnya jual rugi. Bandingkan dengan Akumulasi Palsu dan Sidik Jari Broker sebelum ikut.")
    r.append("Saham yang ramai karena pom-pom: lihat Takaran Risiko untuk ukuran ayunannya, bukan arah.")
    return r


def _rec_lapkeu(s):
    r = []
    if abs(s['params']['kejutan']) >= 6 and s['params']['antisipasi'] >= 6:
        r.append("Kejutan besar tapi sudah diantisipasi: reaksi komunitas kecil. 'Buy the rumor, sell the news' paling mungkin di sini.")
    inv = s['seg'].get('investor')
    if inv and inv['op'] > 0.3 and s['seg']['pemula']['op'] < 0.1:
        r.append("Investor fundamental positif tapi ritel belum peduli. Kabar fundamental menyebar pelan; jangan berharap respons cepat.")
    return r


def _rec_negatif(s):
    r = []
    if s['final']['neg_action'] > 0.15:
        r.append(f"{s['final']['neg_action']:.0%} komunitas menjual. Cek likuiditas (nilai transaksi) — di saham tidak likuid, jual serentak bisa mentok ARB berhari-hari.")
    if not s['ada_event_positif']:
        r.append("Uji event 'Klarifikasi emiten' di hari 1–2 lalu bandingkan dengan klarifikasi yang telat.")
    return r


def _rec_aksi(s):
    r = []
    if s['final']['pos_action'] < 0.1:
        r.append("Minat ritel rendah. Aksi korporasi ini kurang dipahami komunitas; tunggu prospektus/ringkasan resmi.")
    return r


KABAR = {
    'rumor': dict(
        key='rumor', label='Rumor akuisisi / backdoor listing', distribusi=True,
        params=[{'key': 'kredibilitas', 'label': 'Kredibilitas sumber rumor (0-10)', 'min': 0, 'max': 10, 'default': 4}] + UMUM,
        impact=lambda p: _clip(0.2 + p['kredibilitas'] * 0.05),
        controversy=lambda p: 0.5,
        bias={'insider': 0.6, 'pompom': 0.45, 'investor': -0.1},
        neg_mult=1.0, pos_mult=1.2,
        events=[
            {'name': 'Bantahan emiten di keterbukaan informasi', 'effect': -0.55, 'target': 'all', 'aw': 0.5},
            {'name': 'Konfirmasi resmi (keterbukaan informasi)', 'effect': 0.4, 'target': 'all', 'aw': 0.5},
            {'name': 'Saham kena ARA', 'effect': 0.25, 'target': 'all', 'aw': 0.35},
            {'name': 'Bursa umumkan UMA', 'effect': -0.1, 'target': 'all', 'aw': 0.3},
            {'name': 'Suspensi perdagangan', 'effect': -0.2, 'target': 'all', 'aw': 0.25},
        ],
        recs=_rec_rumor,
        templates={
            'vneg': ['${kode} cuma rumor, udah dibantah. Yang nyangkut sabar ya.', 'Jangan percaya pom-pom ${kode}, gak ada keterbukaan info sama sekali.',
                     'Exit dulu dari ${kode}, baunya kayak jebakan.', '${kode} rumor basi, bandar udah keluar duluan.'],
            'neg': ['Rumor ${kode} belum ada sumber resmi, hati-hati.', 'Kok ${kode} naik tanpa berita jelas ya.',
                    'Saya skip ${kode}, terlalu spekulatif.', 'Udah cek KSEI ${kode}? Gak ada pemegang baru.'],
            'neu': ['Ada yang tau kabar akuisisi ${kode}?', 'Pantau ${kode} dulu, tunggu keterbukaan informasi.',
                    '${kode} rame di grup, ada apa ya?', 'Volume ${kode} naik, rumor beneran gak sih?'],
            'pos': ['Katanya ${kode} mau diakuisisi, mulai cicil dikit.', '${kode} volume naik, kayaknya ada yang tau sesuatu.',
                    'Entry ${kode} sebagian, SL ketat.', 'Rumor ${kode} makin kencang nih.'],
            'vpos': ['${kode} otw diakuisisi, gas sebelum ARA!', 'HAKA ${kode}, bandar lagi kumpulin barang!',
                     '${kode} to the moon, backdoor listing confirmed (katanya).', 'Telat beli ${kode} nyesel seumur hidup!'],
        },
    ),
    'pompom': dict(
        key='pompom', label='Pom-pom / saham digoreng', distribusi=True,
        params=[{'key': 'intensitas', 'label': 'Intensitas pom-pom (0-10)', 'min': 0, 'max': 10, 'default': 6}] + UMUM,
        impact=lambda p: _clip(0.05 + p['intensitas'] * 0.02),
        controversy=lambda p: min(1.0, 0.3 + p['intensitas'] / 12),
        bias={'pompom': 0.75, 'insider': 0.7, 'investor': -0.35, 'analis': -0.15},
        neg_mult=1.2, pos_mult=1.3,
        events=[
            {'name': 'Influencer besar ikut pom-pom', 'effect': 0.6, 'target': 'pompom', 'aw': 0.3},
            {'name': 'ARA berturut-turut', 'effect': 0.3, 'target': 'all', 'aw': 0.35},
            {'name': 'Bandar buang barang (ARB)', 'effect': -0.6, 'target': 'all', 'aw': 0.3},
            {'name': 'Bursa umumkan UMA', 'effect': -0.15, 'target': 'all', 'aw': 0.3},
        ],
        recs=_rec_pompom,
        templates={
            'vneg': ['${kode} digoreng, sekarang dibuang. Sakit.', 'Kena guyur ${kode}, ARB lagi. Kapok ikut grup.',
                     'Awas ${kode}, bandar distribusi ke ritel.', 'Cut loss ${kode}. Pelajaran mahal.'],
            'neg': ['${kode} naiknya gak wajar, fundamental nol.', 'Hati-hati ${kode}, saham gorengan.',
                    'Volume ${kode} aneh, broker yang beli itu-itu aja.', 'Gak ikut ${kode}, risiko ARB tinggi.'],
            'neu': ['${kode} lagi rame, ada yang ikut?', 'Lihat ${kode} di watchlist dulu.',
                    'Siapa yang pom-pom ${kode} pagi ini?', '${kode} naik terus, nunggu koreksi.'],
            'pos': ['${kode} masih kuat, hold.', 'Ikut ${kode} dikit buat scalping.',
                    '${kode} breakout, target masih jauh.', 'Momentum ${kode} bagus nih.'],
            'vpos': ['${kode} ARA lagi! Jangan jual dulu!', 'Gas ${kode}, target 2x lipat!',
                     'Yang belum masuk ${kode} rugi banget.', '${kode} multibagger, percaya prosesnya!'],
        },
    ),
    'lapkeu': dict(
        key='lapkeu', label='Rilis laporan keuangan',
        params=[{'key': 'kejutan', 'label': 'Kejutan laba (-10 jauh di bawah - 10 jauh di atas)', 'min': -10, 'max': 10, 'default': 4},
                {'key': 'antisipasi', 'label': 'Sudah diantisipasi pasar (0-10)', 'min': 0, 'max': 10, 'default': 5}] + UMUM,
        impact=lambda p: _clip(p['kejutan'] / 10 * 0.8 * (1 - p['antisipasi'] / 10 * 0.6)),
        controversy=lambda p: 0.2,
        bias={'insider': 0.0},
        neg_mult=0.8, pos_mult=0.9,
        events=[
            {'name': 'Analis menaikkan target harga', 'effect': 0.3, 'target': 'all', 'aw': 0.2},
            {'name': 'Asing net sell besar', 'effect': -0.25, 'target': 'all', 'aw': 0.1},
            {'name': 'Laba ternyata dari pos sekali (one-off)', 'effect': -0.35, 'target': 'all', 'aw': 0.15},
        ],
        recs=_rec_lapkeu,
        templates={
            'vneg': ['Lapkeu ${kode} jelek banget, jual.', '${kode} rugi lagi, mau sampai kapan?', 'Kinerja ${kode} hancur, out.'],
            'neg': ['Laba ${kode} di bawah ekspektasi.', 'Margin ${kode} turun, kurang menarik.', '${kode} lapkeu meh.'],
            'neu': ['Lapkeu ${kode} sudah keluar, ada yang udah baca?', '${kode} sesuai ekspektasi aja.', 'Nunggu analisa lapkeu ${kode}.'],
            'pos': ['Laba ${kode} tumbuh, lumayan.', 'Lapkeu ${kode} solid, hold.', '${kode} kinerja oke, PER masih murah.'],
            'vpos': ['Lapkeu ${kode} gila, laba naik tajam!', '${kode} beat ekspektasi, add posisi.', 'Fundamental ${kode} makin kuat, akumulasi!'],
        },
    ),
    'negatif': dict(
        key='negatif', label='Kabar buruk (gagal bayar / kasus / PKPU)',
        params=[{'key': 'keparahan', 'label': 'Keparahan kabar (0-10)', 'min': 0, 'max': 10, 'default': 6}] + UMUM,
        impact=lambda p: _clip(-0.15 - p['keparahan'] * 0.07),
        controversy=lambda p: 0.4,
        bias={'insider': -0.5},
        neg_mult=1.3, pos_mult=0.6,
        events=[
            {'name': 'Klarifikasi emiten', 'effect': 0.25, 'target': 'all', 'aw': 0.3},
            {'name': 'Media besar memberitakan', 'effect': -0.2, 'target': 'all', 'aw': 0.4},
            {'name': 'Suspensi perdagangan', 'effect': -0.2, 'target': 'all', 'aw': 0.3},
            {'name': 'Investor baru / pembeli siaga masuk', 'effect': 0.4, 'target': 'all', 'aw': 0.3},
        ],
        recs=_rec_negatif,
        templates={
            'vneg': ['${kode} bisa delisting, keluar sekarang!', 'Kabar ${kode} parah, jual semua.', '${kode} kasus begini biasanya panjang. Out.'],
            'neg': ['Hati-hati ${kode}, kabarnya kurang enak.', 'Kurangi posisi ${kode} dulu.', '${kode} risikonya naik, wait and see.'],
            'neu': ['Ada yang tau kelanjutan kasus ${kode}?', 'Nunggu klarifikasi resmi ${kode}.', '${kode} rame, kabarnya beneran?'],
            'pos': ['${kode} sudah murah, kabarnya mungkin overreaction.', 'Cicil ${kode} dikit di bawah.', 'Panik di ${kode} berlebihan.'],
            'vpos': ['${kode} diskon besar, borong!', 'Kabar buruk ${kode} sudah priced in.', 'Beli saat orang takut: ${kode}.'],
        },
    ),
    'aksi': dict(
        key='aksi', label='Aksi korporasi (rights issue / split / buyback)',
        params=[{'key': 'daya_tarik', 'label': 'Daya tarik bagi pemegang saham (-10 - 10)', 'min': -10, 'max': 10, 'default': 3}] + UMUM,
        impact=lambda p: _clip(p['daya_tarik'] / 10 * 0.7),
        controversy=lambda p: 0.25,
        bias={'insider': 0.2},
        neg_mult=0.8, pos_mult=0.8,
        events=[
            {'name': 'Harga tebus di atas harga pasar', 'effect': 0.2, 'target': 'all', 'aw': 0.2},
            {'name': 'Pembeli siaga mundur', 'effect': -0.4, 'target': 'all', 'aw': 0.25},
            {'name': 'Buyback diumumkan', 'effect': 0.3, 'target': 'all', 'aw': 0.3},
        ],
        recs=_rec_aksi,
        templates={
            'vneg': ['Rights issue ${kode} cuma buat bayar utang, males tebus.', '${kode} dilusi parah, jual.', 'Aksi korporasi ${kode} merugikan minoritas.'],
            'neg': ['Gak yakin tebus right ${kode}.', '${kode} aksi korporasinya kurang jelas.', 'Dana rights ${kode} buat apa ya?'],
            'neu': ['Ada yang baca prospektus ${kode}?', 'Jadwal aksi korporasi ${kode} kapan?', 'Pantau ${kode} sampai cum date.'],
            'pos': ['Aksi korporasi ${kode} cukup menarik.', 'Tebus right ${kode}, prospek ekspansi oke.', '${kode} split bikin lebih likuid.'],
            'vpos': ['${kode} buyback, sinyal manajemen yakin!', 'Tebus full right ${kode}!', 'Aksi korporasi ${kode} game changer.'],
        },
    ),
}


def daftar_kabar():
    """Versi aman-JSON untuk halaman (tanpa fungsi)."""
    return [{
        'key': k['key'], 'label': k['label'], 'params': k['params'], 'events': k['events'],
        'segments': [{'key': s['key'], 'label': s['label']} for s in SEGMEN],
        'neg_label': 'Jual', 'pos_label': 'Beli',
    } for k in KABAR.values()]


def bangun_preset(kabar, p, profil=None):
    """
    Gabungkan segmen dasar + jenis kabar + slider + profil saham jadi satu preset
    untuk engine. `profil` (dari profil_saham) opsional; tanpa itu semua saham
    diperlakukan sama kecuali tiga slider.
    """
    ritel = p.get('ritel', 45) / 100
    naik = p.get('naik5', 0)
    fomo = _clip(naik / 50, -0.3, 0.3)
    segs = []
    for s in SEGMEN:
        s = dict(s)
        if s['ritel']:
            s['share'] *= 0.5 + ritel
        elif not (s['hub'] or s['insider']):
            s['share'] *= 1.5 - ritel
        s['bias'] = _clip(s['bias'] + kabar['bias'].get(s['key'], 0.0))
        if s['key'] == 'pemula':
            s['bias'] = _clip(s['bias'] + fomo)
        if s['key'] == 'investor' and naik > 0:
            s['bias'] = _clip(s['bias'] - min(0.2, naik / 100))
        segs.append(s)
    dinamika, asumsi = terapkan_profil(segs, profil or {}, spekulatif=kabar.get('distribusi', False))
    total = sum(s['share'] for s in segs)
    for s in segs:
        s['share'] /= total
    tambah = dinamika['contro_add']
    return {
        'key': kabar['key'], 'label': kabar['label'], 'params': kabar['params'],
        'segments': segs, 'events': kabar['events'], 'templates': kabar['templates'],
        'impact': kabar['impact'],
        'controversy': lambda _p: min(1.0, kabar['controversy'](_p) + tambah),
        'neg_mult': lambda _p: kabar['neg_mult'], 'pos_mult': lambda _p: kabar['pos_mult'],
        'neg_label': 'Jual', 'pos_label': 'Beli', 'recs': kabar['recs'],
        'distribusi': kabar.get('distribusi', False),
        'insider_sell_mult': dinamika['insider_sell_mult'],
        'asumsi': asumsi,
    }


# ------------------------------------------------------------ profil saham
# SEMUA angka di bagian ini adalah ASUMSI arah yang masuk akal, belum
# dikalibrasi terhadap kabar nyata. Tujuannya membuat saham yang berbeda
# berperilaku berbeda dengan alasan yang bisa dibaca -- bukan membuatnya
# "benar". Tiap efek menghasilkan satu kalimat yang ditampilkan apa adanya
# di halaman dan laporan.

def _mult(segs, key, faktor):
    for s in segs:
        if s['key'] == key:
            s['share'] *= max(0.15, faktor)


def _geser(segs, key, d):
    for s in segs:
        if s['key'] == key:
            s['bias'] = _clip(s['bias'] + d)


def _rp(x):
    return ('Rp %.1f T' % (x / 1e12)).replace('.', ',') if x >= 1e12 else ('Rp %.0f M' % (x / 1e9))


def terapkan_profil(segs, pr, spekulatif=False):
    """Ubah porsi & sikap segmen di tempat. Kembalikan (dinamika, daftar kalimat asumsi)."""
    din = {'contro_add': 0.0, 'insider_sell_mult': 1.0}
    asumsi = []
    cap, liq = pr.get('cap'), pr.get('liq')
    if cap is not None:
        _mult(segs, 'pemula', 1 - 0.35 * cap)
        _mult(segs, 'pompom', 1 - 0.6 * cap)
        _mult(segs, 'analis', 1 + 0.7 * cap)
        _mult(segs, 'investor', 1 + 0.35 * cap)
        _mult(segs, 'pasif', 1 + 0.2 * cap)
        ukuran = ('sangat besar' if cap > 0.6 else 'besar' if cap > 0.2 else 'menengah' if cap > -0.2
                  else 'kecil' if cap > -0.6 else 'sangat kecil')
        arah = ('lebih banyak analis & investor, lebih sedikit pemula & pom-pom' if cap > 0
                else 'lebih banyak ritel pemula & pom-pom, lebih sedikit analis')
        asumsi.append(f"Kapitalisasi {_rp(pr['mcap'])} ({ukuran}) → komunitas berisi {arah}.")
        if spekulatif and cap > 0:
            _geser(segs, 'analis', -0.2 * cap)
            _geser(segs, 'investor', -0.15 * cap)
            asumsi.append("Saham besar banyak diliput: kabar spekulatif lebih cepat diragukan analis & investor.")
    if liq is not None:
        _mult(segs, 'trader', 1 + 0.35 * liq)
        din['insider_sell_mult'] = 0.45 + 0.55 * (liq + 1) / 2
        nilai = ('%.1f' % pr['nilai_m']).replace('.', ',')
        if liq < -0.2:
            asumsi.append(f"Nilai transaksi {nilai} M/hari (tipis) → lebih sedikit trader; orang dalam butuh "
                          "lebih lama untuk keluar tanpa menjatuhkan harga.")
        elif liq > 0.2:
            asumsi.append(f"Nilai transaksi {nilai} M/hari (likuid) → lebih banyak trader; orang dalam bisa keluar cepat.")
        else:
            asumsi.append(f"Nilai transaksi {nilai} M/hari (sedang) → porsi trader & kecepatan keluar orang dalam "
                          "mendekati rata-rata.")
    if pr.get('asing') is not None:
        a = pr['asing']
        _mult(segs, 'investor', 0.7 + 0.9 * a)
        if a >= 0.3:
            asumsi.append(f"Asing memegang {a:.0%} → porsi investor fundamental lebih besar; kabar ditimbang lebih dingin.")
        else:
            asumsi.append(f"Asing hanya {a:.0%} → investor fundamental lebih sedikit.")
    if pr.get('konsentrasi') is not None:
        c = pr['konsentrasi']
        _mult(segs, 'insider', 0.4 + 1.6 * c)
        if spekulatif:
            _geser(segs, 'insider', 0.2 * (c - 0.4))
        asumsi.append(f"Korporasi memegang {c:.0%} saham → orang dalam "
                      f"{'lebih banyak dan lebih menentukan' if c >= 0.5 else 'lebih sedikit'}.")
    if pr.get('vol') is not None:
        v = pr['vol']
        _mult(segs, 'trader', min(1.6, max(0.7, 0.6 + v / 4)))
        din['contro_add'] += min(0.3, max(0.0, (v - 2) / 10))
        sifat = ('lebih banyak trader dan obrolan lebih panas' if v >= 3
                 else 'trader & panasnya obrolan mendekati rata-rata' if v >= 1.5
                 else 'lebih sedikit trader; obrolan lebih tenang')
        asumsi.append(f"Ayunan harian {v:.1f}% → {sifat}.".replace('.', ',', 1))
    rawan = pr.get('rawan')
    if rawan is not None and rawan > 0.2:
        _geser(segs, 'pompom', 0.25 * rawan)
        _geser(segs, 'pemula', 0.1 * rawan)
        din['contro_add'] += 0.2 * rawan
        sebab = [nama for nama, ya in (('kecil', (cap or 0) < -0.2), ('transaksi tipis', (liq or 0) < -0.2),
                                       ('pemilik terkonsentrasi', pr.get('konsentrasi', 0) > 0.5)) if ya]
        asumsi.append(f"Skor rawan goreng {rawan:.2f}".replace('.', ',')
                      + f" ({' + '.join(sebab) or 'gabungan faktor'}) → pom-pom lebih agresif, pemula lebih mudah terbawa.")
    return din, asumsi


def profil_saham(ksei, harga):
    """Data mentah -> skor ternormalisasi. Kunci yang datanya tidak ada dihilangkan."""
    import math
    pr = {}
    if ksei and ksei.get('mcap'):
        pr['mcap'] = ksei['mcap']
        # Rp 0,1 T -> -1 (sangat kecil) ... Rp 100 T -> +1 (sangat besar)
        pr['cap'] = _clip((math.log10(max(ksei['mcap'], 1e9) / 1e12) - 0.5) / 1.5)
    if harga and harga.get('nilai_m'):
        pr['nilai_m'] = harga['nilai_m']
        # 1 M/hari -> -0,67 ; 10 M -> 0 ; >= 316 M -> +1
        pr['liq'] = _clip((math.log10(max(harga['nilai_m'], 0.01)) - 1) / 1.5)
    if ksei:
        pr['asing'] = ksei['pct_foreign'] / 100
        pr['konsentrasi'] = ksei['pct_korporasi'] / 100
    if harga and harga.get('vol') is not None:
        pr['vol'] = harga['vol']
    if any(k in pr for k in ('cap', 'liq', 'konsentrasi')):
        pr['rawan'] = max(0.0, min(1.0, 0.4 * max(0.0, -pr.get('cap', 0.0)) + 0.4 * max(0.0, -pr.get('liq', 0.0))
                                   + 0.4 * max(0.0, pr.get('konsentrasi', 0.0) - 0.3) / 0.7))
    return pr


# ------------------------------------------------------------ data emiten
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUZZ_CSV = str(_runtime_file('', 'ramai_dibahas_harian.csv'))


def _buzz(kode):
    """Bacaan Ramai Dibahas terakhir untuk kode ini: (total obrolan/hari, peringkat, tanggal, n emiten)."""
    if not os.path.exists(BUZZ_CSV):
        return None
    with open(BUZZ_CSV, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    tgl = max(r['tanggal'] for r in rows)
    # sejak 27 Okt 2026 jurnal juga memuat emiten nol obrolan (peringkat kosong)
    hari = [r for r in rows if r['tanggal'] == tgl and float(r['total'] or 0) > 0]
    for r in hari:
        if r['ticker'] == kode:
            return {'total': float(r['total'] or 0), 'peringkat': int(float(r['peringkat'] or 0)),
                    'tanggal': tgl, 'n': len(hari)}
    return {'total': 0.0, 'peringkat': None, 'tanggal': tgl, 'n': len(hari)}


def _ksei(kode):
    from ..ownership import load_ksei_months, build_month_metrics, month_label
    months = load_ksei_months()
    for payload in reversed(months):
        rec = payload.get('securities', {}).get(kode)
        if rec:
            m = build_month_metrics(rec)
            return {'pct_retail': m['pct_retail'], 'pct_foreign': m['pct_foreign'],
                    'pct_korporasi': m['local_pct'].get('CP', 0.0) + m['foreign_pct'].get('CP', 0.0),
                    'mcap': m['market_cap'], 'bulan': month_label(payload['month'])}
    return None


def _harga(kode):
    """Close, naik 1/5 hari, median nilai transaksi 20 hari, dan ayunan harian 60 hari dari Summary."""
    from ..ramai_dibahas import SUMMARY_DIR
    from ..tembus_basis import _baca_summary
    df = _baca_summary(os.path.join(SUMMARY_DIR, '%s_Summary.csv' % kode))
    if df is None or len(df) < 6:
        return None
    c = df['Close']
    ret = c.pct_change().dropna().tail(60)
    return {'close': float(c.iloc[-1]), 'tgl': c.index[-1].strftime('%d %b'),
            'r1': float((c.iloc[-1] / c.iloc[-2] - 1) * 100),
            'r5': float((c.iloc[-1] / c.iloc[-6] - 1) * 100),
            'nilai_m': float((df['Close'] * df['Volume']).tail(20).median() / 1e9),
            'vol': float(ret.std() * 100) if len(ret) >= 20 else None}


_CACHE = {}
_CACHE_DETIK = 600


def konteks_emiten(kode):
    """
    Data nyata untuk mengisi slider awal dan profil saham. Tiap sumber boleh
    gagal sendiri. Disimpan 10 menit per kode supaya tiap klik Jalankan tidak
    membaca ulang Summary.
    """
    import time
    kode = ''.join(ch for ch in (kode or '').upper() if ch.isalnum())[:6]
    simpan = _CACHE.get(kode)
    if simpan and time.time() - simpan[0] < _CACHE_DETIK:
        return simpan[1]
    out = _konteks(kode)
    _CACHE[kode] = (time.time(), out)
    return out


def _konteks(kode):
    from ..models import stockList
    out = {'kode': kode, 'dikenal': kode in stockList, 'saran': {}, 'catatan': []}
    if not kode:
        return out
    for nama, fungsi in (('buzz', _buzz), ('ksei', _ksei), ('harga', _harga)):
        try:
            out[nama] = fungsi(kode)
        except Exception as exc:          # data opsional: halaman tetap jalan tanpa salah satunya
            out[nama] = None
            out['catatan'].append('%s tidak terbaca (%s)' % (nama, exc.__class__.__name__))
    b, k, h = out.get('buzz'), out.get('ksei'), out.get('harga')
    if b:
        # 0 obrolan -> 3% sudah tahu; ~170 obrolan/hari (puncak Ramai Dibahas) -> ~70%
        out['saran']['awareness'] = int(round(max(3, min(80, 3 + b['total'] * 0.4))))
    if k:
        out['saran']['ritel'] = int(round(k['pct_retail']))
    if h:
        out['saran']['naik5'] = int(round(max(-50, min(100, h['r5']))))
    out['profil'] = profil_saham(k, h)
    # Komposisi komunitas yang akan dipakai (contoh: kabar rumor), untuk ditampilkan.
    pre = bangun_preset(KABAR['rumor'], dict({'ritel': 45, 'naik5': 0}, **out['saran']), out['profil'])
    out['komunitas'] = [{'label': s['label'], 'share': round(s['share'], 3)} for s in pre['segments']]
    out['asumsi'] = pre['asumsi']
    return out
