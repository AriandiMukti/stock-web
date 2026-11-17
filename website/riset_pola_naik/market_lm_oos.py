"""
Market LM di data Yahoo 2013-2026, diuji di luar sampel (16 Okt 2026).

PERTANYAANNYA
market_lm.py (transformer gaya GPT, dilatih dari nol) sempat terlihat
belajar sesuatu: return +9 poin, volume +17,5, arus Top5 +20 di atas
tebakan "samain kemarin". Tapi korpusnya cuma Daily\\Summary (~100 hari per
emiten) dan ujinya emiten yang belum dilihat DI PERIODE YANG SAMA. Di sini
pertanyaannya dipersempit jadi satu: dengan data bertahun-tahun dan uji di
periode DAN emiten yang terpisah, apakah transformer dari nol menebak lebih
baik daripada fitur polos (volatilitas 20 hari, momentum, jarak dari
puncak 52 minggu) -- atau cuma menyamar jadi fitur-fitur itu?

TOKEN (Yahoo saja -- arus broker tidak ada sebelum 2026)
Satu hari = 4 token, vocab total 20, sama gayanya dengan market_lm.py:
  return harian 7 kelompok (batas market_lm.RETURN_EDGES), volume relatif
  thd rata-rata 20 hari sebelumnya 3 (VOLUME_EDGES), volatilitas 20 hari 5
  (RISIKO_EDGES, % per hari), jarak dari puncak 250 hari 5
  (<-50, -50..-30, -30..-15, -15..-5, >-5%).
Konteks 32 hari (128 token). Arsitektur MarketGPT dari market_lm.py, lebih
lebar (n_embd 128, 4 lapis).

PROTOKOL (sama dengan uji.py / analog.py)
  Latih            = separuh emiten A (paritas md5) x 2013-2019, jendela
                     yang seluruhnya sebelum 2020; 10% emiten A disisihkan
                     untuk berhenti-dini
  Uji penuh        = separuh emiten B x 2020-2026 (periode DAN emiten beda)
  Silang emiten    = B x 2013-2019;  silang periode = A x 2020-2026
  Titik uji        = emiten layak (elig uji.py), tiap 5 bar.
Yang diukur:
  H+1  : arah (IC peringkat ramalan vs return besok), besar gerak (IC vs
         |return besok|), akurasi kelompok tiap channel vs "samain kemarin".
         Ini kemampuan asli model bahasa (token berikutnya) -- bukan hasil
         yang bisa diperdagangkan (close t ke close t+1).
  H+20 : model mensimulasikan 20 hari ke depan (16 jalur per titik, token
         diambil sampel per channel). Skor arah = rata-rata return majemuk
         jalur, skor besar gerak = sebaran jalur. Dibandingkan dengan fwd20
         dari panel.py (masuk close t+1, keluar 20 bar kemudian).
Pembanding: fitur polos sendiri-sendiri, dan model LINEAR dari 9 fitur
polos (peringkat per tanggal) yang dilatih di sel yang sama dengan
transformer. IC = korelasi peringkat antar-emiten per tanggal, t dari
rata-rata bulanan. "Sisa" = IC skor model setelah dinetralkan (regresi per
tanggal) dari fitur polos -- kalau ~0, model cuma fitur polos yang menyamar.

HASIL: lihat bagian bawah berkas ini setelah dijalankan (diisi tangan).

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.market_lm_oos            # latih + uji
    python -m website.riset_pola_naik.market_lm_oos uji        # uji ulang dari checkpoint
Lingkungan: LANGKAH (default 20000), JALUR (16), MAKS_SIMULASI (semua).
"""
import hashlib
import json
import math
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from . import panel as PN

_WEBSITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WEBSITE not in sys.path:
    sys.path.insert(0, _WEBSITE)            # market_lm.py mengimpor `config` tingkat atas
from website import market_lm as ML        # noqa: E402

warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning)

CACHE = PN.RESEARCH_CACHE
CKPT = os.path.join(CACHE, 'market_lm_oos.pt')
HASIL = os.path.join(CACHE, 'market_lm_oos_hasil.json')

DD_EDGES = [-1e9, -0.50, -0.30, -0.15, -0.05, 1e9]
CHANNELS = [('return', ML.RETURN_EDGES), ('volume', ML.VOLUME_EDGES),
            ('volatilitas', ML.RISIKO_EDGES), ('dari_puncak', DD_EDGES)]
NC = len(CHANNELS)
SIZES = [len(e) - 1 for _, e in CHANNELS]
OFF = np.cumsum([0] + SIZES[:-1]).tolist()
VOCAB = sum(SIZES)
DAYS = 32
BLOCK = DAYS * NC
LANGKAH = int(os.environ.get('LANGKAH', 20000))
JALUR = int(os.environ.get('JALUR', 16))
MAKS_SIMULASI = int(os.environ.get('MAKS_SIMULASI', 0))
DEV = 'cuda' if torch.cuda.is_available() else 'cpu'
POLOS = ['ret1', 'ret5', 'ret20', 'ret120', 'dd250', 'vol20', 'vspike', 'pos30', 'rsi14']


def md5_bit(t, salt=''):
    return int(hashlib.md5((salt + t).encode()).hexdigest(), 16) % 2


# ------------------------------------------------------------------ data --

def muat():
    p = PN.bangun()
    p = p[p['date'] >= '2011-01-01'].sort_values(['ticker', 'date']).reset_index(drop=True)
    g = p.groupby('ticker', sort=False)
    p['ret1'] = g['close'].pct_change()
    p['ret_besok'] = g['ret1'].shift(-1)
    p['elig'] = ((p['hist'] >= 260) & (p['close'] >= 100) & (p['medval20'] >= 1e9)
                 & (p['traded30'] >= 0.9) & (p['bad_back60'] == 0) & (p['date'] >= '2013-01-01'))
    p['half'] = p['ticker'].map(md5_bit)
    p['period'] = np.where(p['date'] < '2020-01-01', 1, 2)

    # token per hari
    vals = {'return': p['ret1'] * 100, 'volume': p['vspike'],
            'volatilitas': p['vol20'] * 100, 'dari_puncak': p['dd250']}
    tok = np.zeros((len(p), NC), dtype=np.int64)
    ok = np.ones(len(p), dtype=bool)
    for c, (name, edges) in enumerate(CHANNELS):
        v = vals[name].to_numpy(float)
        ok &= np.isfinite(v)
        b = np.clip(np.searchsorted(edges, np.nan_to_num(v), side='right') - 1, 0, SIZES[c] - 1)
        tok[:, c] = OFF[c] + b
    ok &= (p['ret1'].abs() <= PN.LONCAT).fillna(False).to_numpy()
    p['valid'] = ok
    return p, tok


def jendela_valid(p, n_days):
    """valid_end[i] = True kalau hari i-n_days+1..i semuanya valid & satu emiten."""
    v = p['valid'].to_numpy()
    cs = np.concatenate([[0], np.cumsum(~v)])
    i = np.arange(len(p))
    lo = i - n_days + 1
    tick_start = p.groupby('ticker', sort=False).cumcount().to_numpy()
    out = (tick_start >= n_days - 1)
    lo_c = np.clip(lo, 0, None)
    out &= (cs[i + 1] - cs[lo_c]) == 0
    return out


def ret_bin_stats(p, tok, mask):
    """Rata-rata log-return dan |return| per kelompok return, dari data latih."""
    r = np.log1p(p['ret1'].to_numpy(float))
    b = tok[:, 0]
    mlog = np.zeros(SIZES[0]); mabs = np.zeros(SIZES[0])
    for k in range(SIZES[0]):
        s = mask & (b == k) & np.isfinite(r)
        mlog[k] = r[s].mean(); mabs[k] = np.abs(np.expm1(r[s])).mean()
    return mlog, mabs


# ------------------------------------------------------------------ latih --

def model_baru():
    return ML.MarketGPT(VOCAB, BLOCK, NC, n_embd=128, n_head=4, n_layer=4, dropout=0.1).to(DEV)


def latih(p, tok):
    ends = jendela_valid(p, DAYS + 1)
    tanggal = p['date'].to_numpy()
    a = (p['half'] == 0).to_numpy()
    sebelum = tanggal < np.datetime64('2020-01-01')
    val_t = p['ticker'].map(lambda t: int(hashlib.md5(('v' + t).encode()).hexdigest(), 16) % 10 == 0).to_numpy()
    akhir = np.nonzero(ends & a & sebelum)[0]
    tr_idx = akhir[~val_t[akhir]]
    va_idx = akhir[val_t[akhir]]
    print('jendela latih %d, validasi %d (emiten A, sebelum 2020)' % (len(tr_idx), len(va_idx)), flush=True)
    flat = torch.from_numpy(tok.reshape(-1)).to(DEV)

    def batch(idx_arr, n, rng):
        e = rng.choice(idx_arr, n)
        start = (e - DAYS) * NC                    # 33 hari: e-32..e
        offs = torch.arange(BLOCK + 1, device=DEV)
        w = flat[torch.from_numpy(start).to(DEV)[:, None] + offs[None, :]]
        return w[:, :-1].contiguous(), w[:, 1:].contiguous()

    model = model_baru()
    print('parameter: %d, perangkat: %s' % (sum(x.numel() for x in model.parameters()), DEV), flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=0.05)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=6e-4, total_steps=LANGKAH, pct_start=0.05)
    rng = np.random.default_rng(0)
    vrng = np.random.default_rng(1)
    vx, vy = batch(va_idx, 4096, vrng)
    best, best_state, t0 = 1e9, None, time.time()
    for step in range(1, LANGKAH + 1):
        model.train()
        x, y = batch(tr_idx, 256, rng)
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sched.step()
        if step % 1000 == 0 or step == LANGKAH:
            model.eval()
            with torch.no_grad():
                vl = sum(model(vx[i:i + 512], vy[i:i + 512])[1].item() for i in range(0, len(vx), 512)) / math.ceil(len(vx) / 512)
            tanda = ''
            if vl < best:
                best, best_state, tanda = vl, {k: v.detach().clone() for k, v in model.state_dict().items()}, ' *'
            print('langkah %5d  latih %.4f  validasi %.4f%s  (%.0f dtk)' % (step, loss.item(), vl, tanda, time.time() - t0), flush=True)
    model.load_state_dict(best_state)
    torch.save({'state': best_state, 'val_loss': best}, CKPT)
    return model


def muat_model():
    m = model_baru()
    m.load_state_dict(torch.load(CKPT, map_location=DEV)['state'])
    m.eval()
    return m


# -------------------------------------------------------------------- uji --

def titik_uji(p):
    v31 = jendela_valid(p, DAYS - 1)
    nxt = np.roll(p['valid'].to_numpy(), -1)
    same = np.roll(p['ticker'].to_numpy(), -1) == p['ticker'].to_numpy()
    m = p['elig'].to_numpy() & (p['hist'].to_numpy() % 5 == 0) & v31 & nxt & same
    s = p.loc[m].copy()
    s['cell'] = np.select([(s['half'] == 0) & (s['period'] == 1), (s['half'] == 1) & (s['period'] == 2),
                           (s['half'] == 1) & (s['period'] == 1), (s['half'] == 0) & (s['period'] == 2)],
                          ['latih (A x 13-19)', 'UJI PENUH (B x 20-26)', 'silang emiten (B x 13-19)',
                           'silang periode (A x 20-26)'], default='')
    return s


def channel_probs(logits, c):
    return F.softmax(logits[..., OFF[c]:OFF[c] + SIZES[c]], dim=-1)


@torch.no_grad()
def nilai_h1(model, tok, rows, mlog, mabs):
    """Satu forward: konteks hari t-30..t, ditambah hari t+1 asli (teacher forcing per channel)."""
    flat = torch.from_numpy(tok.reshape(-1)).to(DEV)
    offs = torch.arange(BLOCK, device=DEV)
    out = {k: [] for k in ('e_ret', 'e_abs', 'ok0', 'ok1', 'ok2', 'ok3', 'pers0', 'pers1', 'pers2', 'pers3')}
    ml, ma = torch.tensor(mlog, device=DEV, dtype=torch.float32), torch.tensor(mabs, device=DEV, dtype=torch.float32)
    for i in range(0, len(rows), 2048):
        r = rows[i:i + 2048]
        start = torch.from_numpy((r - (DAYS - 2)) * NC).to(DEV)      # hari t-30 .. t+1
        x = flat[start[:, None] + offs[None, :]]
        logits, _ = model(x)
        base = (DAYS - 1) * NC - 1                                  # token terakhir hari t
        pr = channel_probs(logits[:, base], 0)
        out['e_ret'].append((pr * ml).sum(1).cpu())
        out['e_abs'].append((pr * ma).sum(1).cpu())
        for c in range(NC):
            pc = channel_probs(logits[:, base + c], c)
            actual = x[:, base + 1 + c] - OFF[c]
            today = x[:, base - (NC - 1) + c] - OFF[c]
            out['ok%d' % c].append((pc.argmax(1) == actual).float().cpu())
            out['pers%d' % c].append((today == actual).float().cpu())
    return {k: torch.cat(v).numpy() for k, v in out.items()}


@torch.no_grad()
def simulasi_h20(model, tok, rows, mlog, horizon=20, jalur=JALUR):
    flat = torch.from_numpy(tok.reshape(-1)).to(DEV)
    ctx_days = DAYS - 1
    offs = torch.arange(ctx_days * NC, device=DEV)
    ml = torch.tensor(mlog, device=DEV, dtype=torch.float32)
    mean_out, sd_out = [], []
    per = max(1, 1536 // jalur)
    g = torch.Generator(device=DEV).manual_seed(0)
    t0 = time.time()
    for i in range(0, len(rows), per):
        r = rows[i:i + per]
        start = torch.from_numpy((r - (ctx_days - 1)) * NC).to(DEV)
        ctx = flat[start[:, None] + offs[None, :]].repeat_interleave(jalur, 0)
        cum = torch.zeros(len(ctx), device=DEV)
        for d in range(horizon):
            ctx = ctx[:, NC:] if ctx.shape[1] + NC > BLOCK else ctx
            for c in range(NC):
                logits, _ = model(ctx)
                pc = channel_probs(logits[:, -1], c)
                k = torch.multinomial(pc, 1, generator=g)
                if c == 0:
                    cum += ml[k[:, 0]]
                ctx = torch.cat([ctx, k + OFF[c]], dim=1)
        cum = cum.view(len(r), jalur)
        mean_out.append(cum.mean(1).cpu()); sd_out.append(cum.std(1).cpu())
        if (i // per) % 20 == 0:
            print('  simulasi %d/%d (%.0f dtk)' % (i + len(r), len(rows), time.time() - t0), flush=True)
    return torch.cat(mean_out).numpy(), torch.cat(sd_out).numpy()


# ---------------------------------------------------------------- statistik --

def ic(df, score, target, min_n=10):
    d = df[['date', score, target]].dropna()
    cnt = d.groupby('date')[score].transform('size')
    d = d[cnt >= min_n]
    if d.empty:
        return np.nan, np.nan, 0
    r = d.groupby('date')[[score, target]].rank()
    r['date'] = d['date']
    per = r.groupby('date').apply(lambda x: x[score].corr(x[target]))
    m = per.groupby(pd.to_datetime(per.index).to_period('M')).mean().dropna()
    return per.mean(), m.mean() / m.std() * math.sqrt(len(m)) if len(m) > 2 else np.nan, len(d)


def netralkan(df, score, kontrol):
    """Sisa skor setelah regresi per tanggal pada peringkat fitur kontrol."""
    out = pd.Series(np.nan, index=df.index)
    for _, d in df.groupby('date'):
        d = d[[score] + kontrol].dropna()
        if len(d) < 15:
            continue
        X = d[kontrol].rank(pct=True).to_numpy()
        X = np.column_stack([np.ones(len(X)), X])
        y = d[score].rank(pct=True).to_numpy()
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        out.loc[d.index] = y - X @ beta
    return out


def linear_polos(s, target):
    """Model linear dari peringkat 9 fitur polos, dilatih di sel latih; prediksi semua sel."""
    R = s.groupby('date')[POLOS].rank(pct=True).fillna(0.5)
    y = s.groupby('date')[target].rank(pct=True)
    tr = (s['cell'] == 'latih (A x 13-19)') & y.notna()
    X = np.column_stack([np.ones(int(tr.sum())), R[tr].to_numpy()])
    lam = 1e-3 * np.eye(X.shape[1]); lam[0, 0] = 0
    beta = np.linalg.solve(X.T @ X + lam * len(X), X.T @ y[tr].to_numpy())
    return pd.Series(np.column_stack([np.ones(len(R)), R.to_numpy()]) @ beta, index=s.index)


def kuintil(df, score, target):
    d = df[['date', score, target]].dropna()
    q = d.groupby('date')[score].rank(pct=True)
    top = d[q > 0.8].groupby('date')[target].mean()
    bot = d[q <= 0.2].groupby('date')[target].mean()
    return float((top - bot).mean())


def uji(p, tok, model):
    lat = (p['half'] == 0).to_numpy() & (p['date'] < '2020-01-01').to_numpy() & p['valid'].to_numpy()
    mlog, mabs = ret_bin_stats(p, tok, lat)
    s = titik_uji(p)
    rows = s.index.to_numpy()
    print('titik uji: %s' % s['cell'].value_counts().to_dict(), flush=True)

    h1 = nilai_h1(model, tok, rows, mlog, mabs)
    for k, v in h1.items():
        s[k] = v
    s['abs_besok'] = s['ret_besok'].abs()
    s['lr20'] = np.log1p(s['fwd20'])
    s['abs20'] = s['fwd20'].abs()
    s['neg_vol20'] = -s['vol20']
    s['neg_ret1'] = -s['ret1']

    sim_rows = s.index[s['cell'].isin(['UJI PENUH (B x 20-26)', 'latih (A x 13-19)'])].to_numpy()
    if MAKS_SIMULASI:
        sim_rows = np.random.default_rng(0).choice(sim_rows, min(MAKS_SIMULASI, len(sim_rows)), replace=False)
    print('simulasi H+20: %d titik x %d jalur' % (len(sim_rows), JALUR), flush=True)
    mu, sd = simulasi_h20(model, tok, sim_rows, mlog)
    s['sim_mean'] = np.nan; s['sim_sd'] = np.nan
    s.loc[sim_rows, 'sim_mean'] = mu; s.loc[sim_rows, 'sim_sd'] = sd

    s['lin_h1'] = linear_polos(s, 'ret_besok')
    s['lin_abs1'] = linear_polos(s, 'abs_besok')
    s['lin_h20'] = linear_polos(s, 'lr20')
    s['lin_abs20'] = linear_polos(s, 'abs20')
    kontrol = ['ret1', 'ret20', 'ret120', 'dd250', 'vol20']
    s['sisa_e_ret'] = netralkan(s, 'e_ret', kontrol)
    s['sisa_e_abs'] = netralkan(s, 'e_abs', kontrol)
    s['sisa_sim'] = netralkan(s, 'sim_mean', kontrol)
    s['sisa_sd'] = netralkan(s, 'sim_sd', kontrol)

    uji_list = [
        ('H+1 arah', 'ret_besok', ['e_ret', 'sisa_e_ret', 'lin_h1', 'neg_ret1', 'ret20', 'ret120', 'dd250', 'neg_vol20']),
        ('H+1 besar gerak', 'abs_besok', ['e_abs', 'sisa_e_abs', 'lin_abs1', 'vol20']),
        ('H+20 arah', 'lr20', ['sim_mean', 'sisa_sim', 'e_ret', 'lin_h20', 'ret20', 'ret120', 'dd250', 'neg_vol20']),
        ('H+20 besar gerak', 'abs20', ['sim_sd', 'sisa_sd', 'lin_abs20', 'vol20']),
    ]
    hasil = {}
    for cell in ['UJI PENUH (B x 20-26)', 'silang emiten (B x 13-19)', 'silang periode (A x 20-26)', 'latih (A x 13-19)']:
        d = s[s['cell'] == cell]
        hasil[cell] = {'n': int(len(d)), 'akurasi': {}, 'ic': {}}
        print('\n=== %s  (n=%d, %d tanggal) ===' % (cell, len(d), d['date'].nunique()))
        print('Akurasi kelompok H+1 (model vs "samain hari ini"):')
        for c, (name, _) in enumerate(CHANNELS):
            a, b = float(d['ok%d' % c].mean()), float(d['pers%d' % c].mean())
            hasil[cell]['akurasi'][name] = [a, b]
            print('  %-12s model %5.1f%%   samain %5.1f%%   selisih %+5.1f poin' % (name, a * 100, b * 100, (a - b) * 100))
        for judul, target, skor in uji_list:
            print('%s (IC, t, n; kuintil atas-bawah):' % judul)
            hasil[cell]['ic'][judul] = {}
            for sc in skor:
                v, t, n = ic(d, sc, target)
                if n == 0:
                    continue
                kq = kuintil(d, sc, target) * 100
                hasil[cell]['ic'][judul][sc] = [float(v), float(t) if t == t else None, int(n), kq]
                print('  %-12s IC %+.3f  t %+5.1f  n %6d   Q5-Q1 %+6.2f%%' % (sc, v, t, n, kq))
    with open(HASIL, 'w') as f:
        json.dump(hasil, f, indent=1)
    print('\nhasil: %s' % HASIL)
    return hasil


def main():
    t0 = time.time()
    p, tok = muat()
    print('panel %d baris, valid %d, %.0f dtk' % (len(p), int(p['valid'].sum()), time.time() - t0), flush=True)
    if len(sys.argv) > 1 and sys.argv[1] == 'uji':
        model = muat_model()
    else:
        model = latih(p, tok)
    model.eval()
    uji(p, tok, model)
    print('selesai %.0f dtk' % (time.time() - t0))


if __name__ == '__main__':
    main()
