"""
Menjalankan twin: kalibrasi mikro, Monte Carlo baseline-vs-skenario,
ringkasan untuk halaman, dan pendaftaran ke kerangka riset (research.py).

KONTRAFAKTUAL, BUKAN SATU JALUR
Satu jalur simulasi tidak berarti apa-apa: harganya bisa naik 10% hanya
karena undian berita. Maka setiap seed dijalankan DUA kali -- tanpa
skenario dan dengan skenario -- dengan lingkungan (faktor IHSG, berita,
watak agen) yang identik. Efek skenario = selisih keduanya, dan sebarannya
antar-seed menunjukkan seberapa yakin kita pada arah dan besarnya. Skenario
kosong harus menghasilkan selisih nol persis; itu diuji di _uji_nol().

KALIBRASI MIKRO
Ukuran order tiap kelompok dan kedalaman antrean pedagang cepat disetel
beberapa putaran supaya volume, porsi aktivitas tiap kelompok, dan
volatilitas harian baseline mendekati data asli tiap saham. Yang disetel
hanya BESARAN; perilaku (siapa membeli kapan) tidak disentuh -- dan
justru perilaku itulah yang diuji di rapor realisme (validasi.py).

PEMAKAIAN SEBAGAI SCRIPT
    python -m website.twin.jalan --preset bi_rate_naik --agen 2000 --hari 60 --seed 1 --run 4
"""
import hashlib
import json
import os
import pickle
import time

import numpy as np
import pandas as pd

from . import kalibrasi, skenario, validasi
from .agen import GRUP, G, LABEL_TIPE, TIPE
from .simulasi import Dunia
from . import aturan

CACHE_DIR = kalibrasi.CACHE_DIR
# Naikkan setiap kali perilaku agen/mesin berubah: kalibrasi mikro yang
# tersimpan untuk versi lama tidak boleh dipakai versi baru.
VERSI_MODEL = 25
ITERASI_MIKRO = 6
HARI_MIKRO = 50
SEED_MIKRO = (7919, 104729)

DEFAULTS = {
    'kodes': ','.join(kalibrasi.BAWAAN),
    'n_agen': 2000,
    'hari': 60,
    'n_seed': 6,
    'seed': 1,
    'tick': 10,
    'rezim': 'campur',
    'bandar': 'otomatis',
    'skenario': 'bi_rate_naik',
    'events': None,
    'kalibrasi_ulang': 0,
    'pakai_llm': 0,
    'k_llm': 10,
}
MAKS_RUN_LLM = 3        # agen pemimpin berbayar & lambat: run Monte Carlo dibatasi

FIELDS = [
    {'k': 'kodes', 'label': 'Saham', 'tipe': 'teks'},
    {'k': 'n_agen', 'label': 'Jumlah agen', 'tipe': 'angka', 'min': 300, 'max': 8000, 'step': 100},
    {'k': 'hari', 'label': 'Hari bursa', 'tipe': 'angka', 'min': 15, 'max': 250},
    {'k': 'n_seed', 'label': 'Run Monte Carlo', 'tipe': 'angka', 'min': 1, 'max': 40},
    {'k': 'seed', 'label': 'Seed', 'tipe': 'angka', 'min': 0},
    {'k': 'tick', 'label': 'Lelang per hari', 'tipe': 'angka', 'min': 4, 'max': 30},
    {'k': 'rezim', 'label': 'Rezim IHSG', 'tipe': 'pilih',
     'opsi': [['campur', 'Campur'], ['tenang', 'Tenang'], ['gejolak', 'Bergejolak']]},
    {'k': 'bandar', 'label': 'Bandar', 'tipe': 'pilih',
     'opsi': [['otomatis', 'Otomatis (lapis bawah)'], ['tidak', 'Tidak ada'], ['semua', 'Semua saham']]},
]


# ------------------------------------------------------------ konfigurasi
def normalisasi(config):
    c = dict(DEFAULTS)
    c.update({k: v for k, v in (config or {}).items() if v is not None})
    kodes = c['kodes']
    if isinstance(kodes, str):
        kodes = [x.strip().upper() for x in kodes.replace(';', ',').replace(' ', ',').split(',')]
    kodes = [k for k in dict.fromkeys(kodes) if k]
    if not kodes:
        raise ValueError('Pilih minimal satu saham.')
    if len(kodes) > 15:
        raise ValueError('Maksimal 15 saham sekali jalan (sekarang %d).' % len(kodes))
    c['kodes'] = kodes
    c['n_agen'] = int(np.clip(int(float(c['n_agen'])), 300, 8000))
    c['hari'] = int(np.clip(int(float(c['hari'])), 15, 250))
    c['n_seed'] = int(np.clip(int(float(c['n_seed'])), 1, 40))
    c['seed'] = int(float(c['seed']))
    c['tick'] = int(np.clip(int(float(c['tick'])), 4, 30))
    c['burn'] = 10
    if c['rezim'] not in ('campur', 'tenang', 'gejolak'):
        c['rezim'] = 'campur'
    if c['bandar'] not in ('otomatis', 'tidak', 'semua'):
        c['bandar'] = 'otomatis'
    if isinstance(c.get('events'), str):
        c['events'] = json.loads(c['events']) if c['events'].strip() else None
    c['pakai_llm'] = 1 if int(float(c.get('pakai_llm') or 0)) else 0
    c['k_llm'] = int(np.clip(int(float(c.get('k_llm') or 10)), 3, 60))
    if c['pakai_llm']:
        c['n_seed'] = min(c['n_seed'], MAKS_RUN_LLM)
    return c


def _cfg_dunia(c, kodes):
    return {'kodes': kodes, 'n_agen': c['n_agen'], 'hari': c['hari'], 'burn': c['burn'],
            'tick': c['tick'], 'rezim': c['rezim'], 'bandar': c['bandar'],
            'komposisi': c.get('komposisi'), 'pakai_llm': c.get('pakai_llm', 0),
            'k_llm': c.get('k_llm', 10)}


# --------------------------------------------------------- kalibrasi mikro
def _kunci_mikro(prof, c, kodes):
    isi = json.dumps([sorted(kodes), c['n_agen'], c['tick'], c['bandar'], c.get('komposisi'),
                      prof.get('dibangun'), VERSI_MODEL], sort_keys=True, default=str)
    return hashlib.md5(isi.encode()).hexdigest()[:14]


def kalibrasi_mikro(prof, c, kodes, kanal=None, paksa=False):
    """Setel pengali ukuran order (per kelompok-saham), kedalaman antrean
    pedagang cepat, dan skala berita fundamental supaya volume, porsi
    aktivitas, dan volatilitas baseline mendekati data asli."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    berkas = os.path.join(CACHE_DIR, 'mikro_%s.pkl' % _kunci_mikro(prof, c, kodes))
    if not paksa and os.path.exists(berkas):
        try:
            with open(berkas, 'rb') as fh:
                kal = pickle.load(fh)
            if kanal:
                kanal.log('Kalibrasi mikro dari cache (%s).' % kal.get('dibangun'), 'dim')
            return kal
        except Exception:
            pass

    kal = {'mult': {g: {k: 1.0 for k in kodes} for g in ('ritel', 'institusi', 'asing', 'bandar')},
           'dalam': {k: 1.0 for k in kodes}, 'k_fund': {k: 0.8 for k in kodes},
           'derau': {'ritel': 1.0, 'institusi': 1.0, 'asing': 1.0}, 'iterasi': []}
    cfg = _cfg_dunia(c, kodes)
    cfg.update({'hari': HARI_MIKRO, 'burn': 10, 'rezim': 'campur', 'pakai_llm': 0})
    for it in range(ITERASI_MIKRO):
        if kanal and kanal.berhenti():
            break
        # dua seed per putaran: satu jalur bisa kebetulan memuat siklus
        # bandar (atau tidak) dan menyeret kalibrasi saham kecil
        dunia = []
        for sd in SEED_MIKRO:
            w = Dunia(prof, cfg, seed=sd, events=[], kal=kal)
            w.jalan()
            dunia.append(w)
        sts = [validasi.statistik_dunia(x) for x in dunia]
        st = {'ret': np.concatenate([x['ret'] for x in sts]), 'vol': np.concatenate([x['vol'] for x in sts])}
        catatan = {}
        for j, k in enumerate(kodes):
            ps = prof['saham'][k]
            # penaksir kokoh di kedua sisi: satu hari ekstrem di dua seed
            # kalibrasi tidak boleh menyetel ulang seluruh saham
            vol_sim = kalibrasi.vol_kokoh(st['ret'][:, j])
            vol_tgt = kalibrasi.vol_kokoh(ps['ret_asli']) if ps.get('ret_asli') else w.sigma[j]
            rasio_v = vol_sim / vol_tgt if vol_tgt > 0 else 1.0
            # kedalaman antrean -> snapshot ORDER_BOOK asli (kalau ada);
            # volatilitas -> skala berita fundamental. Dulu volatilitas
            # disetel lewat kedalaman, dan hasilnya antrean BBCA 5x antrean
            # asli: pasar yang terlalu tebal untuk dipercaya.
            bn = ps.get('buku_nyata')
            dalam_twin = [x['buku'].get(k, {}).get('dalam_5_lot') for x in sts]
            dalam_twin = [v for v in dalam_twin if v]
            if bn and dalam_twin:
                tgt = 0.5 * (bn['dalam_5_bid_lot'] + bn['dalam_5_offer_lot'])
                d = kal['dalam'][k] * float(np.clip((tgt / np.median(dalam_twin)) ** 0.8, 0.5, 2.0))
                kal['dalam'][k] = float(np.clip(d, 0.05, 20.0))
            kf = kal['k_fund'][k] * float(np.clip((1.0 / max(rasio_v, 1e-6)) ** 1.5, 0.6, 1.6))
            kal['k_fund'][k] = float(np.clip(kf, 0.05, 2.5))

            akt = w.info['akt'][j]
            B = w.burn
            bruto = np.mean([(x.rek['beli'][B:, :, j] + x.rek['jual'][B:, :, j]).mean(axis=0) for x in dunia], axis=0)
            adv = ps['adv_lot']
            ada_bandar = j in w.info['saham_bandar']
            target = {
                'ritel': akt['ritel'] * 2 * adv * 0.85,
                'asing': akt['asing'] * 2 * adv * 0.85,
                'institusi': akt['lokal'] * 2 * adv * 0.85 * (0.7 if ada_bandar else 1.0),
            }
            for g, tg in target.items():
                nyata = bruto[G[g]]
                if nyata <= 0:
                    faktor = 2.0
                else:
                    faktor = float(np.clip((tg / nyata) ** 0.8, 0.33, 3.0))
                kal['mult'][g][k] = float(np.clip(kal['mult'][g][k] * faktor, 0.02, 80.0))
            catatan[k] = {'vol_rasio': round(rasio_v, 3),
                          'volume_rasio': round(float(st['vol'][:, j].mean() / adv), 3),
                          'k_fund': round(kal['k_fund'][k], 3), 'dalam': round(kal['dalam'][k], 3)}
        # keberagaman tiap kelompok: median keterarahan arus (|netto|/bruto
        # per hari) twin vs JSON broker asli, dirata-rata lintas saham
        catatan['_searah'] = {}
        for g, gi, kunci in (('ritel', [G['ritel']], 'ritel'), ('asing', [G['asing']], 'asing'),
                             ('institusi', [G['institusi'], G['bandar']], 'lokal')):
            tw, asli = [], []
            for j, k in enumerate(kodes):
                a_ = ((prof['saham'][k].get('bruto') or {}).get('searah') or {}).get(kunci)
                if a_ is None:
                    continue
                vals = []
                for x in dunia:
                    B = x.burn
                    b = x.rek['beli_nilai'][B:, gi, j].sum(axis=1)
                    s_ = x.rek['jual_nilai'][B:, gi, j].sum(axis=1)
                    ok = (b + s_) > 0
                    vals.extend((np.abs(b - s_)[ok] / (b + s_)[ok]).tolist())
                if vals:
                    tw.append(float(np.median(vals)))
                    asli.append(a_)
            if tw:
                rasio = float(np.mean(tw)) / max(float(np.mean(asli)), 1e-3)
                kal['derau'][g] = float(np.clip(kal['derau'][g] * np.clip(rasio ** 0.8, 0.6, 1.7), 0.3, 6.0))
                catatan['_searah'][g] = {'twin': round(float(np.mean(tw)), 3), 'asli': round(float(np.mean(asli)), 3),
                                         'derau': round(kal['derau'][g], 3)}
        kal['iterasi'].append(catatan)
        if kanal:
            ringkas = ', '.join('%s vol x%.2f volume x%.2f' % (k, v['vol_rasio'], v['volume_rasio'])
                                for k, v in catatan.items() if not k.startswith('_'))
            ringkas += ' | searah ' + ', '.join('%s %.2f/%.2f' % (g, v['twin'], v['asli'])
                                                for g, v in catatan.get('_searah', {}).items())
            kanal.log('Putaran %d: %s' % (it + 1, ringkas), 'dim')
            kanal.maju(0.04 + 0.12 * (it + 1) / ITERASI_MIKRO)
    kal['dibangun'] = time.strftime('%Y-%m-%d %H:%M')
    try:
        with open(berkas, 'wb') as fh:
            pickle.dump(kal, fh)
    except Exception:
        pass
    return kal


# ------------------------------------------------------------- kumpulkan
def _kumpul(w, simpan_detail=False):
    """Ambil yang perlu dari satu dunia (tanpa menyimpan seluruh dunia)."""
    B = w.burn
    r = w.rek
    pop = w.pop
    akhir = w.kekayaan()
    awal = w.kekayaan_awal if w.kekayaan_awal is not None else akhir
    awal = awal + w.setoran          # modal yang disetor di tengah jalan bukan untung
    pnl_grup, pnl_tipe = {}, {}
    for gi, g in enumerate(GRUP):
        m = pop.grup == gi
        if m.any() and awal[m].sum() > 0:
            pnl_grup[g] = {'pct': float((akhir[m].sum() / awal[m].sum() - 1) * 100),
                           'rp': float(akhir[m].sum() - awal[m].sum())}
    for ti, t in enumerate(TIPE):
        m = pop.tipe == ti
        if m.any() and awal[m].sum() > 0:
            pnl_tipe[t] = {'pct': float((akhir[m].sum() / awal[m].sum() - 1) * 100),
                           'rp': float(akhir[m].sum() - awal[m].sum())}
    ritel = (pop.grup == G['ritel']) & (awal > 0)
    ret_ritel = (akhir[ritel] / awal[ritel] - 1) * 100
    out = {
        'close': r['close'][B:].copy(),
        'close0': r['close'][B - 1].copy() if B > 0 else w.P0.copy(),
        'vol': r['vol'][B:].copy(),
        'nilai': r['nilai'][B:].copy(),
        'ihsg': r['ihsg'][B:].copy(),
        'ihsg0': float(r['ihsg'][B - 1]) if B > 0 else w.ihsg0,
        'net': (r['beli_nilai'][B:] - r['jual_nilai'][B:]).copy(),      # (D, G, S)
        'net_lot': (r['beli'][B:] - r['jual'][B:]).copy(),
        'ara': r['ara'][B:].sum(axis=0), 'arb': r['arb'][B:].sum(axis=0),
        'pnl_grup': pnl_grup, 'pnl_tipe': pnl_tipe,
        'ret_ritel': ret_ritel,
        'n_bandar': len(w.bandar),
    }
    if simpan_detail:
        out['open'] = r['open'][B:].copy()
        out['high'] = r['high'][B:].copy()
        out['low'] = r['low'][B:].copy()
        out['V'] = r['V'][B:].copy()
        out['sent'] = r['sent'][B:].copy()
        out['bid'] = r['bid'][B:].copy()
        out['offer'] = r['offer'][B:].copy()
        out['bid_harga'] = r['bid_harga'][B:].copy()
        out['offer_harga'] = r['offer_harga'][B:].copy()
        out['tick_harga'] = r['tick_harga'][B:].copy()
        out['bandar'] = [b for b in w.rek_bandar if b['hari'] >= 0]
        out['bandar_pnl'] = []
        for b in w.bandar:
            nilai = float(w.pop.kas[b['a']] + w.pop.pos[b['a'], b['s']] * w.harga[b['s']] * aturan.LOT)
            out['bandar_pnl'].append({'kode': w.kodes[b['s']], 'agen': int(b['a']), 'otomatis': b['otomatis'],
                                      'pnl_pct': (nilai / b['modal_awal'] - 1) * 100 if b['modal_awal'] > 0 else None})
        out['pemimpin'] = list(w.log_pemimpin)
    return out


def _q(x, axis=0):
    """p10/p50/p90 sepanjang axis seed."""
    return {'p10': np.percentile(x, 10, axis=axis), 'p50': np.percentile(x, 50, axis=axis),
            'p90': np.percentile(x, 90, axis=axis)}


def _daftar(a, d=4):
    return [None if not np.isfinite(v) else round(float(v), d) for v in np.asarray(a).ravel()]


def _qlist(q, d=4):
    return {k: _daftar(v, d) for k, v in q.items()}


def _tanggal(prof, kodes, D):
    akhir = max(pd.Timestamp(prof['saham'][k]['tanggal_harga']) for k in kodes)
    return [str(t.date()) for t in pd.bdate_range(akhir + pd.Timedelta(days=1), periods=D)]


# ------------------------------------------------------------- ringkasan
def ringkas(prof, c, kodes, events, base, sken, stats, kal, peringatan, info_sken):
    S, D = len(kodes), c['hari']
    tanggal = _tanggal(prof, kodes, D)
    mulai_ev = min([e['hari'] for e in events], default=0)
    hasil = {
        'kodes': kodes,
        'tanggal': tanggal,
        'hari_event': sorted({e['hari'] for e in events}),
        'mulai_jendela': mulai_ev,
        'events': [{k: v for k, v in e.items() if k != 'id'} for e in events],
        'skenario': info_sken,
        'n_seed': len(base),
        'sektor': {k: prof['saham'][k].get('sektor') for k in kodes},
        'harga0': {k: float(prof['saham'][k]['harga']) for k in kodes},
    }

    # ---- harga & IHSG
    harga, efek = {}, {}
    cb = np.stack([b['close'] for b in base])        # (n, D, S)
    cs = np.stack([s['close'] for s in sken])
    c0 = np.stack([b['close0'] for b in base])       # (n, S)
    selisih = (cs / cb - 1.0) * 100.0
    for j, k in enumerate(kodes):
        harga[k] = {
            'base': _qlist(_q(cb[:, :, j]), 2),
            'sken': _qlist(_q(cs[:, :, j]), 2),
            'selisih': _qlist(_q(selisih[:, :, j]), 3),
        }
        med = np.percentile(selisih[:, :, j], 50, axis=0)
        jendela = slice(mulai_ev, D)
        rb = np.diff(np.log(np.concatenate([c0[:, None, j], cb[:, :, j]], axis=1)), axis=1)[:, jendela]
        rs = np.diff(np.log(np.concatenate([c0[:, None, j], cs[:, :, j]], axis=1)), axis=1)[:, jendela]
        vb = np.stack([b['vol'][:, j] for b in base])[:, jendela].mean()
        vs = np.stack([s['vol'][:, j] for s in sken])[:, jendela].mean()
        efek[k] = {
            'akhir': float(med[-1]),
            'akhir_p10': float(np.percentile(selisih[:, -1, j], 10)),
            'akhir_p90': float(np.percentile(selisih[:, -1, j], 90)),
            'terdalam': float(med.min()), 'hari_terdalam': int(med.argmin()),
            'tertinggi': float(med.max()), 'hari_tertinggi': int(med.argmax()),
            'peluang_lebih_rendah': float((selisih[:, -1, j] < 0).mean()),
            'vol_base': float(rb.std(axis=1).mean() * 100), 'vol_sken': float(rs.std(axis=1).mean() * 100),
            'volume_rasio': float(vs / vb) if vb > 0 else None,
            'ara_base': float(np.mean([b['ara'][j] for b in base])),
            'ara_sken': float(np.mean([s['ara'][j] for s in sken])),
            'arb_base': float(np.mean([b['arb'][j] for b in base])),
            'arb_sken': float(np.mean([s['arb'][j] for s in sken])),
        }
    ib = np.stack([b['ihsg'] for b in base])
    isk = np.stack([s['ihsg'] for s in sken])
    sel_i = (isk / ib - 1.0) * 100
    hasil['ihsg'] = {'base': _qlist(_q(ib), 1), 'sken': _qlist(_q(isk), 1), 'selisih': _qlist(_q(sel_i), 3),
                     'level0': float(base[0]['ihsg0']), 'sumber': prof['ihsg']['sumber']}
    med_i = np.percentile(sel_i, 50, axis=0)
    efek['IHSG'] = {'akhir': float(med_i[-1]), 'akhir_p10': float(np.percentile(sel_i[:, -1], 10)),
                    'akhir_p90': float(np.percentile(sel_i[:, -1], 90)),
                    'terdalam': float(med_i.min()), 'hari_terdalam': int(med_i.argmin()),
                    'tertinggi': float(med_i.max()), 'hari_tertinggi': int(med_i.argmax()),
                    'peluang_lebih_rendah': float((sel_i[:, -1] < 0).mean())}
    hasil['harga'] = harga
    hasil['efek'] = efek

    # ---- arus netto per kelompok (Rp miliar), median antar-seed
    arus = {}
    nb = np.stack([b['net'] for b in base]) / 1e9      # (n, D, G, S)
    ns = np.stack([s['net'] for s in sken]) / 1e9
    for j, k in enumerate(kodes):
        per = {}
        for gi, g in enumerate(GRUP):
            if np.abs(nb[:, :, gi, j]).sum() == 0 and np.abs(ns[:, :, gi, j]).sum() == 0:
                continue
            tb = nb[:, mulai_ev:, gi, j].sum(axis=1)
            ts = ns[:, mulai_ev:, gi, j].sum(axis=1)
            per[g] = {
                'base': _daftar(np.median(nb[:, :, gi, j], axis=0), 2),
                'sken': _daftar(np.median(ns[:, :, gi, j], axis=0), 2),
                'total_base': float(np.median(tb)), 'total_sken': float(np.median(ts)),
                'total_selisih': float(np.median(ts - tb)),
                'selisih_p10': float(np.percentile(ts - tb, 10)),
                'selisih_p90': float(np.percentile(ts - tb, 90)),
            }
        arus[k] = per
    hasil['arus'] = arus

    # ---- untung-rugi per kelompok & watak
    def _pnl(kunci):
        keluar = {}
        nama = set()
        for x in base + sken:
            nama.update(x[kunci].keys())
        for g in nama:
            pb = [x[kunci][g]['pct'] for x in base if g in x[kunci]]
            psk = [x[kunci][g]['pct'] for x in sken if g in x[kunci]]
            rb = [x[kunci][g]['rp'] for x in base if g in x[kunci]]
            rs = [x[kunci][g]['rp'] for x in sken if g in x[kunci]]
            keluar[g] = {'base_pct': float(np.median(pb)) if pb else None,
                         'sken_pct': float(np.median(psk)) if psk else None,
                         'base_rp': float(np.median(rb)) if rb else None,
                         'sken_rp': float(np.median(rs)) if rs else None,
                         'label': LABEL_TIPE.get(g, g)}
        return keluar
    hasil['pnl_grup'] = _pnl('pnl_grup')
    hasil['pnl_tipe'] = _pnl('pnl_tipe')
    tepi = np.linspace(-40, 40, 33)
    rb = np.clip(np.concatenate([b['ret_ritel'] for b in base]), -39.99, 39.99)
    rs = np.clip(np.concatenate([s['ret_ritel'] for s in sken]), -39.99, 39.99)
    hasil['ritel_sebaran'] = {
        'tepi': _daftar(tepi, 1),
        'base': [int(v) for v in np.histogram(rb, tepi)[0]],
        'sken': [int(v) for v in np.histogram(rs, tepi)[0]],
        'base_rugi_pct': float((rb < 0).mean() * 100), 'sken_rugi_pct': float((rs < 0).mean() * 100),
        'base_rugi10_pct': float((rb < -10).mean() * 100), 'sken_rugi10_pct': float((rs < -10).mean() * 100),
    }

    # ---- contoh satu jalur (seed pertama): lilin, intraday hari event, buku, bandar
    b0, s0 = base[0], sken[0]
    contoh = {}
    for j, k in enumerate(kodes):
        contoh[k] = {
            'base': {f: _daftar(b0[f][:, j], 2) for f in ('open', 'high', 'low', 'close')},
            'sken': {f: _daftar(s0[f][:, j], 2) for f in ('open', 'high', 'low', 'close')},
            'vol_base': _daftar(b0['vol'][:, j], 0), 'vol_sken': _daftar(s0['vol'][:, j], 0),
            'V_base': _daftar(b0['V'][:, j], 2), 'V_sken': _daftar(s0['V'][:, j], 2),
            'sent_sken': _daftar(s0['sent'][:, j], 3),
        }
        hari_ev = mulai_ev if events else max(D // 2, 0)
        contoh[k]['intraday'] = {
            'hari': hari_ev,
            'base': _daftar(b0['tick_harga'][hari_ev, :, j], 2),
            'sken': _daftar(s0['tick_harga'][hari_ev, :, j], 2),
        }
        buku = {}
        for h in sorted({hari_ev, min(hari_ev + 1, D - 1), D - 1}):
            buku[str(h)] = {
                'bid': _daftar(s0['bid'][h, j], 0), 'bid_harga': _daftar(s0['bid_harga'][h, j], 2),
                'offer': _daftar(s0['offer'][h, j], 0), 'offer_harga': _daftar(s0['offer_harga'][h, j], 2),
                'base_bid': _daftar(b0['bid'][h, j], 0), 'base_offer': _daftar(b0['offer'][h, j], 0),
            }
        contoh[k]['buku'] = buku
    hasil['contoh'] = contoh
    hasil['bandar'] = {'base': _ringkas_bandar(b0['bandar'], b0.get('bandar_pnl')),
                       'sken': _ringkas_bandar(s0['bandar'], s0.get('bandar_pnl'))}
    hasil['pemimpin'] = {'base': b0.get('pemimpin') or [], 'sken': s0.get('pemimpin') or []}

    hasil['rapor'] = validasi.rapor(prof, kodes, stats)
    hasil['kalibrasi'] = {
        'ihsg': {k: prof['ihsg'][k] for k in ('sumber', 'dari', 'sampai', 'level', 'vol_harian')},
        'pasar': prof.get('pasar'),
        'catatan': prof.get('catatan', []),
        'mikro': {'dalam': kal.get('dalam'), 'k_fund': kal.get('k_fund'),
                  'putaran_terakhir': (kal.get('iterasi') or [{}])[-1], 'dibangun': kal.get('dibangun')},
        'saham': {k: {
            'harga': prof['saham'][k]['harga'], 'tanggal_harga': prof['saham'][k]['tanggal_harga'],
            'adv_lot': prof['saham'][k]['adv_lot'], 'adv_nilai': prof['saham'][k]['adv_nilai'],
            'beta': prof['saham'][k]['beta'], 'vol_harian': (prof['saham'][k].get('fakta') or {}).get('vol_harian'),
            'pemilik': (prof['saham'][k].get('pemilik') or {}).get('porsi_pemilik'),
            'pct_pengendali': (prof['saham'][k].get('pemilik') or {}).get('pct_pengendali'),
            'mcap': (prof['saham'][k].get('pemilik') or {}).get('mcap'),
            'aktivitas': (prof['saham'][k].get('bruto') or {}).get('porsi'),
            'bandar_data': ((prof.get('perilaku') or {}).get(k) or {}).get('bandar'),
        } for k in kodes},
    }
    hasil['peringatan'] = peringatan
    return hasil


def _ringkas_bandar(rek, pnl=None):
    pnl_peta = {(p['kode'], p['agen']): p['pnl_pct'] for p in (pnl or [])}
    per = {}
    for b in rek:
        kunci = '%s#%d' % (b['kode'], b['agen'])
        per.setdefault(kunci, {'kode': b['kode'], 'otomatis': b['otomatis'], 'hari': [], 'inv': [],
                               'modal_rata': [], 'fase': [], 'kas': [],
                               'pnl_pct': pnl_peta.get((b['kode'], b['agen']))})
        p = per[kunci]
        p['hari'].append(b['hari'])
        p['inv'].append(round(b['inv']))
        p['modal_rata'].append(None if b['modal_rata'] is None else round(b['modal_rata'], 2))
        p['fase'].append(b['fase'])
        p['kas'].append(round(b['kas'] / 1e9, 3))
    return list(per.values())


# -------------------------------------------------------------- runner
def jalankan(config, kanal):
    t0 = time.time()
    c = normalisasi(config)
    kanal.tahap('Memuat data & kalibrasi profil')
    prof = kalibrasi.profil(c['kodes'])
    kodes = [k for k in c['kodes'] if k in prof['saham']]
    for cat in prof.get('catatan', []):
        kanal.log(cat, 'warn')
    if not kodes:
        raise ValueError('Tidak ada saham yang punya data.')
    kanal.log('IHSG: %s, %s s/d %s, level %.0f.' % (prof['ihsg']['sumber'], prof['ihsg']['dari'],
                                                    prof['ihsg']['sampai'], prof['ihsg']['level']))
    for k in kodes:
        ps = prof['saham'][k]
        pm = (ps.get('pemilik') or {}).get('porsi_pemilik') or {}
        akt = (ps.get('bruto') or {}).get('porsi') or {}
        kanal.log('%s: harga %s, ADV %s lot, vol %.2f%%, beta %.2f | pemilik ritel %.0f%% asing %.0f%% '
                  '| aktivitas ritel %.0f%% asing %.0f%%' % (
                      k, '{:,.0f}'.format(ps['harga']), '{:,.0f}'.format(ps['adv_lot']),
                      100 * ((ps.get('fakta') or {}).get('vol_harian') or 0), ps['beta'],
                      100 * pm.get('ritel', 0), 100 * pm.get('asing', 0),
                      100 * akt.get('ritel', 0), 100 * akt.get('asing', 0)), 'dim')
    kanal.maju(0.03)

    # ---- skenario
    if c.get('events') is not None:
        events_mentah = c['events']
        info_sken = {'kunci': c.get('skenario') or 'kustom', 'judul': c.get('judul_skenario') or 'Skenario kustom',
                     'deskripsi': c.get('deskripsi_skenario') or ''}
    else:
        p = skenario.PRESET.get(c['skenario']) or skenario.PRESET['normal']
        events_mentah = p['events']
        info_sken = {'kunci': c['skenario'], 'judul': p['judul'], 'deskripsi': p['deskripsi']}
    events, peringatan = skenario.siapkan(events_mentah, prof, kodes, c['hari'])
    for p_ in peringatan:
        kanal.log(p_, 'warn')
    for e in events:
        kanal.log('Event hari %d: %s %s besar %s durasi %d%s' % (
            e['hari'], skenario.JENIS[e['jenis']]['label'], ','.join(e['target_kode']), e['besar'],
            e['durasi'], (' (dibantah hari +%d)' % e['bantah_hari']) if e.get('bantah_hari') else ''))
    n_cad = skenario.butuh_cadangan(events)
    if c['pakai_llm']:
        from . import llm
        st = llm.status()
        if not st['aktif']:
            raise RuntimeError('Agen pemimpin Claude diminta, tapi: ' + st['alasan'])
        n_pemimpin = 2 + (len(kodes) if c['bandar'] == 'semua' else 2) + n_cad
        n_konsul = int(np.ceil(c['hari'] / c['k_llm']))
        kanal.log('Agen pemimpin Claude (%s) aktif: konsultasi tiap %d hari, perkiraan paling banyak '
                  '%d panggilan API (%d pemimpin x %d konsultasi x 2 dunia x %d run). Hasil tidak bisa '
                  'diulang persis.' % (llm.MODEL, c['k_llm'], n_pemimpin * n_konsul * 2 * c['n_seed'],
                                       n_pemimpin, n_konsul, c['n_seed']), 'warn')

    kanal.tahap('Kalibrasi mikro (volume, porsi, volatilitas)')
    kal = kalibrasi_mikro(prof, c, kodes, kanal, paksa=bool(int(c.get('kalibrasi_ulang') or 0)))
    if kanal.berhenti():
        return None

    kanal.tahap('Monte Carlo: %d pasang dunia' % c['n_seed'])
    cfg = _cfg_dunia(c, kodes)
    base, sken, stats = [], [], []
    for i in range(c['n_seed']):
        sd = c['seed'] + i
        t1 = time.time()
        wb = Dunia(prof, cfg, sd, [], kal, n_cad)
        if not wb.jalan(kanal.berhenti):
            break
        ws = Dunia(prof, cfg, sd, events, kal, n_cad)
        if not ws.jalan(kanal.berhenti):
            break
        base.append(_kumpul(wb, simpan_detail=(i == 0)))
        sken.append(_kumpul(ws, simpan_detail=(i == 0)))
        stats.append(validasi.statistik_dunia(wb))
        sel = (ws.rek['close'][-1] / wb.rek['close'][-1] - 1) * 100
        kanal.log('Seed %d (%.1f detik, %d agen): selisih akhir %s' % (
            sd, time.time() - t1, wb.N, ', '.join('%s %+.1f%%' % (k, v) for k, v in zip(kodes, sel))), 'dim')
        kanal.maju(0.18 + 0.78 * (i + 1) / c['n_seed'])
    if not base:
        return None

    kanal.tahap('Meringkas & rapor realisme')
    hasil = ringkas(prof, c, kodes, events, base, sken, stats, kal, peringatan, info_sken)
    hasil['config'] = {k: v for k, v in c.items() if k != 'events'}
    hasil['jumlah_agen'] = {k: v for k, v in (Dunia(prof, cfg, c['seed'], [], kal, 0).info['jumlah']).items()}
    rp = hasil['rapor']['ringkas']
    ef = hasil['efek']
    terdampak = sorted(kodes, key=lambda k: -abs(ef[k]['akhir']))[0]
    hasil['ringkas'] = {
        'skenario': info_sken['judul'],
        'ihsg_akhir': round(ef['IHSG']['akhir'], 2),
        'terdampak': '%s %+.1f%%' % (terdampak, ef[terdampak]['akhir']),
        'realisme': '%d/%d' % (rp['lolos'], rp['lolos'] + rp['gagal']),
        'n_seed': len(base),
    }
    hasil['judul_config'] = '%s · %d saham · %d agen · %d hari · %d run' % (
        info_sken['judul'], len(kodes), c['n_agen'], c['hari'], len(base))
    hasil['durasi_detik'] = round(time.time() - t0, 1)
    kanal.log('IHSG twin: %+.2f%% vs baseline di akhir (p10 %+.2f, p90 %+.2f). Realisme %s lolos.' % (
        ef['IHSG']['akhir'], ef['IHSG']['akhir_p10'], ef['IHSG']['akhir_p90'], hasil['ringkas']['realisme']), 'ok')
    return hasil


# ------------------------------------------------------- daftar ke riset
def _daftar_riset():
    from .. import research
    research.register(
        key='digital_twin',
        label='Market Digital Twin',
        ringkas='Klon digital beberapa saham BEI yang dijalankan ribuan agen berpersona; '
                'membandingkan dunia dengan dan tanpa skenario.',
        runner=jalankan,
        fields=FIELDS,
        defaults=DEFAULTS,
        halaman='digital-twin',
    )


_daftar_riset()


# ------------------------------------------------------------------ CLI
class _KanalCetak:
    def __init__(self):
        self.t0 = time.time()

    def log(self, pesan, level='info'):
        print('[%6.1f] %s' % (time.time() - self.t0, pesan), flush=True)

    def tahap(self, nama):
        self.log('== %s ==' % nama)

    def maju(self, frac):
        pass

    def berhenti(self):
        return False


def _uji_nol(prof, kodes, c, kal):
    """Skenario kosong harus memberi selisih NOL persis (seed sama)."""
    cfg = _cfg_dunia(c, kodes)
    a = Dunia(prof, cfg, 3, [], kal, 0)
    a.jalan()
    b = Dunia(prof, cfg, 3, [], kal, 0)
    b.jalan()
    return float(np.abs(a.rek['close'] - b.rek['close']).max())


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--preset', default='bi_rate_naik')
    ap.add_argument('--kodes', default=DEFAULTS['kodes'])
    ap.add_argument('--agen', type=int, default=2000)
    ap.add_argument('--hari', type=int, default=60)
    ap.add_argument('--run', type=int, default=4)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--kalibrasi-ulang', action='store_true')
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    h = jalankan({'kodes': a.kodes, 'skenario': a.preset, 'n_agen': a.agen, 'hari': a.hari,
                  'n_seed': a.run, 'seed': a.seed, 'kalibrasi_ulang': int(a.kalibrasi_ulang)}, _KanalCetak())
    print(json.dumps(h['ringkas'], ensure_ascii=False))
    for k, e in h['efek'].items():
        print('%-5s akhir %+6.2f%% [%+.2f, %+.2f]  terdalam %+6.2f%% (h%d)' % (
            k, e['akhir'], e['akhir_p10'], e['akhir_p90'], e['terdalam'], e['hari_terdalam']))
    for k, baris in h['rapor']['per_saham'].items():
        print('--', k)
        for b in baris:
            print('   %-55s twin %-8s asli %-8s %-10s %s' % (
                b['nama'], None if b['twin'] is None else round(b['twin'], 3),
                None if b['asli'] is None else round(b['asli'], 3), b['jenis'], b['ok']))
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as fh:
            json.dump(h, fh, ensure_ascii=False, default=str)
