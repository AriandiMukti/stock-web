"""
RL di dalam "mimpi" world model: apakah data sintetis dari transformer pasar
(market_lm_oos.pt) mengurangi overfitting RL?

LATAR
rl_trading.py (PPO pilih-saham) GAGAL di luar sampel 18 Okt 2026 dan makin
jelek kalau fiturnya ditambah -- dugaan: ~72 episode/fold terlalu sedikit,
PPO menghafal. Di sini masalahnya dipersempit ke satu saham, posisi 0/1, dan
yang diuji cuma satu hal: kalau episode latihan diperbanyak dengan jalur
"mimpi" yang digulirkan world model, apakah kebijakannya lebih baik di data
asli yang belum pernah dilihat?

Catatan jujur sebelum jalan: agen ini price-taker (aksinya tak menggeser
harga), jadi kebijakan terbaik di mimpi kira-kira "pegang kalau ramalan model
> ambang biaya". Arah Market LM di luar sampel lemah (IC H+20 0,059 vs linear
polos 0,095; sisa H+1 negatif). Prior: kemungkinan besar GAGAL. Yang tetap
berguna: ukuran "celah mimpi" -- seberapa jauh agen mengakali kesalahan model.

DESAIN (didaftar SEBELUM hasil dilihat, 29 Okt 2026)
Tiap saham diproses TERPISAH, hasilnya independen: data, jalur mimpi,
kebijakan, dan hasil uji satu saham tidak pernah menyentuh saham lain.
World model dipakai bersama tapi beku (cuma mesin simulasi).
  Split per saham = periode: latih 2013-2019, uji 2020-2026 (hari return).
  Emiten B (paritas md5, tak pernah dilihat world model) = hasil utama;
  emiten A dilaporkan terpisah sebagai cek silang.
  Lingkungan: tiap hari agen lihat token 32 hari (4 channel market_lm_oos,
  multi-hot 20) + posisi; aksi pegang/kas di close t, eksekusi close t+1
  -> return yang didapat = close t+1 ke close t+2. Biaya 0,9% pulang-pergi
  (0,45%/sisi, = keluar.BIAYA), cek kepekaan 0,7%. Episode 60 langkah.
  Saat konteks tak sah / emiten tak elig -> paksa kas (sama untuk semua).
  Mimpi: konteks awal = jendela asli saham itu <2020; world model
  menggulirkan 61 hari (sampling per channel, KV-cache, konteks 24-31 hari).
  Return harian mimpi diambil acak dari return asli saham itu <2020 di
  kelompok token yang sama (kalau < 20 isinya: kelompok A x <2020).
  Tiga lengan, PPO identik, cuma sumber episode yang beda:
      asli    jendela 93 hari asli saham itu <2020
      mimpi   jalur mimpi saham itu saja
      campur  50:50
  5 seed (7, 108, 209, 310, 411), hiperparameter PPO = rl_trading.latih.
  Pembanding per saham: pegang terus (aturan paksa-kas sama), acak dengan
  peluang ganti posisi sama (20 jalan, median), aturan linear 9 fitur polos
  (ridge ke return 20 langkah, ambang dipilih di <2020 saham itu).

KRITERIA LOLOS (lengan mimpi / campur, di emiten B x 2020-26; majemuk)
  Per saham: nilai lengan = median antar seed dari return majemuk total.
  (a) median selisih vs `asli` > 0 DAN menang di > 50% saham, uji tanda
      satu sisi p < 0,05
  (b) median selisih vs aturan linear > 0 DAN vs acak > 0
  (c) median selisih vs `asli` per seed (pasangan seed sama) > 0 di >= 4/5 seed
  (d) median selisih vs `asli` per tahun > 0 di >= 5 dari 7 tahun
  Emiten A harus searah dengan (a). Selain itu: GAGAL.

PEMAKAIAN (dari <project>/)
    python -m website.riset_pola_naik.rl_mimpi mimpi     # data + jalur mimpi per saham (GPU)
    python -m website.riset_pola_naik.rl_mimpi latih     # PPO per saham, lanjut dari yg belum ada
    python -m website.riset_pola_naik.rl_mimpi laporan   # agregasi -> research_cache/rl_mimpi/laporan.txt
    python -m website.riset_pola_naik.rl_mimpi asap      # uji kecil + cek KV-cache & independensi
Lingkungan: PROSES (1, paralel per saham), SAHAM (BBCA,TLKM), MAKS_SAHAM (0 =
semua, peringkat nilai transaksi <2020 saja), JALUR (2000), ITER (60), EPS (128).

HASIL (29 Okt 2026, SEMENTARA -- dihentikan pengguna di 18/99 saham, vonis
penuh belum ada; lanjutkan dengan `latih` lalu `laporan`, yang selesai dilewati)
  - Mimpi tidak realistis untuk big cap: world model menarik jalur ke "saham
    IDX rata-rata" (hari naik lebih jarang, volatilitas & jarak dari puncak
    lebih besar). Drift mimpi BBCA -0,02%/hari vs asli +0,08%.
  - PPO kolaps ke kebijakan KONSTAN di semua lengan: selalu kas (0%) atau
    hampir selalu pegang (= beli-tahan); kutubnya ditentukan seed, bukan
    kondisi pasar. Tidak ada timing yang dipelajari.
  - Lengan mimpi paling sering memilih kas (drift negatif) -- kelihatan
    "menang" cuma karena 2020-26 banyak saham jeblok (median pegang emiten
    B -56% di 7 saham pertama).
  - Vonis sementara (12 saham): mimpi & campur GAGAL, (a)-(d) tak satu pun.
"""
import hashlib
import json
import math
import os
import sys
import time
import traceback

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from . import panel as PN

KELUAR = os.path.join(PN.RESEARCH_CACHE, 'rl_mimpi')
CTX = 32                        # hari konteks yang dilihat kebijakan (= market_lm_oos.DAYS)
LANGKAH = 60                    # langkah per episode
JEDA = 2                        # keputusan close t -> return close t+1..t+2
L = CTX + LANGKAH + 1           # hari per episode (termasuk konteks bootstrap)
W_KV = 24                       # hari konteks saat re-encode world model
SEEDS = (7, 108, 209, 310, 411)
BIAYA_SISI = 0.0045             # 0,9% pulang-pergi
BIAYA_SISI_ALT = 0.0035         # 0,7% pulang-pergi (cek kepekaan)
BATAS = np.datetime64('2020-01-01')
POLOS = ['ret1', 'ret5', 'ret20', 'ret120', 'dd250', 'vol20', 'vspike', 'pos30', 'rsi14']


def _env(nama, default):
    return int(os.environ.get(nama, default))


def _hash(s):
    return int(hashlib.md5(s.encode()).hexdigest(), 16) % (2 ** 31)


class Kanal:
    def __init__(self, berkas):
        self.t0 = time.time()
        self.f = open(berkas, 'a', encoding='utf-8')

    def log(self, pesan):
        baris = '%7.0fs %s' % (time.time() - self.t0, pesan)
        print(baris, flush=True)
        self.f.write(baris + '\n')
        self.f.flush()


# ------------------------------------------------------ world model + KV --

@torch.no_grad()
def _kv_encode(model, idx, K, V):
    """Forward penuh atas idx [N,T] (mulai batas hari), isi cache K/V[l][:, :, :T]."""
    N, T = idx.shape
    pos = torch.arange(T, device=idx.device)
    x = model.tok_emb(idx) + model.pos_emb(pos) + model.channel_emb(pos % model.n_channels)
    for l, b in enumerate(model.blocks):
        a = b.attn
        C = x.shape[-1]
        q, k, v = a.qkv(b.ln1(x)).split(C, dim=2)
        q, k, v = (z.view(N, T, a.n_head, C // a.n_head).transpose(1, 2) for z in (q, k, v))
        K[l][:, :, :T] = k
        V[l][:, :, :T] = v
        att = (q @ k.transpose(-2, -1)) / math.sqrt(k.size(-1))
        att = att.masked_fill(a.mask[:, :, :T, :T] == 0, float('-inf'))
        out = (F.softmax(att, dim=-1) @ v).transpose(1, 2).contiguous().view(N, T, C)
        x = x + a.proj(out)
        x = x + b.mlp(b.ln2(x))
    return model.head(model.ln_f(x[:, -1]))


@torch.no_grad()
def _kv_step(model, tok, p, K, V):
    """Satu token di posisi p (cache 0..p-1 sudah terisi) -> logit token p+1."""
    N = tok.shape[0]
    x = (model.tok_emb(tok) + model.pos_emb.weight[p] + model.channel_emb.weight[p % model.n_channels])[:, None]
    for l, b in enumerate(model.blocks):
        a = b.attn
        C = x.shape[-1]
        q, k, v = a.qkv(b.ln1(x)).split(C, dim=2)
        q, k, v = (z.view(N, 1, a.n_head, C // a.n_head).transpose(1, 2) for z in (q, k, v))
        K[l][:, :, p] = k[:, :, 0]
        V[l][:, :, p] = v[:, :, 0]
        att = (q @ K[l][:, :, :p + 1].transpose(-2, -1)) / math.sqrt(k.size(-1))
        out = (F.softmax(att, dim=-1) @ V[l][:, :, :p + 1]).transpose(1, 2).contiguous().view(N, 1, C)
        x = x + a.proj(out)
        x = x + b.mlp(b.ln2(x))
    return model.head(model.ln_f(x[:, 0]))


def _cache(model, N, dev):
    blk = model.blocks[0].attn
    C = model.tok_emb.weight.shape[1]
    shape = (N, blk.n_head, model.block_size, C // blk.n_head)
    K = [torch.zeros(shape, device=dev) for _ in model.blocks]
    V = [torch.zeros(shape, device=dev) for _ in model.blocks]
    return K, V


@torch.no_grad()
def bangkitkan(model, ctx_tok, hari, seed, off, sizes, dev, per=1000):
    """ctx_tok [N, CTX, NC] token global -> token [N, CTX+hari, NC] (konteks + mimpi)."""
    nc = len(sizes)
    blok = model.block_size
    g = torch.Generator(device=dev).manual_seed(seed)
    hasil = []
    for i in range(0, len(ctx_tok), per):
        c = torch.from_numpy(ctx_tok[i:i + per].astype(np.int64)).to(dev)
        N = len(c)
        total = (CTX + hari) * nc
        buf = torch.zeros((N, total), dtype=torch.long, device=dev)
        buf[:, :CTX * nc] = c.reshape(N, -1)
        K, V = _cache(model, N, dev)
        n = CTX * nc
        while n < total:
            awal = n - W_KV * nc
            logits = _kv_encode(model, buf[:, awal:n], K, V)
            p = n - awal
            while True:
                ch = n % nc
                pr = F.softmax(logits[:, off[ch]:off[ch] + sizes[ch]], dim=-1)
                k = torch.multinomial(pr, 1, generator=g)[:, 0] + off[ch]
                buf[:, n] = k
                n += 1
                if n >= total or p >= blok - 1:
                    break
                logits = _kv_step(model, k, p, K, V)
                p += 1
        hasil.append(buf.view(N, CTX + hari, nc).cpu().numpy())
    return np.concatenate(hasil).astype(np.int8)


@torch.no_grad()
def cek_kv(model, tok_flat, dev, log):
    """KV-cache harus sama dengan forward penuh market_lm."""
    nc = model.n_channels
    rng = np.random.default_rng(0)
    awal = rng.integers(0, len(tok_flat) // nc - 40, 64) * nc
    idx = torch.from_numpy(np.stack([tok_flat[a:a + model.block_size] for a in awal]).astype(np.int64)).to(dev)
    K, V = _cache(model, len(idx), dev)
    t0 = W_KV * nc
    lg = _kv_encode(model, idx[:, :t0], K, V)
    beda = 0.0
    for p in range(t0, model.block_size):
        penuh = model(idx[:, :p])[0][:, -1]
        beda = max(beda, (penuh - lg).abs().max().item())
        lg = _kv_step(model, idx[:, p], p, K, V)
    log('cek KV-cache vs forward penuh: beda logit maks %.2e %s' % (beda, 'OK' if beda < 1e-3 else 'SALAH'))
    return beda < 1e-3


# ------------------------------------------------------------- tahap 1 --

def siapkan(keluar, kanal, maks=0, saham=None, jalur=2000, kv=False):
    """Data per saham + jalur mimpi -> keluar/data/<T>.npz (yang sudah ada dilewati)."""
    from . import market_lm_oos as MO
    os.makedirs(os.path.join(keluar, 'data'), exist_ok=True)
    p, tok = MO.muat()
    kanal.log('panel %d baris' % len(p))
    model = MO.muat_model()
    if kv and not cek_kv(model, tok.reshape(-1), MO.DEV, kanal.log):
        raise SystemExit('KV-cache tidak cocok dengan forward penuh')

    tgl = p['date'].to_numpy().astype('datetime64[D]')
    v = p['valid'].to_numpy()
    elig = p['elig'].to_numpy()
    ret = p['ret1'].to_numpy(np.float64)
    ctxok = MO.jendela_valid(p, CTX)
    sebelum = tgl < BATAS
    b0 = tok[:, 0] - MO.OFF[0]
    lat_a = (p['half'] == 0).to_numpy() & sebelum & v
    kolam_global = [ret[lat_a & (b0 == k)] for k in range(MO.SIZES[0])]
    polos = p[POLOS].to_numpy(np.float32)
    medval = p['medval20'].to_numpy(np.float64)

    batas = p.groupby('ticker', sort=False).indices
    kandidat = []
    for t, rows in batas.items():
        a, z = rows[0], rows[-1] + 1
        n = z - a
        if n < L + 10:
            continue
        boleh = np.zeros(n, bool)
        boleh[:n - JEDA] = ctxok[a:z - JEDA] & elig[a:z - JEDA] & v[a + JEDA:z]
        hari_ret = np.full(n, np.datetime64('NaT'), dtype='datetime64[D]')
        hari_ret[:n - JEDA] = tgl[a + JEDA:z]
        n_lat = int((boleh & (hari_ret < BATAS)).sum())
        n_uji = int((boleh & (hari_ret >= BATAS)).sum())
        if n_lat < 500 or n_uji < 250:
            continue
        kandidat.append((t, a, z, float(np.nanmedian(np.where(sebelum[a:z], medval[a:z], np.nan)))))
    kandidat.sort(key=lambda x: -x[3])
    if saham:
        kandidat = [k for k in kandidat if k[0] in saham]
    if maks:
        kandidat = kandidat[:maks]
    kanal.log('saham layak: %d' % len(kandidat))

    for i, (t, a, z, _) in enumerate(kandidat):
        tujuan = os.path.join(keluar, 'data', t + '.npz')
        if os.path.exists(tujuan):
            continue
        t0 = time.time()
        n = z - a
        sv, st = v[a:z], tgl[a:z]
        boleh = np.zeros(n, bool)
        boleh[:n - JEDA] = ctxok[a:z - JEDA] & elig[a:z - JEDA] & v[a + JEDA:z]
        # jendela episode asli: L hari sah berturut-turut, semuanya < 2020
        cs = np.concatenate([[0], np.cumsum(~sv)])
        s = np.arange(n - L + 1)
        utuh = (cs[s + L] - cs[s]) == 0
        lat_awal = s[utuh & (st[s + L - 1] < BATAS)].astype(np.int32)
        uji_awal = s[utuh & (st[s] >= BATAS)].astype(np.int32)
        # konteks awal mimpi: CTX hari sah, berakhir < 2020
        s2 = np.arange(n - CTX + 1)
        ctx_awal = s2[((cs[s2 + CTX] - cs[s2]) == 0) & (st[s2 + CTX - 1] < BATAS)]
        if len(lat_awal) < 100 or len(ctx_awal) < 100:
            kanal.log('%s dilewati: jendela latih %d' % (t, len(lat_awal)))
            continue
        rng = np.random.default_rng(_hash(t))
        pilih = rng.choice(ctx_awal, jalur)
        ctx = np.stack([tok[a + c:a + c + CTX] for c in pilih])
        mt = bangkitkan(model, ctx, L - CTX, _hash('m' + t), MO.OFF, MO.SIZES, MO.DEV)
        # return mimpi: hari konteks = asli, hari bangkitan = ambil dari kolam kelompok token
        mr = np.stack([ret[a + c:a + c + CTX] for c in pilih])
        mr = np.concatenate([mr, np.zeros((jalur, L - CTX))], axis=1)
        sr, sb = ret[a:z], b0[a:z]
        sendiri = sv & (st < BATAS)
        gb = mt[:, CTX:, 0].astype(np.int64) - MO.OFF[0]
        for k in range(MO.SIZES[0]):
            kol = sr[sendiri & (sb == k)]
            if len(kol) < 20:
                kol = kolam_global[k]
            m = gb == k
            mr[:, CTX:][m] = rng.choice(kol, int(m.sum()))
        np.savez_compressed(
            tujuan, ticker=t, half=int(p['half'].iat[a]), tanggal=st, tok=tok[a:z].astype(np.int8),
            ret=np.nan_to_num(ret[a:z]).astype(np.float32), sah=sv, boleh=boleh,
            polos=polos[a:z], lat_awal=lat_awal, uji_awal=uji_awal,
            mimpi_tok=mt, mimpi_ret=mr.astype(np.float32),
            off=np.array(MO.OFF), sizes=np.array(MO.SIZES))
        kanal.log('[%d/%d] %s  jendela latih %d, mimpi %d jalur  %.1f dtk'
                  % (i + 1, len(kandidat), t, len(lat_awal), jalur, time.time() - t0))


# ------------------------------------------------------------- tahap 2 --

class Kebijakan(nn.Module):
    def __init__(self, d, h=64):
        super().__init__()
        self.badan = nn.Sequential(nn.Linear(d, h), nn.Tanh(), nn.Linear(h, h), nn.Tanh())
        self.pi = nn.Linear(h, 2)
        self.v = nn.Linear(h, 1)

    def forward(self, x):
        z = self.badan(x)
        return self.pi(z), self.v(z).squeeze(-1)


def _multihot(tok, vocab):
    """tok [..., NC] int -> [..., vocab] float32 (channel memakai rentang token yang terpisah)."""
    out = np.zeros(tok.shape[:-1] + (vocab,), np.float32)
    np.put_along_axis(out, tok.astype(np.int64), 1.0, axis=-1)
    return out


def _obs_episode(mh, k):
    """mh [B, L, vocab] tensor -> observasi langkah k: hari k..k+CTX-1 diratakan."""
    return mh[:, k:k + CTX].reshape(mh.shape[0], -1)


def latih_ppo(kolam, p_asli, seed, iters, eps):
    """kolam: {'asli': (mh, lr), 'mimpi': (mh, lr)} tensor [N, L, vocab] / [N, L]."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    d = CTX * next(iter(kolam.values()))[0].shape[-1] + 1
    net = Kebijakan(d)
    opt = torch.optim.Adam(net.parameters(), lr=3e-4)
    gamma, lam, clip, ent = 0.99, 0.95, 0.2, 0.01
    for _ in range(iters):
        dari_asli = rng.random(eps) < p_asli
        bag = []
        for nama, m in (('asli', dari_asli), ('mimpi', ~dari_asli)):
            if m.any():
                mh, lr = kolam[nama]
                j = torch.from_numpy(rng.integers(0, len(mh), int(m.sum())))
                bag.append((mh[j], lr[j]))
        mh = torch.cat([b[0] for b in bag])
        lr = torch.cat([b[1] for b in bag])
        B = len(mh)
        pos = torch.zeros(B)
        obs, act, logp, val, rew = [], [], [], [], []
        with torch.no_grad():
            for k in range(LANGKAH):
                x = torch.cat([_obs_episode(mh, k), pos[:, None]], 1)
                lg, v = net(x)
                dist = torch.distributions.Categorical(logits=lg)
                a = dist.sample()
                af = a.float()
                r = 100.0 * (af * lr[:, k + CTX - 1 + JEDA] - BIAYA_SISI * (af - pos).abs())
                obs.append(x); act.append(a); logp.append(dist.log_prob(a)); val.append(v); rew.append(r)
                pos = af
            _, v_akhir = net(torch.cat([_obs_episode(mh, LANGKAH), pos[:, None]], 1))
        val.append(v_akhir)
        rew = torch.stack(rew); val = torch.stack(val)
        adv = torch.zeros_like(rew)
        g = torch.zeros(B)
        for k in reversed(range(LANGKAH)):
            delta = rew[k] + gamma * val[k + 1] - val[k]
            g = delta + gamma * lam * g
            adv[k] = g
        ret_t = (adv + val[:-1]).reshape(-1)
        adv = adv.reshape(-1)
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        obs = torch.cat(obs); act = torch.cat(act); logp = torch.cat(logp)
        n = len(obs)
        for _ in range(3):
            urut = torch.from_numpy(rng.permutation(n))
            for i in range(0, n, 1024):
                j = urut[i:i + 1024]
                lg, v = net(obs[j])
                dist = torch.distributions.Categorical(logits=lg)
                rasio = torch.exp(dist.log_prob(act[j]) - logp[j])
                l_pi = -torch.min(rasio * adv[j], rasio.clamp(1 - clip, 1 + clip) * adv[j]).mean()
                loss = l_pi + 0.5 * F.mse_loss(v, ret_t[j]) - ent * dist.entropy().mean()
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                opt.step()
    net.eval()
    return net


@torch.no_grad()
def _greedy_dua(net, X):
    """Aksi rakus untuk posisi 0 dan posisi 1 di tiap baris X [n, d-1]."""
    n = X.shape[0]
    a0 = net(torch.cat([X, torch.zeros(n, 1)], 1))[0].argmax(1).numpy()
    a1 = net(torch.cat([X, torch.ones(n, 1)], 1))[0].argmax(1).numpy()
    return a0, a1


def jalankan_urut(a0, a1, boleh):
    """Aksi berurutan (posisi bergantung aksi kemarin); tak boleh -> kas."""
    act = np.zeros(len(boleh), np.int8)
    pos = 0
    for i in range(len(boleh)):
        pos = int(a1[i] if pos else a0[i]) if boleh[i] else 0
        act[i] = pos
    return act


def bersih(act, lr, biaya):
    """Return log bersih per langkah."""
    ganti = np.abs(np.diff(np.concatenate([[0], act.astype(np.float64)])))
    return act * lr - biaya * ganti


def majemuk(x):
    return float(np.expm1(np.sum(x)))


def per_tahun(x, tahun):
    return {str(y): majemuk(x[tahun == y]) for y in np.unique(tahun)}


def acak_setara(act, lr, boleh, seed, n=20):
    """Rantai Markov dengan peluang masuk/keluar sama dengan kebijakan -> median majemuk."""
    prev = np.concatenate([[0], act[:-1]])
    b = boleh.astype(bool)
    n0 = max(int(((prev == 0) & b).sum()), 1)
    n1 = max(int(((prev == 1) & b).sum()), 1)
    p_on = ((prev == 0) & (act == 1) & b).sum() / n0
    p_off = ((prev == 1) & (act == 0) & b).sum() / n1
    rng = np.random.default_rng(seed)
    hasil = []
    for _ in range(n):
        u = rng.random(len(act))
        a = np.zeros(len(act), np.int8)
        pos = 0
        for i in range(len(act)):
            if not b[i]:
                pos = 0
            elif pos == 0:
                pos = int(u[i] < p_on)
            else:
                pos = int(u[i] >= p_off)
            a[i] = pos
        hasil.append(majemuk(bersih(a, lr, BIAYA_SISI)))
    return float(np.median(hasil))


def aturan_linear(polos, lr, boleh, lat, uji):
    """Ridge 9 fitur polos -> return 20 langkah; pegang kalau ramalan > ambang terbaik <2020."""
    n = len(lr)
    cs = np.concatenate([[0], np.cumsum(lr)])
    y = np.full(n, np.nan)
    y[:n - 20] = cs[20:n] - cs[:n - 20]
    ok_lat = lat & boleh & np.isfinite(y)
    ok_lat[np.nonzero(lat)[0][-20:]] = False          # target tak boleh menyeberang ke 2020
    X = polos.astype(np.float64)
    mu = np.nanmean(X[ok_lat], 0); sd = np.nanstd(X[ok_lat], 0) + 1e-9
    X = np.nan_to_num((X - mu) / sd)
    X = np.column_stack([np.ones(n), X])
    A = X[ok_lat]
    reg = 1e-3 * len(A) * np.eye(A.shape[1]); reg[0, 0] = 0
    beta = np.linalg.solve(A.T @ A + reg, A.T @ y[ok_lat])
    pred = X @ beta
    terbaik, ambang = -np.inf, 0.0
    for q in np.linspace(0.1, 0.9, 9):
        thr = float(np.quantile(pred[ok_lat], q))
        a = jalankan_urut(pred[lat] > thr, pred[lat] > thr, boleh[lat])
        s = bersih(a, lr[lat], BIAYA_SISI).sum()
        if s > terbaik:
            terbaik, ambang = s, thr
    return jalankan_urut(pred[uji] > ambang, pred[uji] > ambang, boleh[uji])


@torch.no_grad()
def nilai_episode(net, mh, lr, maks=500):
    """Rata-rata return log bersih per episode 60 langkah (kebijakan rakus), % ."""
    if len(mh) == 0:
        return None
    if len(mh) > maks:                                # merata sepanjang periode, bukan 500 pertama
        j = torch.from_numpy(np.linspace(0, len(mh) - 1, maks).round().astype(np.int64))
        mh, lr = mh[j], lr[j]
    B = len(mh)
    X = torch.stack([_obs_episode(mh, k) for k in range(LANGKAH)], 1).reshape(B * LANGKAH, -1)
    a0, a1 = (a.reshape(B, LANGKAH) for a in _greedy_dua(net, X))
    pos = np.zeros(B)
    tot = np.zeros(B)
    r = lr.numpy()
    for k in range(LANGKAH):
        a = np.where(pos == 1, a1[:, k], a0[:, k])
        tot += a * r[:, k + CTX - 1 + JEDA] - BIAYA_SISI * np.abs(a - pos)
        pos = a
    return float(np.mean(tot) * 100)


def proses_saham(tugas):
    """Satu saham, mandiri: baca npz -> latih 3 lengan x seed -> uji -> json."""
    npz, tujuan, cfg = tugas
    torch.set_num_threads(1)
    t0 = time.time()
    nama = os.path.basename(npz)[:-4]
    try:
        D = np.load(npz)
        vocab = int(D['sizes'].sum())
        tok, ret, boleh, sah = D['tok'], D['ret'].astype(np.float64), D['boleh'], D['sah']
        tgl = D['tanggal'].astype('datetime64[D]')
        n = len(tok)
        # langkah t = hari keputusan, return = hari t+JEDA
        t_idx = np.arange(CTX - 1, n - JEDA)
        hari_ret = tgl[t_idx + JEDA]
        lr = np.log1p(np.where(sah[t_idx + JEDA], ret[t_idx + JEDA], 0.0))
        bl = boleh[t_idx]
        lat, uji = hari_ret < BATAS, hari_ret >= BATAS
        tahun_uji = hari_ret[uji].astype('datetime64[Y]').astype(int) + 1970
        mh_all = _multihot(tok, vocab)
        X = torch.from_numpy(np.lib.stride_tricks.sliding_window_view(mh_all, (CTX, vocab))[:, 0]
                             .reshape(-1, CTX * vocab)[:len(t_idx)].copy())

        def kolam_dari(awal):
            idx = awal[:, None] + np.arange(L)[None]
            return (torch.from_numpy(mh_all[idx]),
                    torch.from_numpy(np.log1p(ret[idx]).astype(np.float32)))
        kolam = {'asli': kolam_dari(D['lat_awal']),
                 'mimpi': (torch.from_numpy(_multihot(D['mimpi_tok'], vocab)),
                           torch.from_numpy(np.log1p(D['mimpi_ret'].astype(np.float64)).astype(np.float32)))}
        kolam_uji = kolam_dari(D['uji_awal'])

        def ringkas(act_uji):
            x = bersih(act_uji, lr[uji], BIAYA_SISI)
            return {'total': majemuk(x), 'total_07': majemuk(bersih(act_uji, lr[uji], BIAYA_SISI_ALT)),
                    'tahun': per_tahun(x, tahun_uji), 'porsi_pegang': float(act_uji.mean()),
                    'ganti': int(np.abs(np.diff(np.concatenate([[0], act_uji]))).sum())}

        hasil = {'ticker': nama, 'half': int(D['half']), 'n_latih_jendela': int(len(D['lat_awal'])),
                 'n_uji_langkah': int(uji.sum()), 'n_uji_boleh': int(bl[uji].sum())}
        hasil['pegang'] = ringkas(bl[uji].astype(np.int8))
        hasil['linear'] = ringkas(aturan_linear(D['polos'][t_idx], lr, bl, lat, uji))
        gen = D['mimpi_ret'][:, CTX:].astype(np.float64)
        asli_lat = ret[(sah & (tgl < BATAS))]
        hasil['mimpi_cek'] = {'mu_mimpi': float(np.mean(np.log1p(gen)) * 100), 'sd_mimpi': float(np.std(np.log1p(gen)) * 100),
                              'mu_asli': float(np.mean(np.log1p(asli_lat)) * 100), 'sd_asli': float(np.std(np.log1p(asli_lat)) * 100)}
        hasil['lengan'] = {}
        for lengan, p_asli in (('asli', 1.0), ('mimpi', 0.0), ('campur', 0.5)):
            per_seed = {}
            for sd in cfg['seeds']:
                net = latih_ppo(kolam, p_asli, sd, cfg['iters'], cfg['eps'])
                a0, a1 = _greedy_dua(net, X)
                act = jalankan_urut(a0, a1, bl)
                r = ringkas(act[uji])
                r['acak'] = acak_setara(act[uji], lr[uji], bl[uji], _hash('%s%s%d' % (nama, lengan, sd)))
                r['ep_mimpi'] = nilai_episode(net, *kolam['mimpi'])
                r['ep_latih'] = nilai_episode(net, *kolam['asli'])
                r['ep_uji'] = nilai_episode(net, *kolam_uji)
                r['latih_total'] = majemuk(bersih(act[lat], lr[lat], BIAYA_SISI))
                per_seed[str(sd)] = r
            hasil['lengan'][lengan] = per_seed
        hasil['detik'] = time.time() - t0
        tmp = tujuan + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(hasil, f, indent=1)
        os.replace(tmp, tujuan)
        return nama, 'ok', time.time() - t0
    except Exception:
        return nama, 'GAGAL\n' + traceback.format_exc(), time.time() - t0


def latih_semua(keluar, kanal, cfg, saham=None, proses=1):
    os.makedirs(os.path.join(keluar, 'per_saham'), exist_ok=True)
    tugas = []
    for f in sorted(os.listdir(os.path.join(keluar, 'data'))):
        t = f[:-4]
        if not f.endswith('.npz') or (saham and t not in saham):
            continue
        tujuan = os.path.join(keluar, 'per_saham', t + '.json')
        if not os.path.exists(tujuan):
            tugas.append((os.path.join(keluar, 'data', f), tujuan, cfg))
    kanal.log('saham yang perlu dilatih: %d (proses %d)' % (len(tugas), proses))
    if proses > 1:
        import multiprocessing as mp
        with mp.get_context('spawn').Pool(proses) as pool:
            hasil = pool.imap_unordered(proses_saham, tugas)
            for i, (t, status, dtk) in enumerate(hasil):
                kanal.log('[%d/%d] %s %s %.0f dtk' % (i + 1, len(tugas), t, status, dtk))
    else:
        for i, tg in enumerate(tugas):
            t, status, dtk = proses_saham(tg)
            kanal.log('[%d/%d] %s %s %.0f dtk' % (i + 1, len(tugas), t, status, dtk))


# ------------------------------------------------------------- tahap 3 --

def laporan(keluar):
    from scipy.stats import binomtest
    folder = os.path.join(keluar, 'per_saham')
    semua = [json.load(open(os.path.join(folder, f))) for f in sorted(os.listdir(folder)) if f.endswith('.json')]
    baris = []
    tulis = baris.append
    pct = lambda x: '%+7.1f%%' % (x * 100)
    tulis('RL di dalam mimpi world model -- %d saham (%s)' % (len(semua), time.strftime('%Y-%m-%d %H:%M')))
    tulis('Semua angka = return MAJEMUK periode uji 2020-2026 per saham; ringkasan = median antar saham.\n')
    seeds = sorted(semua[0]['lengan']['asli'].keys(), key=int) if semua else []

    def med_seed(h, lengan, kunci='total'):
        return float(np.median([h['lengan'][lengan][s][kunci] for s in seeds]))

    vonis = {}
    for half, judul in ((1, 'EMITEN B (utama: tak pernah dilihat world model)'), (0, 'EMITEN A (cek silang)')):
        H = [h for h in semua if h['half'] == half]
        if not H:
            continue
        tulis('=' * 78)
        tulis('%s  n=%d saham' % (judul, len(H)))
        tulis('-' * 78)
        tulis('%-10s %9s %9s %9s %8s %8s %9s %9s %9s' % ('', 'uji', 'uji 0,7%', 'latih', 'pegang%', 'ganti',
                                                         'ep_mimpi', 'ep_latih', 'ep_uji'))
        for nama in ('pegang', 'linear'):
            tulis('%-10s %9s %9s %9s %7.0f%% %8.0f' % (
                nama, pct(np.median([h[nama]['total'] for h in H])), pct(np.median([h[nama]['total_07'] for h in H])),
                '', np.median([h[nama]['porsi_pegang'] for h in H]) * 100, np.median([h[nama]['ganti'] for h in H])))
        for lengan in ('asli', 'mimpi', 'campur'):
            g = lambda k: np.median([med_seed(h, lengan, k) for h in H])
            gm = lambda k: np.median([np.median([h['lengan'][lengan][s][k] for s in seeds
                                                 if h['lengan'][lengan][s][k] is not None]) for h in H])
            tulis('%-10s %9s %9s %9s %7.0f%% %8.0f %8.2f%% %8.2f%% %8.2f%%' % (
                lengan, pct(g('total')), pct(g('total_07')), pct(g('latih_total')), g('porsi_pegang') * 100,
                g('ganti'), gm('ep_mimpi'), gm('ep_latih'), gm('ep_uji')))
        tulis('(ep_* = rata-rata return bersih per episode 60 langkah; celah mimpi = ep_mimpi - ep_latih)')
        mc = lambda k: np.median([h['mimpi_cek'][k] for h in H])
        tulis('realisme mimpi (log-return harian, %%): mimpi rata %.3f sd %.2f | asli <2020 rata %.3f sd %.2f\n'
              % (mc('mu_mimpi'), mc('sd_mimpi'), mc('mu_asli'), mc('sd_asli')))

        for lengan in ('mimpi', 'campur'):
            d_asli = np.array([med_seed(h, lengan) - med_seed(h, 'asli') for h in H])
            d_lin = np.array([med_seed(h, lengan) - h['linear']['total'] for h in H])
            d_acak = np.array([med_seed(h, lengan) - med_seed(h, lengan, 'acak') for h in H])
            menang = int((d_asli > 0).sum()); seri = int((d_asli == 0).sum())
            pv = binomtest(menang, len(H) - seri, 0.5, alternative='greater').pvalue if len(H) > seri else 1.0
            a = np.median(d_asli) > 0 and menang / max(len(H) - seri, 1) > 0.5 and pv < 0.05
            b = np.median(d_lin) > 0 and np.median(d_acak) > 0
            per_seed = [float(np.median([h['lengan'][lengan][s]['total'] - h['lengan']['asli'][s]['total'] for h in H]))
                        for s in seeds]
            c = sum(x > 0 for x in per_seed) >= 4
            thn = sorted({y for h in H for y in h['pegang']['tahun']})
            per_thn = []
            for y in thn:
                v = [np.median([h['lengan'][lengan][s]['tahun'].get(y, 0) for s in seeds])
                     - np.median([h['lengan']['asli'][s]['tahun'].get(y, 0) for s in seeds]) for h in H]
                per_thn.append(float(np.median(v)))
            dd = sum(x > 0 for x in per_thn) >= 5
            tulis('%s vs asli: median selisih %s, menang %d/%d saham (uji tanda p=%.3g)  -> (a) %s'
                  % (lengan, pct(np.median(d_asli)), menang, len(H) - seri, pv, 'ya' if a else 'TIDAK'))
            tulis('   vs linear %s, vs acak setara %s  -> (b) %s'
                  % (pct(np.median(d_lin)), pct(np.median(d_acak)), 'ya' if b else 'TIDAK'))
            tulis('   per seed %s  -> (c) %s' % (' '.join(pct(x).strip() for x in per_seed), 'ya' if c else 'TIDAK'))
            tulis('   per tahun %s  -> (d) %s' % (' '.join('%s:%s' % (y, pct(x).strip()) for y, x in zip(thn, per_thn)),
                                                  'ya' if dd else 'TIDAK'))
            vonis[(half, lengan)] = (a, b, c, dd, np.median(d_asli))
        tulis('')
    tulis('=' * 78)
    tulis('VONIS (kriteria didaftar 29 Okt 2026)')
    for lengan in ('mimpi', 'campur'):
        if (1, lengan) not in vonis:
            continue
        a, b, c, dd, med = vonis[(1, lengan)]
        searah = (0, lengan) not in vonis or (vonis[(0, lengan)][4] > 0) == (med > 0)
        lolos = a and b and c and dd and searah
        tulis('  %-7s %s  (a=%s b=%s c=%s d=%s, A searah=%s)' % (
            lengan, 'LOLOS' if lolos else 'GAGAL', a, b, c, dd, searah))
    teks = '\n'.join(baris)
    print(teks)
    with open(os.path.join(keluar, 'laporan.txt'), 'w', encoding='utf-8') as f:
        f.write(teks + '\n')


# ---------------------------------------------------------------- asap --

def asap():
    keluar = os.path.join(PN.RESEARCH_CACHE, 'rl_mimpi_asap')
    os.makedirs(keluar, exist_ok=True)
    kanal = Kanal(os.path.join(keluar, 'asap.log'))
    t0 = time.time()
    siapkan(keluar, kanal, maks=3, jalur=200, kv=True)
    kanal.log('siapkan %.0f dtk' % (time.time() - t0))

    # cek hitungan biaya & pembanding trivial
    lr = np.array([0.01, -0.02, 0.03, 0.0])
    assert abs(bersih(np.array([1, 1, 1, 1]), lr, 0.0045).sum() - (0.02 - 0.0045)) < 1e-12
    assert bersih(np.zeros(4, np.int8), lr, 0.0045).sum() == 0
    assert abs(bersih(np.array([1, 0, 1, 0]), lr, 0.0045).sum() - (0.04 - 4 * 0.0045)) < 1e-12
    kanal.log('cek biaya: OK')

    cfg = {'seeds': (7,), 'iters': 5, 'eps': 64}
    berkas = sorted(f for f in os.listdir(os.path.join(keluar, 'data')) if f.endswith('.npz'))
    hasil = []
    for f in berkas:
        t1 = time.time()
        tujuan = os.path.join(keluar, f[:-4] + '_1.json')
        t, status, _ = proses_saham((os.path.join(keluar, 'data', f), tujuan, cfg))
        kanal.log('%s %s  %.1f dtk (1 seed, %d iterasi)' % (t, status, time.time() - t1, cfg['iters']))
        hasil.append(tujuan)
    # independensi: saham pertama diulang sendirian -> harus identik
    f = berkas[0]
    tujuan2 = os.path.join(keluar, f[:-4] + '_2.json')
    proses_saham((os.path.join(keluar, 'data', f), tujuan2, cfg))
    a, b = json.load(open(hasil[0])), json.load(open(tujuan2))
    a.pop('detik'); b.pop('detik')
    kanal.log('cek independensi (ulang sendirian identik): %s' % ('OK' if a == b else 'BEDA'))
    for h in hasil:
        d = json.load(open(h))
        s = d['lengan']['asli']['7']
        kanal.log('%s pegang %+.1f%% | linear %+.1f%% | asli %+.1f%% (pegang %.0f%%, ganti %d) mimpi %+.1f%% campur %+.1f%% '
                  '| mimpi sd %.2f vs asli %.2f' % (
                      d['ticker'], d['pegang']['total'] * 100, d['linear']['total'] * 100, s['total'] * 100,
                      s['porsi_pegang'] * 100, s['ganti'], d['lengan']['mimpi']['7']['total'] * 100,
                      d['lengan']['campur']['7']['total'] * 100, d['mimpi_cek']['sd_mimpi'], d['mimpi_cek']['sd_asli']))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    saham = set(os.environ['SAHAM'].split(',')) if os.environ.get('SAHAM') else None
    os.makedirs(KELUAR, exist_ok=True)
    if cmd == 'mimpi':
        kanal = Kanal(os.path.join(KELUAR, 'mimpi.log'))
        siapkan(KELUAR, kanal, maks=_env('MAKS_SAHAM', 0), saham=saham, jalur=_env('JALUR', 2000), kv=True)
    elif cmd == 'latih':
        kanal = Kanal(os.path.join(KELUAR, 'latih.log'))
        cfg = {'seeds': SEEDS, 'iters': _env('ITER', 60), 'eps': _env('EPS', 128)}
        latih_semua(KELUAR, kanal, cfg, saham=saham, proses=_env('PROSES', 1))
    elif cmd == 'laporan':
        laporan(KELUAR)
    elif cmd == 'asap':
        asap()
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
