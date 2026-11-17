"""
Rapor realisme: seberapa mirip dunia baseline twin dengan pasar asli.

DUA JENIS BARIS, JANGAN DICAMPUR
  'dicocokkan'  volatilitas harian (penaksir kokoh), volume, porsi aktivitas
                dan keterarahan arus tiap kelompok, serta kedalaman antrean
                DISETEL supaya sama (kalibrasi mikro di jalan.py). Kalau
                cocok, itu bukan prestasi -- itu memang targetnya.
  'muncul'      tidak pernah disetel: ekor gemuk, gejolak yang mengumpul,
                tidak adanya autokorelasi return, volume yang membesar saat
                harga bergerak, spread, dan ARAH arus tiap kelompok terhadap
                return hari itu & 5 hari sebelumnya (ritel menampung, asing
                searah harga). Kalau ini cocok, perilaku agennya menghasilkan
                pasar yang berbentuk seperti pasar asli. Kalau meleset, rapor
                bilang meleset.

Sebagian fakta (ekor gemuk, gejolak mengumpul) bisa DIWARISI dari faktor
IHSG yang dibootstrap dari IHSG asli. Karena itu ada baris tambahan yang
memeriksa hal yang sama pada return SISA (setelah bagian IHSG dibuang) --
yang itu tidak bisa diwarisi.
"""
import numpy as np

from .kalibrasi import fakta_return, vol_kokoh
from .agen import GRUP, G

# Ambang lulus -- sengaja longgar dan ditulis terang, bukan dicari supaya lulus.
TOL_RASIO = 3.0       # faktor kelipatan yang masih dianggap "setara"


def _rasio_ok(twin, asli, tol=TOL_RASIO):
    if twin is None or asli is None:
        return None
    if asli == 0:
        return abs(twin) < 0.05
    if np.sign(twin) != np.sign(asli):
        return False
    r = abs(twin) / max(abs(asli), 1e-9)
    return (1.0 / tol) <= r <= tol


def _kor(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10 or x[ok].std() == 0 or y[ok].std() == 0:
        return None
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def statistik_dunia(w):
    """Ringkas satu dunia baseline: return, sisa, volume, korelasi arus
    persona, kedalaman buku. Dipanggil per seed lalu digabung."""
    B = w.burn
    r = w.rek
    close = r['close'][B - 1 if B > 0 else 0:]
    ret = np.diff(np.log(close), axis=0)                         # (D, S)
    ihsg = r['ihsg'][B - 1 if B > 0 else 0:]
    m = np.diff(np.log(ihsg))
    vol = r['vol'][B:]
    nilai = r['nilai'][B:]
    keluar = {'ret': ret, 'm': m, 'vol': vol, 'kor': {}, 'buku': {}, 'porsi': {}}
    for j, k in enumerate(w.kodes):
        rr = ret[:, j]
        r5_lalu = np.r_[np.full(5, np.nan), np.convolve(rr, np.ones(5), 'valid')[:-1]]
        net = (r['beli_nilai'][B:, :, j] - r['jual_nilai'][B:, :, j])
        nil = np.maximum(nilai[:, j], 1.0)
        kor = {}
        for g, gi in (('ritel', G['ritel']), ('asing', G['asing'])):
            x = net[:, gi] / nil
            kor[g] = {'hari_sama': _kor(x, rr), 'tren_5h_lalu': _kor(x, r5_lalu[:len(rr)])}
        lokal = (net[:, G['institusi']] + net[:, G['bandar']]) / nil
        kor['lokal'] = {'hari_sama': _kor(lokal, rr), 'tren_5h_lalu': _kor(lokal, r5_lalu[:len(rr)])}
        keluar['kor'][k] = kor
        # buku: kedalaman 5 level per sisi & spread dalam fraksi, akhir hari
        bid = r['bid'][B:, j, :5].sum(axis=1)
        off = r['offer'][B:, j, :5].sum(axis=1)
        bh = r['bid_harga'][B:, j, 0]
        oh = r['offer_harga'][B:, j, 0]
        ok = (bh > 0) & (oh > 0) & (oh > bh)
        from .aturan import fraksi
        spread = ((oh - bh) / fraksi(bh))[ok] if ok.any() else np.array([])
        keluar['buku'][k] = {
            'dalam_5_lot': float(np.median(0.5 * (bid + off))) if len(bid) else None,
            'spread_fraksi': float(np.median(spread)) if len(spread) else None,
        }
        searah = {}
        for g, gi in (('ritel', [G['ritel']]), ('asing', [G['asing']]), ('lokal', [G['institusi'], G['bandar']])):
            b = r['beli_nilai'][B:, gi, j].sum(axis=1)
            s_ = r['jual_nilai'][B:, gi, j].sum(axis=1)
            ok = (b + s_) > 0
            if ok.any():
                searah[g] = float(np.median(np.abs(b - s_)[ok] / (b + s_)[ok]))
        keluar.setdefault('searah', {})[k] = searah
        bruto = (r['beli_nilai'][B:, :, j] + r['jual_nilai'][B:, :, j]).sum(axis=0)
        inti = bruto[G['ritel']] + bruto[G['asing']] + bruto[G['institusi']] + bruto[G['bandar']]
        if inti > 0:
            keluar['porsi'][k] = {
                'ritel': float(bruto[G['ritel']] / inti),
                'asing': float(bruto[G['asing']] / inti),
                'lokal': float((bruto[G['institusi']] + bruto[G['bandar']]) / inti),
                'cepat_dari_total': float(bruto[G['cepat']] / max(bruto.sum(), 1)),
            }
    return keluar


def _median_fakta(daftar):
    daftar = [f for f in daftar if f]
    if not daftar:
        return {}
    kunci = set.intersection(*[set(f) for f in daftar])
    return {k: float(np.median([f[k] for f in daftar])) for k in kunci}


def rapor(prof, kodes, stat_list):
    """Bandingkan baseline semua seed dengan data asli.

    Statistik bentuk (ekor, gejolak mengumpul, autokorelasi, volume-gejolak)
    dihitung PER JENDELA dengan panjang sama di kedua sisi: per seed di twin,
    per potongan tak bertumpuk sepanjang D hari di 2 tahun data asli, lalu
    dimedian. Return {'per_saham': {...}, 'ringkas': {...}}."""
    from .kalibrasi import fakta_jendela
    per_saham = {}
    lolos = gagal = 0
    D = int(stat_list[0]['ret'].shape[0]) if stat_list else 60
    for j, k in enumerate(kodes):
        ps = prof['saham'][k]
        if ps.get('ret_asli'):
            asli = fakta_jendela(ps['ret_asli'], ps.get('vol_asli'), D)
        else:
            asli = ps.get('fakta') or {}
        asli_penuh = ps.get('fakta') or {}
        f_seed, f_sisa_seed = [], []
        for s in stat_list:
            rr, mm = s['ret'][:, j], s['m'][:len(s['ret'])]
            f_seed.append(fakta_return(rr, s['vol'][:, j]))
            b = np.cov(rr, mm)[0, 1] / mm.var() if mm.var() > 0 else 0.0
            f_sisa_seed.append(fakta_return(rr - b * mm))
        f_twin = _median_fakta(f_seed)
        f_sisa = _median_fakta(f_sisa_seed)
        vol = np.concatenate([s['vol'][:, j] for s in stat_list])
        baris = []

        def tambah(nama, twin, asli_v, jenis, ok, catatan=''):
            nonlocal lolos, gagal
            if jenis == 'muncul' and ok is not None:
                if ok:
                    lolos += 1
                else:
                    gagal += 1
            baris.append({'nama': nama, 'twin': twin, 'asli': asli_v, 'jenis': jenis,
                          'ok': None if ok is None else bool(ok), 'catatan': catatan})

        tv = float(np.median([vol_kokoh(s['ret'][:, j]) for s in stat_list]))
        av = vol_kokoh(ps['ret_asli']) if ps.get('ret_asli') else asli_penuh.get('vol_harian')
        tambah('Volatilitas harian (kokoh)', tv, av, 'dicocokkan', _rasio_ok(tv, av, 1.3),
               '1,4826 x median simpangan absolut -- penaksir yang dipakai kalibrasi, tidak '
               'diseret satu-dua hari ekstrem (itu urusan baris ekor gemuk); asli = 2 tahun terakhir')
        vt = float(vol.mean()) if len(vol) else None
        tambah('Volume rata-rata (lot/hari)', vt, ps['adv_lot'], 'dicocokkan', _rasio_ok(vt, ps['adv_lot'], 1.5),
               'asli = rata-rata 60 hari terakhir (Summary)')

        porsi_twin = {}
        for s in stat_list:
            for g, v in (s['porsi'].get(k) or {}).items():
                porsi_twin.setdefault(g, []).append(v)
        porsi_twin = {g: float(np.mean(v)) for g, v in porsi_twin.items()}
        asli_porsi = ((ps.get('bruto') or {}).get('porsi')) or {}
        for g, label in (('ritel', 'Porsi aktivitas ritel'), ('asing', 'Porsi aktivitas asing'),
                         ('lokal', 'Porsi aktivitas lokal non-ritel')):
            t_, a_ = porsi_twin.get(g), asli_porsi.get(g)
            tambah(label, t_, a_, 'dicocokkan', None if a_ is None or t_ is None else abs(t_ - a_) < 0.10,
                   'nilai bruto beli+jual; asli = JSON broker 40 hari terakhir')

        asli_searah = ((ps.get('bruto') or {}).get('searah')) or {}
        for g, label in (('ritel', 'Keterarahan arus ritel'), ('asing', 'Keterarahan arus asing'),
                         ('lokal', 'Keterarahan arus lokal non-ritel')):
            nilai = [s.get('searah', {}).get(k, {}).get(g) for s in stat_list]
            nilai = [v for v in nilai if v is not None]
            t_ = float(np.median(nilai)) if nilai else None
            a_ = asli_searah.get(g)
            tambah(label, t_, a_, 'dicocokkan', _rasio_ok(t_, a_, 2.0),
                   '|netto| / bruto per hari: 0 = beli-jual seimbang, 1 = semua satu arah. '
                   'Disetel lewat keberagaman tafsir per kelompok (rata-rata lintas saham, jadi '
                   'per saham bisa meleset)')

        bk = [s['buku'].get(k, {}) for s in stat_list]
        dalam = [b.get('dalam_5_lot') for b in bk if b.get('dalam_5_lot')]
        spread = [b.get('spread_fraksi') for b in bk if b.get('spread_fraksi')]
        bn = ps.get('buku_nyata') or {}
        if bn:
            a_dalam = 0.5 * (bn['dalam_5_bid_lot'] + bn['dalam_5_offer_lot'])
            t_dalam = float(np.median(dalam)) if dalam else None
            tambah('Kedalaman antrean 5 level (lot)', t_dalam, a_dalam, 'dicocokkan', _rasio_ok(t_dalam, a_dalam, 2.0),
                   'antrean pedagang cepat disetel ke snapshot ORDER_BOOK 24 Agu-15 Sep 2026')
            t_sp = float(np.median(spread)) if spread else None
            tambah('Spread (fraksi)', t_sp, bn['spread_fraksi'], 'muncul',
                   None if t_sp is None else t_sp <= 3 * bn['spread_fraksi'],
                   'selisih harga bid & offer terbaik di akhir hari')

        catatan_jendela = 'median per jendela %d hari, twin vs 2 tahun data asli dipotong sama panjang' % D
        tk, ak = f_twin.get('kurtosis_lebih'), asli.get('kurtosis_lebih')
        tambah('Ekor gemuk (kurtosis lebih)', tk, ak, 'muncul',
               None if tk is None or ak is None else (tk > 0.2 if ak > 0.2 else tk < 1.0),
               'positif = gerakan ekstrem lebih sering daripada distribusi normal; ' + catatan_jendela)
        sk = f_sisa.get('kurtosis_lebih')
        tambah('Ekor gemuk pada return sisa', sk, None, 'muncul', None if sk is None else sk > 0.2,
               'setelah bagian IHSG dibuang -- tidak bisa diwarisi dari faktor IHSG')
        ta, aa = f_twin.get('acf_abs_1_10'), asli.get('acf_abs_1_10')
        tambah('Gejolak mengumpul (ACF |r| lag 1-10)', ta, aa, 'muncul',
               None if ta is None or aa is None else (ta > 0.0 if aa > 0.02 else abs(ta) < 0.06),
               'positif = hari bergejolak cenderung diikuti hari bergejolak; ' + catatan_jendela)
        sa = f_sisa.get('acf_abs_1_10')
        tambah('Gejolak mengumpul pada return sisa', sa, None, 'muncul', None if sa is None else sa > 0.0,
               'tidak bisa diwarisi dari faktor IHSG')
        t1, a1 = f_twin.get('acf_r1'), asli.get('acf_r1')
        tambah('Autokorelasi return lag 1', t1, a1, 'muncul', None if t1 is None else abs(t1) < 0.12,
               'harus dekat nol -- kalau tidak, harga twin bisa ditebak dari kemarin')
        tc, ac = f_twin.get('corr_vol_absr'), asli.get('corr_vol_absr')
        tambah('Volume membesar saat harga bergerak', tc, ac, 'muncul',
               None if tc is None or ac is None else (tc > 0.15 and _rasio_ok(tc, ac, 2.0)),
               'korelasi log volume dengan |return|; ' + catatan_jendela)

        perilaku = (prof.get('perilaku') or {}).get(k) or {}
        kor_asli = perilaku.get('korelasi') or {}
        # Korelasi data asli yang lebih kecil dari 2 galat baku (2/akar n hari)
        # tidak bisa dibedakan dari nol -- untuk baris seperti itu twin cukup
        # tidak menunjukkan arah yang kuat.
        ambang_arah = 2.0 / np.sqrt(max(perilaku.get('n_hari') or 100, 10))
        for g, label in (('ritel', 'Ritel'), ('asing', 'Asing'), ('lokal', 'Lokal non-ritel')):
            for kunci, ket in (('hari_sama', 'arus netto vs return hari yang sama'),
                               ('tren_5h_lalu', 'arus netto vs return 5 hari sebelumnya')):
                nilai = [s['kor'].get(k, {}).get(g, {}).get(kunci) for s in stat_list]
                nilai = [v for v in nilai if v is not None]
                tv_ = float(np.mean(nilai)) if nilai else None
                av_ = (kor_asli.get(g) or {}).get(kunci)
                ok = None
                if tv_ is not None and av_ is not None:
                    if abs(av_) < ambang_arah:
                        ok = abs(tv_) < 0.25
                    else:
                        ok = bool(np.sign(tv_) == np.sign(av_) and abs(tv_) > 0.05)
                tambah('%s: %s' % (label, ket), tv_, av_, 'muncul', ok,
                       'asli = buku besar broker Jan-Okt 2026; |asli| < %.2f (2 galat baku) dianggap '
                       '"tidak berarah" -- twin cukup tidak berarah kuat' % ambang_arah)
        per_saham[k] = baris

    return {
        'per_saham': per_saham,
        'ringkas': {'lolos': lolos, 'gagal': gagal,
                    'porsi_lolos': lolos / max(lolos + gagal, 1), 'jendela': D},
    }
