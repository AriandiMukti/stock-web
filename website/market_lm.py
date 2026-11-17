"""
Market LM: transformer decoder-only (gaya GPT) DILATIH DARI NOL -- bobot
acak, tanpa pretrained weights, tanpa library model (attention/MLP/block
ditulis manual di bawah) -- buat "menganalisa saham" dengan cara yang
sama seperti LLM teks memprediksi kata berikutnya: di sini "kata"-nya
bukan token bahasa, tapi KEADAAN PASAR harian.

BACA INI DULU -- INI BUKAN LLM SEPERTI CHATGPT/CLAUDE
Model bahasa komersial dilatih di triliunan token teks dengan ribuan GPU
selama berbulan-bulan. Ini dilatih di puluhan ribu hari-emiten di CPU
selama beberapa menit. Yang bisa dipelajari cuma statistik urutan
KEADAAN pasar jangka pendek -- BUKAN membaca berita, BUKAN mengerti
fundamental, BUKAN "menganalisa" dalam arti bernalar. Anggap ini
demonstrasi arsitektur riset (mini-GPT) diterapkan ke data pasar, bukan
alat trading.

V2 -- PENGETAHUAN PROJECT INI DITAMBAHKAN SEBAGAI TOKEN, BUKAN CUMA HARGA
Versi awal cuma tahu return/volume/arus harian mentah. Sekarang tiap hari
dipecah jadi 8 "channel" terpisah -- gabungan angka mentah DAN status
dari sinyal-sinyal yang sudah diuji/ditemukan di project ini sepanjang
sesi ini -- supaya modelnya bisa belajar KORELASI ANTAR SINYAL, bukan
cuma korelasi harga-ke-harga:

  1. Return harian        (7 kelompok)  -- data mentah
  2. Volume relatif 20h    (3 kelompok)  -- data mentah
  3. Arus Top5 harian      (3 kelompok)  -- data mentah
  4. Arus Retail harian    (3 kelompok)  -- data mentah
  5. Status Jatuh Dalam    (3): normal / dalam (>40% dari puncak 60h) /
     dalam_sekali (>60%) -- persis definisi jatuh_dalam.py
  6. Status Akumulasi Palsu (3): lainnya / turun+Top5-beli (sel TERBAIK
     di fake_accumulation.py) / naik-banyak+Top5-beli (sel PALSU/jebakan)
  7. Aktivitas insider 20h (3): tidak_ada / ada_BELI / ada_JUAL -- dari
     insider_activity.py (cuma terisi utk ~409/865 emiten yg pernah ada
     transaksi insidernya; sisanya selalu "tidak_ada", itu jujur apa
     adanya, bukan diisi tebakan)
  8. Volatilitas 20h        (5 kelompok) -- ambang sama seperti
     risiko.py (VOL_BIN)

Kenapa dipisah 8 channel, bukan digabung jadi satu token raksasa (kayak
v1 yang 7x3x3x3=189)? Kalau semua 8 sumbu dikalikan jadi satu token,
vocab-nya meledak ke puluhan ribu kombinasi -- dengan cuma ~100 ribu
hari-token yang ada, hampir semua kombinasi cuma muncul 0-1 kali, model
tidak sempat belajar apa pun. Dipisah per channel (gaya sub-word
tokenizer teks), satu hari = 8 token berurutan, vocab totalnya cuma 30
token (jauh lebih kecil dari v1!) tapi historinya jadi 8x lebih panjang
per hari yang sama -- model belajar hubungan ANTAR channel lewat
attention, bukan lewat vocab yang membengkak.

ARSITEKTUR
Decoder-only transformer, causal self-attention -- kerangka GPT, ditulis
manual. Tambahan dari v1: embedding "channel" (posisi 0-7 dalam satu
hari) supaya model langsung tahu channel_emb) supaya model tidak perlu
menebak-nebak dari posisi absolut saja channel mana yang sedang dilihat.

Run: python market_lm.py            (latih dari nol, simpan checkpoint)
     python market_lm.py analisa TICKER [TICKER ...]
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import glob
import math
import os
import sys

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.nn import functional as F

from config import DAILY_PATH

_WEBSITE_DIR = os.path.dirname(os.path.abspath(__file__))
_FLASK_DIR = os.path.dirname(_WEBSITE_DIR)
if _FLASK_DIR not in sys.path:
    sys.path.insert(0, _FLASK_DIR)
from website import insider_activity as ia  # noqa: E402  (perlu sys.path di atas dulu)

SUMMARY_DIR = os.path.join(DAILY_PATH, 'Summary')
CHECKPOINT_PATH = str(_runtime_file('', 'market_lm.pt'))

# ---------------------------------------------------------------- Vocab --

RETURN_EDGES = [-1e9, -5.0, -2.0, -0.5, 0.5, 2.0, 5.0, 1e9]
RETURN_LABELS = ['<-5%', '-5%~-2%', '-2%~-0.5%', '-0.5%~0.5%', '0.5%~2%', '2%~5%', '>5%']
VOLUME_EDGES = [0, 0.7, 1.5, 1e9]
VOLUME_LABELS = ['sepi', 'normal', 'ramai']
FLOW_EDGES = [-1e9, -0.5, 0.5, 1e9]  # satuan std-score, lihat _flow_bucket
FLOW_LABELS = ['jual', 'netral', 'beli']
JATUH_LABELS = ['normal', 'dalam(>40%)', 'dalam_sekali(>60%)']
AKUMULASI_LABELS = ['lainnya', 'terbaik(turun+Top5beli)', 'palsu(naik_banyak+Top5beli)']
INSIDER_LABELS = ['tidak_ada', 'ada_BELI', 'ada_JUAL']
# Sama seperti risiko.py VOL_BIN.
RISIKO_EDGES = [0, 1.5, 2.5, 3.5, 5.0, 1e9]
RISIKO_LABELS = ['<1,5%', '1,5-2,5%', '2,5-3,5%', '3,5-5%', '>5%']

CHANNELS = [
    ('return', RETURN_LABELS),
    ('volume', VOLUME_LABELS),
    ('top5_flow', FLOW_LABELS),
    ('retail_flow', FLOW_LABELS),
    ('jatuh_dalam', JATUH_LABELS),
    ('akumulasi_palsu', AKUMULASI_LABELS),
    ('insider', INSIDER_LABELS),
    ('risiko_volatilitas', RISIKO_LABELS),
]
N_CHANNELS = len(CHANNELS)
CHANNEL_SIZES = [len(labels) for _, labels in CHANNELS]
CHANNEL_OFFSETS = np.cumsum([0] + CHANNEL_SIZES[:-1]).tolist()
VOCAB_SIZE = sum(CHANNEL_SIZES)  # 7+3+3+3+3+3+3+5 = 30

PUNCAK_W = 60  # sama seperti jatuh_dalam.py
FA_WINDOW = 20  # sama seperti fake_accumulation.py
INSIDER_LOOKBACK_DAYS = 20  # sama seperti insider_signal.py


def _bucket(value, edges):
    idx = np.searchsorted(edges, value, side='right') - 1
    return int(np.clip(idx, 0, len(edges) - 2))


def _flow_bucket(series):
    """Skor-z per emiten (arus dibagi skala arus emiten itu sendiri -- Top5
    lot BBRI dan saham gorengan beda 100x lipat, ambang mutlak tidak masuk akal)."""
    scale = series.abs().rolling(40, min_periods=10).mean().replace(0, np.nan)
    return (series / scale).fillna(0.0)


def global_token(channel_idx, local_bucket):
    return CHANNEL_OFFSETS[channel_idx] + local_bucket


def decode_global_token(channel_idx, token):
    return CHANNELS[channel_idx][1][token - CHANNEL_OFFSETS[channel_idx]]


def describe_day(day_tokens):
    """day_tokens: 8 token global buat satu hari -> deskripsi manusiawi."""
    parts = [decode_global_token(c, t) for c, t in enumerate(day_tokens)]
    names = [name for name, _ in CHANNELS]
    return ', '.join(f'{n}={p}' for n, p in zip(names, parts))


_insider_cache = None


def _insider_dates_by_ticker():
    global _insider_cache
    if _insider_cache is None:
        df = ia.load_all()
        trade = df[df['is_market_trade']].copy()
        trade['day'] = trade['date'].dt.normalize()
        _insider_cache = {}
        for ticker, g in trade.groupby('ticker'):
            _insider_cache[ticker] = {
                'buy': np.array(sorted(g[g['action_type'] == 'ACTION_TYPE_BUY']['day'])),
                'sell': np.array(sorted(g[g['action_type'] == 'ACTION_TYPE_SELL']['day'])),
            }
    return _insider_cache


def _recent_activity_flags(dates, event_dates, lookback_days):
    """Untuk tiap tanggal di `dates`, apakah ADA event_dates di jendela
    [tanggal - lookback_days, tanggal]? Vektor boolean, lewat searchsorted
    supaya tidak loop manual per hari."""
    if len(event_dates) == 0:
        return np.zeros(len(dates), dtype=bool)
    lo = dates - pd.Timedelta(days=lookback_days)
    idx_lo = np.searchsorted(event_dates, lo, side='left')
    idx_hi = np.searchsorted(event_dates, dates, side='right')
    return idx_hi > idx_lo


def tokenize_ticker(ticker, df):
    """DataFrame Summary satu emiten -> array token 1D (n_hari_valid * 8),
    hari demi hari, tiap hari 8 token channel berurutan."""
    close = df['Close'].astype(float)
    high = df['High'].astype(float)
    dates = pd.DatetimeIndex(df['Date'])

    ret_pct = close.pct_change() * 100
    vol_rel = df['Volume'].astype(float) / df['Volume'].astype(float).rolling(20, min_periods=5).mean()
    top5_raw = df['Net Top5 All Lot'].astype(float).fillna(0.0)
    retail_raw = df['Retail'].astype(float).fillna(0.0)
    top5_z = _flow_bucket(top5_raw)
    retail_z = _flow_bucket(retail_raw)

    puncak60 = high.rolling(PUNCAK_W, min_periods=PUNCAK_W).max()
    dari_puncak = (close / puncak60 - 1) * 100

    trail20_pct = (close - close.shift(FA_WINDOW)) / close.shift(FA_WINDOW) * 100
    top5_roll20 = top5_raw.rolling(FA_WINDOW).sum()

    vol20 = ret_pct.rolling(20, min_periods=10).std()

    insider = _insider_dates_by_ticker().get(ticker, {'buy': np.array([]), 'sell': np.array([])})
    recent_buy = _recent_activity_flags(dates, insider['buy'], INSIDER_LOOKBACK_DAYS)
    recent_sell = _recent_activity_flags(dates, insider['sell'], INSIDER_LOOKBACK_DAYS)

    n = len(df)
    out = []
    for i in range(n):
        if i < 40 or pd.isna(ret_pct.iloc[i]) or pd.isna(vol_rel.iloc[i]) or pd.isna(dari_puncak.iloc[i]):
            continue

        rb = _bucket(ret_pct.iloc[i], RETURN_EDGES)
        vb = _bucket(vol_rel.iloc[i], VOLUME_EDGES)
        fb = _bucket(top5_z.iloc[i], FLOW_EDGES)
        rib = _bucket(retail_z.iloc[i], FLOW_EDGES)

        dp = dari_puncak.iloc[i]
        jb = 2 if dp <= -60 else (1 if dp <= -40 else 0)

        if pd.isna(trail20_pct.iloc[i]):
            ab = 0
        else:
            tprice = trail20_pct.iloc[i]
            tflow_beli = top5_roll20.iloc[i] > 0
            if tprice <= -5.0 and tflow_beli:
                ab = 1  # terbaik
            elif tprice > 20.0 and tflow_beli:
                ab = 2  # palsu/jebakan
            else:
                ab = 0

        ib = 2 if recent_sell[i] else (1 if recent_buy[i] else 0)  # jual menang kalau dua2nya (konsisten insider_event_study: hari campuran dibuang -> di sini jual diprioritaskan drpd diam2 pilih beli)

        rv = vol20.iloc[i]
        vib = _bucket(rv, RISIKO_EDGES) if pd.notna(rv) else 0

        day_tokens = [rb, vb, fb, rib, jb, ab, ib, vib]
        out.extend(global_token(c, b) for c, b in enumerate(day_tokens))
    return np.array(out, dtype=np.int64)


def build_corpus(max_tickers=None):
    """{ticker: token_array_1d} -- panggil _insider_dates_by_ticker() sekali
    di awal supaya cache-nya kebentuk sebelum loop paralel-per-ticker."""
    _insider_dates_by_ticker()
    paths = sorted(glob.glob(os.path.join(SUMMARY_DIR, '*_Summary.csv')))
    if max_tickers:
        paths = paths[:max_tickers]
    corpus = {}
    for path in paths:
        ticker = os.path.basename(path).split('_')[0]
        try:
            df = pd.read_csv(path, usecols=['Date', 'Close', 'High', 'Volume', 'Net Top5 All Lot', 'Retail'])
        except Exception:
            continue
        df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
        df = df.dropna(subset=['Date', 'Close']).sort_values('Date').reset_index(drop=True)
        if len(df) < 70:
            continue
        toks = tokenize_ticker(ticker, df)
        if len(toks) >= N_CHANNELS * 5:
            corpus[ticker] = toks
    return corpus


# --------------------------------------------------------------- Dataset --

class MarketSequenceDataset(torch.utils.data.Dataset):
    """Jendela geser (block_size+1) token, DIGESER PER HARI (kelipatan
    N_CHANNELS) supaya tiap contoh selalu mulai di batas awal hari, bukan
    di tengah-tengah 8 channel satu hari -- tidak menyeberang batas emiten."""

    def __init__(self, corpus, days_context):
        self.block_size = days_context * N_CHANNELS
        self.windows = []
        self.corpus = corpus
        for ticker, toks in corpus.items():
            n_days = len(toks) // N_CHANNELS
            for start_day in range(0, n_days - days_context - 1):
                self.windows.append((ticker, start_day * N_CHANNELS))

    def __len__(self):
        return len(self.windows)

    def __getitem__(self, idx):
        ticker, start = self.windows[idx]
        toks = self.corpus[ticker]
        chunk = toks[start:start + self.block_size + 1]
        x = torch.from_numpy(chunk[:-1].copy())
        y = torch.from_numpy(chunk[1:].copy())
        return x, y


# ----------------------------------------------------------- Model (GPT) --

class CausalSelfAttention(nn.Module):
    def __init__(self, n_embd, n_head, block_size, dropout):
        super().__init__()
        assert n_embd % n_head == 0
        self.n_head = n_head
        self.qkv = nn.Linear(n_embd, 3 * n_embd)
        self.proj = nn.Linear(n_embd, n_embd)
        self.attn_drop = nn.Dropout(dropout)
        self.resid_drop = nn.Dropout(dropout)
        mask = torch.tril(torch.ones(block_size, block_size)).view(1, 1, block_size, block_size)
        self.register_buffer('mask', mask)

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        q = q.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        k = k.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        v = v.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)

        att = (q @ k.transpose(-2, -1)) / math.sqrt(k.size(-1))
        att = att.masked_fill(self.mask[:, :, :T, :T] == 0, float('-inf'))
        att = F.softmax(att, dim=-1)
        att = self.attn_drop(att)
        out = att @ v
        out = out.transpose(1, 2).contiguous().view(B, T, C)
        return self.resid_drop(self.proj(out))


class MLP(nn.Module):
    def __init__(self, n_embd, dropout):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd), nn.GELU(),
            nn.Linear(4 * n_embd, n_embd), nn.Dropout(dropout),
        )

    def forward(self, x):
        return self.net(x)


class Block(nn.Module):
    def __init__(self, n_embd, n_head, block_size, dropout):
        super().__init__()
        self.ln1 = nn.LayerNorm(n_embd)
        self.attn = CausalSelfAttention(n_embd, n_head, block_size, dropout)
        self.ln2 = nn.LayerNorm(n_embd)
        self.mlp = MLP(n_embd, dropout)

    def forward(self, x):
        x = x + self.attn(self.ln1(x))
        x = x + self.mlp(self.ln2(x))
        return x


class MarketGPT(nn.Module):
    def __init__(self, vocab_size, block_size, n_channels, n_embd=64, n_head=4, n_layer=4, dropout=0.1):
        super().__init__()
        self.block_size = block_size
        self.n_channels = n_channels
        self.tok_emb = nn.Embedding(vocab_size, n_embd)
        self.pos_emb = nn.Embedding(block_size, n_embd)
        self.channel_emb = nn.Embedding(n_channels, n_embd)  # posisi 0-7 dalam satu "hari"
        self.drop = nn.Dropout(dropout)
        self.blocks = nn.ModuleList([Block(n_embd, n_head, block_size, dropout) for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(n_embd)
        self.head = nn.Linear(n_embd, vocab_size, bias=False)
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)

    def forward(self, idx, targets=None):
        B, T = idx.shape
        pos = torch.arange(T, device=idx.device)
        channel_pos = pos % self.n_channels
        x = self.drop(self.tok_emb(idx) + self.pos_emb(pos) + self.channel_emb(channel_pos))
        for block in self.blocks:
            x = block(x)
        x = self.ln_f(x)
        logits = self.head(x)
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))
        return logits, loss

    @torch.no_grad()
    def next_token_distribution(self, idx):
        self.eval()
        idx_cond = idx[:, -self.block_size:]
        logits, _ = self(idx_cond)
        return F.softmax(logits[0, -1], dim=-1)


# ---------------------------------------------------------------- Train --

DAYS_CONTEXT = 16  # ~3 minggu bursa
BLOCK_SIZE = DAYS_CONTEXT * N_CHANNELS  # 128
BATCH_SIZE = 64
MAX_STEPS = 3000
LR = 3e-4
VAL_FRACTION = 0.1


def train(max_tickers=None):
    print('Membangun korpus token dari Daily/Summary + insider_activity...')
    corpus = build_corpus(max_tickers=max_tickers)
    total_days = sum(len(v) // N_CHANNELS for v in corpus.values())
    print(f'{len(corpus)} emiten, {total_days} hari total ({total_days * N_CHANNELS} token), vocab={VOCAB_SIZE}')

    n_with_insider = sum(1 for t, toks in corpus.items()
                          if t in _insider_dates_by_ticker() and
                          (len(_insider_dates_by_ticker()[t]['buy']) or len(_insider_dates_by_ticker()[t]['sell'])))
    print(f'{n_with_insider} dari {len(corpus)} emiten punya histori insider (sisanya channel insider selalu "tidak_ada")')

    tickers = sorted(corpus.keys())
    split = int(len(tickers) * (1 - VAL_FRACTION))
    train_corpus = {t: corpus[t] for t in tickers[:split]}
    val_corpus = {t: corpus[t] for t in tickers[split:]}
    print(f'Split per-EMITEN: {len(train_corpus)} latih, {len(val_corpus)} validasi (emiten belum pernah dilihat)')

    train_ds = MarketSequenceDataset(train_corpus, DAYS_CONTEXT)
    val_ds = MarketSequenceDataset(val_corpus, DAYS_CONTEXT)
    print(f'{len(train_ds)} jendela latih, {len(val_ds)} jendela validasi, block_size={BLOCK_SIZE} token')

    train_loader = torch.utils.data.DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, drop_last=True)
    val_loader = torch.utils.data.DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, drop_last=True)

    model = MarketGPT(VOCAB_SIZE, BLOCK_SIZE, N_CHANNELS)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'MarketGPT: {n_params:,} parameter')

    opt = torch.optim.AdamW(model.parameters(), lr=LR)

    # Baseline pembanding BUKAN log(VOCAB_SIZE) seperti v1 -- channel
    # ukurannya beda-beda (7 vs 3 vs 5), jadi baseline nebak-buta yang adil
    # adalah RATA-RATA log(ukuran channel) per posisi, bukan log(total vocab).
    uniform_loss = np.mean([math.log(sz) for _, labels in CHANNELS for sz in [len(labels)]])
    print(f'Baseline loss (nebak buta per channel, rata2): {uniform_loss:.3f}')

    step = 0
    train_iter = iter(train_loader)
    model.train()
    while step < MAX_STEPS:
        try:
            x, y = next(train_iter)
        except StopIteration:
            train_iter = iter(train_loader)
            x, y = next(train_iter)

        logits, loss = model(x, y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        step += 1

        if step % 300 == 0 or step == 1:
            model.eval()
            with torch.no_grad():
                val_losses = []
                for i, (vx, vy) in enumerate(val_loader):
                    _, vloss = model(vx, vy)
                    val_losses.append(vloss.item())
                    if i >= 30:
                        break
            model.train()
            print(f'step {step:>5}/{MAX_STEPS}  train_loss {loss.item():.3f}  '
                  f'val_loss {np.mean(val_losses):.3f}  (baseline nebak-buta {uniform_loss:.3f})')

    torch.save({
        'model_state': model.state_dict(),
        'vocab_size': VOCAB_SIZE, 'block_size': BLOCK_SIZE, 'n_channels': N_CHANNELS,
        'n_embd': 64, 'n_head': 4, 'n_layer': 4,
    }, CHECKPOINT_PATH)
    print(f'Checkpoint disimpan: {CHECKPOINT_PATH}')
    return model, val_corpus


# ------------------------------------------------------------- Inference --

def load_model():
    ckpt = torch.load(CHECKPOINT_PATH, map_location='cpu', weights_only=True)
    model = MarketGPT(ckpt['vocab_size'], ckpt['block_size'], ckpt['n_channels'],
                       n_embd=ckpt['n_embd'], n_head=ckpt['n_head'], n_layer=ckpt['n_layer'])
    model.load_state_dict(ckpt['model_state'])
    model.eval()
    return model, ckpt['block_size']


def analisa(ticker, model=None, block_size=None):
    """'Analisa' = distribusi probabilitas TIAP CHANNEL besok (bukan cuma
    return -- juga status Jatuh Dalam/Akumulasi Palsu/insider/risiko yang
    diprediksi model) + seberapa 'mengejutkan' hari-hari terakhir bagi
    model. BUKAN rekomendasi beli/jual -- baca peringatan di docstring atas."""
    if model is None:
        model, block_size = load_model()
    days_context = block_size // N_CHANNELS

    path = os.path.join(SUMMARY_DIR, f'{ticker}_Summary.csv')
    if not os.path.exists(path):
        print(f'{ticker}: data tidak ditemukan.')
        return
    df = pd.read_csv(path, usecols=['Date', 'Close', 'High', 'Volume', 'Net Top5 All Lot', 'Retail'])
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%y', errors='coerce')
    df = df.dropna(subset=['Date', 'Close']).sort_values('Date').reset_index(drop=True)
    toks = tokenize_ticker(ticker, df)
    if len(toks) < block_size + N_CHANNELS:
        print(f'{ticker}: histori belum cukup panjang buat model ini.')
        return

    last_day_tokens = toks[-N_CHANNELS:]
    print(f'\n=== {ticker} -- hari terakhir: {describe_day(last_day_tokens)} ===')
    print(f'--- Prediksi keadaan BESOK, per channel (dari {days_context} hari terakhir) ---')

    # Basis histori cuma (block_size - N_CHANNELS) token (bukan block_size
    # penuh) supaya waktu channel hari INI ditambah satu-satu, panjangnya
    # tidak pernah melewati block_size -- kalau melewati, next_token_
    # distribution akan memotong dari DEPAN per-TOKEN (bukan per-HARI) dan
    # mengacaukan channel_emb (posisi 0 keliru dikira channel 'return' padahal
    # bukan) -- pernah kejadian, perplexity meledak ratusan kali lipat gara2 ini.
    history_base = toks[-(block_size - N_CHANNELS):] if block_size > N_CHANNELS else toks[-block_size:]
    running = torch.tensor(history_base, dtype=torch.long).unsqueeze(0)
    entropies = []
    for c, (name, labels) in enumerate(CHANNELS):
        probs = model.next_token_distribution(running)
        lo, hi = CHANNEL_OFFSETS[c], CHANNEL_OFFSETS[c] + len(labels)
        channel_probs = probs[lo:hi]
        channel_probs = channel_probs / channel_probs.sum()
        top = torch.topk(channel_probs, min(3, len(labels)))
        preds = ', '.join(f'{labels[i]} ({p*100:.0f}%)' for p, i in zip(top.values.tolist(), top.indices.tolist()))
        print(f'  {name:<20} {preds}')
        entropy = -(channel_probs * torch.log(channel_probs + 1e-9)).sum().item()
        entropies.append(entropy / math.log(len(labels)))
        # Teacher-force channel token TERBAIK ke urutan sblm nebak channel
        # berikutnya di hari yang sama -- channel saling bergantung (mis.
        # 'akumulasi_palsu' baru masuk akal setelah 'return' diketahui).
        best_tok = lo + int(top.indices[0].item())
        running = torch.cat([running, torch.tensor([[best_tok]])], dim=1)

    print(f'  Ketidakpastian rata-rata: {np.mean(entropies)*100:.0f}% dari maksimum per channel')

    n_check_days = min(10, len(toks) // N_CHANNELS - days_context - 1)
    if n_check_days > 0:
        nlls = []
        for k in range(n_check_days, 0, -1):
            day_start = len(toks) - k * N_CHANNELS
            ctx = torch.tensor(toks[day_start - (block_size - N_CHANNELS):day_start], dtype=torch.long).unsqueeze(0)
            for c in range(N_CHANNELS):
                actual = int(toks[day_start + c])
                p = model.next_token_distribution(ctx)
                nlls.append(-torch.log(p[actual] + 1e-9).item())
                ctx = torch.cat([ctx, torch.tensor([[actual]])], dim=1)
        avg_nll = float(np.mean(nlls))
        print(f'  Perplexity {n_check_days} hari terakhir (semua channel): {math.exp(avg_nll):.1f} '
              f'(makin tinggi = pola belakangan ini makin tidak biasa menurut model)')
    print()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'analisa':
        tickers = sys.argv[2:] or ['BBRI', 'TLKM', 'ASII']
        m, bs = load_model()
        for t in tickers:
            analisa(t.upper(), model=m, block_size=bs)
    else:
        max_t = None
        if len(sys.argv) > 1 and sys.argv[1] == 'quick':
            max_t = 150
        train(max_tickers=max_t)
