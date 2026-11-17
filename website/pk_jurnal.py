"""
Jurnal maju: saham MASUK Papan Pemantauan Khusus (full call auction).

KENAPA INI ADA
==============
riset_pola_naik/pemantauan_khusus.py (18 Okt 2026): masuk papan karena
kriteria FUNDAMENTAL (Mfund: 2 disclaimer, 3 tanpa pendapatan, 5 ekuitas
negatif, 6 free float, 8/9 PKPU/pailit, 11 OJK) LOLOS sebagai sinyal HINDARI
-- H+5 -4,2%, H+20 -8,7% vs pasar, 72% negatif. Tapi n 84 dalam 3 tahun dan
semuanya kalibrasi. Jurnal ini mencatat tiap pengumuman Peng-PK BARU
sesudah 16 Okt 2026 dan menilainya dengan aturan yang sama.

ATURAN -- DIKUNCI 18 Okt 2026, JANGAN DIUBAH
============================================
(sama dengan DESAIN di pemantauan_khusus.py)
  Sumber   Pengumuman BEI "Efek Bersifat Ekuitas Dalam Pemantauan Khusus"
           (nomor Peng-PK-...). Baris "Masuk / Enter" saja; Perubahan
           (Peng-UK) dan Pencabutan (Peng-CK) tidak dipakai.
  Kelompok kriteria berisi 10 -> M10; selain itu ada 2,3,5,6,8,9,11 -> Mfund;
           selain itu ada 1/7 -> Mharga; sisanya Mlain. Yang DIUJI: Mfund.
           Kelompok lain tetap dicatat & dinilai, tapi bukan klaimnya.
  Masuk    close tanggal EFEKTIF (hari bursa itu, atau berikutnya kalau
           libur, maks 7 hari) -- kalender_bursa._maju.
  Hasil    x5 / x20 = return log H+5 / H+20 dikurangi rata-rata return log
           semua emiten untuk tanggal & horizon yang sama; hari_h = gerak
           hari efektif itu sendiri (mentah, informasi). Dibuang kalau ada
           gerak harian > 35% di H-1..H+20 (aksi korporasi tak disesuaikan).
  Klaim    Mfund: x5 < 0 dan x20 < 0 (kalibrasi -4,2% / -8,7%).
  Dobel    satu kejadian per (emiten, tanggal efektif); pengumuman KOREKSI
           untuk kejadian yang sama tidak dihitung lagi.

DATA -- LEWAT BROWSER
=====================
IDX menolak Python (Cloudflare 403) sejak Sep 2026. Jadi sama seperti
registri/LBRPE di /perbarui-kepemilikan: menu membuat skrip Console
(skrip_browser), skrip itu dijalankan di tab www.idx.co.id -- mendaftar
pengumuman lewat /primary/ListedCompany/GetAnnouncement, membaca PDF-nya
dengan pdf.js, lalu mengunduh satu JSON berisi teks bagian Indonesianya.
File itu diimpor (impor_browser) dan diurai di server. Tidak ada pembobolan
apa pun: semua request datang dari browser kamu sendiri, satu-satu, berjeda.
Parser tabel diuji 18 Okt 2026 pada 177 PDF Peng-PK Apr 2025 - Okt 2026:
327/327 kejadian masuk sama dengan berkas riset.

- tanggal_catat = hari impor. Kalau impor telat, kejadiannya tetap dinilai
  dengan aturan yang sama (yang diukur pengumumannya, bukan kapan dilihat),
  tapi kolom telat_hb mencatat berapa hari bursa sesudah hari efektif
  kejadian itu baru masuk jurnal -- sebesar itulah yang tak bisa diambil.
- Pengumuman s.d. 16 Okt 2026 (sudah dikenal saat aturan dikunci) dicatat
  awal=1 dan tidak dinilai.

PEMAKAIAN
    python -m website.pk_jurnal                 # nilai + ringkas
    python -m website.pk_jurnal skrip > pk.js   # skrip Console (atau lewat menu)
    python -m website.pk_jurnal impor <file.json>
"""
try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
import json
import os
import re
import sys
import time

import numpy as np
import pandas as pd

from .msci_jurnal import hari_bursa, panel_close, tulis_atomik, num, hari_ini
from .riset_pola_naik import kalender_bursa as KB
from .riset_pola_naik.pemantauan_khusus import FUND, HARGA

HERE = os.path.dirname(__file__)
JURNAL_FILE = str(_runtime_file('', 'pk_jurnal.csv'))
DIR_MAJU = os.path.join(KB.DIR, 'pk_maju')
PENGUMUMAN_FILE = os.path.join(DIR_MAJU, 'pengumuman.json')   # teks mentah tiap PDF, untuk audit
IMPOR_FILE = os.path.join(DIR_MAJU, 'impor.csv')              # riwayat impor (cakupan tanggal)

FORMAT = 'bdm-pk-idx-v1'
VERSI = 'pk-v1'
BATAS_AWAL = pd.Timestamp('2026-10-16')   # pengumuman s.d. tanggal ini = awal=1
MULAI_TARIK = '20261001'                  # tarikan pertama mulai dari sini
TUMPANG = 7                               # hari: tarikan berikut mundur sekian dari tarikan lalu
HORIZON = (5, 20)
LONCAT = 0.35
IMPOR_BASI = 14                           # hari: lebih dari ini tanpa impor = diperingatkan

KLAIM = {'Mfund': 'hindari: x5 < 0 dan x20 < 0 vs pasar (kalibrasi -4,2% / -8,7%)'}
KALIBRASI = {'Mfund': {'n': 84, 'x5': -4.2, 'x20': -8.7}}

KOLOM = ['tanggal_catat', 'kejadian', 'aturan', 'awal', 'stock', 'umum', 'efektif', 'grup',
         'kriteria', 'no_pengumuman', 't0', 'telat_hb', 'status', 'hari_h', 'x5', 'x20', 'dinilai']
SELESAI = ('matang', 'dibuang_loncat', 'dibuang_harga', 'dibuang_tanggal', 'awal')

BULAN = {'januari': 1, 'februari': 2, 'maret': 3, 'april': 4, 'mei': 5, 'juni': 6, 'juli': 7,
         'agustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'desember': 12}
RE_EFEKTIF = re.compile(r'efektif pada tanggal (\d{1,2}) ([A-Za-z]+) (\d{4})', re.I)
RE_BARIS = re.compile(r'(?:^|\s)([A-Z][A-Z0-9]{3})\s+(\S[\s\S]*?)\s'
                      r'(\d{1,2}(?:\s*(?:,|\.|dan|&)\s*\d{1,2})*)\s+(Masuk|Keluar)\b')


# ---------------------------------------------------------------------------
# MENGURAI PDF (teksnya dari pdf.js di browser)
# ---------------------------------------------------------------------------
def urai(teks):
    """Teks bagian Indonesia satu PDF Peng-PK -> (tanggal efektif, [baris]).
    baris = {'stock', 'jenis' M/K, 'kr' set}. Tabelnya: Kode, Nama, Papan,
    SDHSM (kadang kosong), Kriteria, Keterangan "Masuk / Enter"."""
    teks = re.sub(r'\s+', ' ', teks or '')
    m = RE_EFEKTIF.search(teks)
    if not m or m.group(2).lower() not in BULAN:
        return None, []
    efektif = pd.Timestamp(int(m.group(3)), BULAN[m.group(2).lower()], int(m.group(1)))
    k = teks.find('Keterangan')
    badan = teks[k + len('Keterangan'):] if k >= 0 else teks
    badan = re.split(r'Perubahan ini mulai efektif|mulai efektif', badan)[0]
    baris = [{'stock': x.group(1), 'jenis': x.group(4)[0],
              'kr': {int(v) for v in re.findall(r'\d+', x.group(3))}}
             for x in RE_BARIS.finditer(badan)]
    return efektif, baris


def grup(kr):
    """SAMA dengan pemantauan_khusus.baca(): 10 dulu, lalu fundamental, lalu harga."""
    if 10 in kr:
        return 'M10'
    if kr & FUND:
        return 'Mfund'
    if kr & HARGA:
        return 'Mharga'
    return 'Mlain'


# ---------------------------------------------------------------------------
# SKRIP CONSOLE & IMPOR
# ---------------------------------------------------------------------------
_SKRIP = r"""// Pemantauan Khusus IDX untuk BDM -- jalankan di Console tab www.idx.co.id
// (F12 -> Console -> tempel -> Enter). Berhenti: bdmBerhenti = true
(async () => {
  if (!/(^|\.)idx\.co\.id$/.test(location.hostname)) {
    console.error('Buka dulu https://www.idx.co.id di tab ini, lalu tempel skrip lagi.');
    return;
  }
  const DARI = '__DARI__', SAMPAI = '__SAMPAI__';
  const DIKETAHUI = new Set(__DIKETAHUI__);
  const JEDA = __JEDA__;
  const tidur = ms => new Promise(res => setTimeout(res, ms));
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  const diambil = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
                  + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':00';
  window.bdmBerhenti = false;
  let pdfjs;
  try {
    pdfjs = await import('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.worker.min.mjs';
  } catch (e) {
    console.error('pdf.js gagal dimuat dari cdnjs: ' + e);
    return;
  }
  const daftar = [];
  let lengkap = false;
  for (let hal = 0; hal < 50; hal++) {
    let j = null;
    try {
      const r = await fetch('/primary/ListedCompany/GetAnnouncement?indexFrom=' + hal + '&pageSize=100&dateFrom=' + DARI
                            + '&dateTo=' + SAMPAI + '&lang=id&keyword=pemantauan%20khusus',
                            { headers: { Accept: 'application/json' } });
      if (r.ok) { j = JSON.parse(await r.text()); }
    } catch (e) { j = null; }
    if (!j) { console.warn('Daftar pengumuman halaman ' + hal + ' ditolak IDX. Muat ulang halaman lalu coba lagi.'); break; }
    const rep = j.Replies || [];
    daftar.push(...rep);
    if (!rep.length || daftar.length >= (j.ResultCount || 0)) { lengkap = true; break; }
    await tidur(JEDA);
  }
  const pk = [];
  for (const rep of daftar) {
    const p = rep.pengumuman || {};
    if (!/^Peng-PK-/.test(p.NoPengumuman || '')) continue;
    for (const a of (rep.attachments || [])) {
      if (a.IsAttachment || !a.FullSavePath) continue;
      const kunci = p.NoPengumuman + '|' + a.PDFFilename;
      if (!DIKETAHUI.has(kunci)) pk.push({ kunci, p, a });
    }
  }
  console.log('Pemantauan Khusus ' + DARI + '..' + SAMPAI + ': ' + daftar.length + ' pengumuman, '
              + pk.length + ' PDF Peng-PK baru.');
  const data = [], gagal = [];
  for (let i = 0; i < pk.length; i++) {
    if (window.bdmBerhenti) { console.warn('Dihentikan di ' + i + '/' + pk.length); lengkap = false; break; }
    const { kunci, p, a } = pk[i];
    try {
      const buf = await (await fetch(new URL(a.FullSavePath).pathname)).arrayBuffer();
      const doc = await pdfjs.getDocument({ data: buf }).promise;
      const hal = [];
      for (let k = 1; k <= doc.numPages; k++) {
        const c = await (await doc.getPage(k)).getTextContent();
        const t = c.items.map(x => x.str).join(' ');
        hal.push(t);
        if (/EXCHANGE ANNOUNCEMENT/.test(t)) break;
      }
      const teks = hal.join(' ').split(/EXCHANGE ANNOUNCEMENT/)[0].replace(/\s+/g, ' ');
      const m = teks.match(/^[\s\S]*?efektif pada tanggal \d{1,2} [A-Za-z]+ \d{4}/i);
      data.push({ kunci, no: p.NoPengumuman, judul: p.JudulPengumuman, tgl: p.TglPengumuman,
                  url: a.FullSavePath, teks: (m ? m[0] : teks).slice(0, 60000) });
    } catch (e) { gagal.push(kunci); }
    await tidur(JEDA);
  }
  const isi = JSON.stringify({ format: '__FORMAT__', diambil, dari: DARI, sampai: SAMPAI,
                               lengkap: lengkap && !gagal.length, data, gagal });
  const el = document.createElement('a');
  el.href = URL.createObjectURL(new Blob([isi], { type: 'application/json' }));
  el.download = 'pk_idx_' + SAMPAI + '_' + data.length + '.json';
  document.body.appendChild(el); el.click(); el.remove();
  console.log('Tersimpan: ' + data.length + ' PDF, ' + gagal.length + ' gagal -> ' + el.download
              + '. Impor lewat menu Perbarui Kepemilikan (kartu Pemantauan Khusus).');
})();
"""


def _impor_log():
    if not os.path.exists(IMPOR_FILE):
        return pd.DataFrame(columns=['diimpor', 'diambil', 'dari', 'sampai', 'lengkap', 'n_pdf', 'n_baru'])
    return pd.read_csv(IMPOR_FILE, dtype=str)


def _pengumuman():
    if not os.path.exists(PENGUMUMAN_FILE):
        return {}
    with open(PENGUMUMAN_FILE, encoding='utf-8') as fh:
        return json.load(fh)


def skrip_browser(jeda=1.5):
    """Skrip Console. Rentang mulai TUMPANG hari sebelum ujung tarikan lengkap
    terakhir (tumpang tindih disengaja -- yang sudah diimpor dilewati)."""
    log = _impor_log()
    ok = log[log['lengkap'] == '1'] if len(log) else log
    if len(ok):
        dari = (pd.Timestamp(ok['sampai'].max()) - pd.Timedelta(days=TUMPANG)).strftime('%Y%m%d')
    else:
        dari = MULAI_TARIK
    # dateTo API dibaca sebagai pukul 00.00 -- pengumuman sore hari ini baru
    # ikut kalau batasnya besok.
    sampai = (hari_ini() + pd.Timedelta(days=1)).strftime('%Y%m%d')
    diketahui = sorted(_pengumuman())
    skrip = (_SKRIP.replace('__DARI__', dari).replace('__SAMPAI__', sampai)
             .replace('__DIKETAHUI__', json.dumps(diketahui))
             .replace('__JEDA__', str(int(jeda * 1000))).replace('__FORMAT__', FORMAT))
    return skrip, '%s..%s' % (dari, sampai)


def muat():
    if not os.path.exists(JURNAL_FILE):
        return pd.DataFrame(columns=KOLOM)
    teks = ('tanggal_catat', 'kejadian', 'aturan', 'stock', 'umum', 'efektif', 'grup', 'kriteria',
            'no_pengumuman', 't0', 'status', 'dinilai')
    j = pd.read_csv(JURNAL_FILE, dtype={k: object for k in teks}, keep_default_na=False, na_values=[''])
    return j[KOLOM]


def _catat_dari(pengumuman, j):
    """Kejadian masuk dari kumpulan pengumuman yang belum ada di jurnal."""
    hari = hari_ini().strftime('%Y-%m-%d')
    kal = hari_bursa()
    ada = set(zip(j['stock'], j['efektif'])) if len(j) else set()
    calon = []
    for kunci, p in pengumuman.items():
        efektif, baris = urai(p.get('teks'))
        if efektif is None:
            continue
        umum = pd.Timestamp(str(p.get('tgl') or '')[:10])
        for b in baris:
            if b['jenis'] == 'M':
                calon.append((umum, efektif, b, p.get('no') or kunci.split('|')[0]))
    # paling awal menang: KOREKSI belakangan untuk kejadian sama tidak dobel
    calon.sort(key=lambda c: (c[0], c[3]))
    baru = []
    for umum, efektif, b, no in calon:
        kunci = (b['stock'], efektif.strftime('%Y-%m-%d'))
        if kunci in ada:
            continue
        ada.add(kunci)
        g = grup(b['kr'])
        awal = int(umum <= BATAS_AWAL)
        i0 = kal.searchsorted(efektif, side='left')
        telat = max(0, int(len(kal) - 1 - i0)) if len(kal) and i0 < len(kal) else 0
        baru.append({
            'tanggal_catat': hari, 'kejadian': '%s %s masuk Pemantauan Khusus (kriteria %s)'
                                               % (g, b['stock'], '.'.join(map(str, sorted(b['kr'])))),
            'aturan': '%s | %s' % (VERSI, KLAIM.get(g, 'bukan klaim, dicatat saja')),
            'awal': awal, 'stock': b['stock'], 'umum': umum.strftime('%Y-%m-%d'),
            'efektif': kunci[1], 'grup': g, 'kriteria': '.'.join(map(str, sorted(b['kr']))),
            'no_pengumuman': no, 'telat_hb': telat, 'status': 'awal' if awal else 'menunggu'})
    if baru:
        j = pd.concat([j, pd.DataFrame(baru)], ignore_index=True)[KOLOM]
    return j, baru


def impor_browser(raw):
    """Impor file hasil skrip_browser(). Ringkasan {'ok', 'log'} seperti menu lain."""
    try:
        payload = json.loads(raw.decode('utf-8-sig') if isinstance(raw, bytes) else raw)
    except (ValueError, UnicodeDecodeError) as exc:
        return {'ok': False, 'log': ['File bukan JSON yang valid: %s' % exc]}
    if not isinstance(payload, dict) or payload.get('format') != FORMAT:
        return {'ok': False, 'log': ['Bukan file Pemantauan Khusus dari skrip menu ini.']}
    try:
        j = muat()
    except Exception as exc:
        return {'ok': False, 'log': ['pk_jurnal.csv tidak terbaca, tidak menulis apa pun: %s' % exc]}

    os.makedirs(DIR_MAJU, exist_ok=True)
    simpan = _pengumuman()
    baru_p, tak_terbaca = {}, []
    for p in payload.get('data') or []:
        kunci = str(p.get('kunci') or '')
        if not kunci.startswith('Peng-PK-') or kunci in simpan:
            continue
        p = {k: p.get(k) for k in ('no', 'judul', 'tgl', 'url', 'teks')}
        p['diimpor'] = hari_ini().strftime('%Y-%m-%d')
        efektif, baris = urai(p['teks'])
        if efektif is None or not baris:
            tak_terbaca.append(p['no'])
        p['n_baris'] = len(baris)
        baru_p[kunci] = p
    simpan.update(baru_p)
    tmp = PENGUMUMAN_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(simpan, fh, ensure_ascii=False, indent=0)
    os.replace(tmp, PENGUMUMAN_FILE)

    j, baru = _catat_dari(baru_p, j)
    if len(j):
        tulis_atomik(j[KOLOM], JURNAL_FILE)
    lengkap = bool(payload.get('lengkap'))
    log = _impor_log()
    log = pd.concat([log, pd.DataFrame([{
        'diimpor': time.strftime('%Y-%m-%d %H:%M'), 'diambil': payload.get('diambil'),
        'dari': str(payload.get('dari')), 'sampai': str(payload.get('sampai')),
        'lengkap': '1' if lengkap else '0', 'n_pdf': len(baru_p), 'n_baru': len(baru)}])], ignore_index=True)
    tulis_atomik(log, IMPOR_FILE)

    maju = [b for b in baru if not b['awal']]
    hasil = ['ok   %d PDF Peng-PK baru, %d kejadian masuk baru (%d maju, %d awal=1)'
             % (len(baru_p), len(baru), len(maju), len(baru) - len(maju))]
    for b in maju:
        hasil.append('     %s  efektif %s  %s' % (b['stock'], b['efektif'], b['grup']))
    if tak_terbaca:
        hasil.append('!!   %d PDF tidak terurai (cek manual): %s' % (len(tak_terbaca), ', '.join(tak_terbaca[:10])))
    if payload.get('gagal'):
        hasil.append('--   %d PDF gagal di browser; ambil skrip baru untuk menyapu sisanya' % len(payload['gagal']))
    if not lengkap:
        hasil.append('--   tarikan tidak lengkap (dihentikan/ditolak) -- rentang ini akan ditarik ulang di skrip berikutnya')
    return {'ok': True, 'log': hasil}


# ---------------------------------------------------------------------------
# MENILAI (rumus = kalender_bursa._maju + saringan loncatan pemantauan_khusus)
# ---------------------------------------------------------------------------
def nilai(j, close=None):
    hari = hari_bursa()
    if not len(j) or not len(hari):
        return 0
    perlu = [i for i, r in j.iterrows()
             if not int(r['awal']) and r['status'] not in SELESAI
             and pd.Timestamp(r['efektif']) <= hari[-1]]
    if not perlu:
        return 0
    if close is None:
        close = panel_close()
    lr = np.log(close)
    idx = close.index
    n = len(idx)
    pasar = {h: (lr.shift(-h) - lr).mean(axis=1).to_numpy() for h in HORIZON}
    r_abs = close.pct_change().abs()
    stamp = hari_ini().strftime('%Y-%m-%d')
    berubah = 0
    for i in perlu:
        e = j.loc[i]
        ef, s_ = pd.Timestamp(e['efektif']), e['stock']
        k = idx.searchsorted(ef, side='left')
        if k >= n:
            continue
        upd = {'t0': idx[k].strftime('%Y-%m-%d')}
        if (idx[k] - ef).days > 7:
            upd['status'] = 'dibuang_tanggal'
        elif s_ not in close.columns or not np.isfinite(lr[s_].iloc[k]):
            if k + max(HORIZON) < n:
                upd['status'] = 'dibuang_harga'
        else:
            s = lr[s_].to_numpy()
            upd['hari_h'] = num(s[k] - s[k - 1]) if k >= 1 else np.nan
            for h in HORIZON:
                if k + h < n and np.isfinite(s[k + h]):
                    upd['x%d' % h] = num(s[k + h] - s[k] - pasar[h][k])
            upd['status'] = 'matang' if k + max(HORIZON) < n else 'sebagian'
            if (r_abs[s_].iloc[max(0, k - 1):k + 21] > LONCAT).any():
                upd['status'] = 'dibuang_loncat'
        lama = {c: j.at[i, c] for c in upd}
        if any(str(lama[c]) != str(v) for c, v in upd.items()):
            for c, v in upd.items():
                j.at[i, c] = v
            j.at[i, 'dinilai'] = stamp
            berubah += 1
    return berubah


def jalankan():
    """Tugas harian kesehatan: nilai kejadian yang jendelanya lewat. Pencatatan
    terjadi saat impor (data IDX cuma bisa lewat browser)."""
    j = muat()
    n = nilai(j)
    if n:
        tulis_atomik(j[KOLOM], JURNAL_FILE)
    return {'dinilai': n, 'baris': len(j)}


def ringkas(j=None):
    j = muat() if j is None else j
    j = j[j['awal'].astype(int) == 0] if len(j) else j
    rows = []
    for g in ('Mfund', 'M10', 'Mharga', 'Mlain'):
        x = j[j['grup'] == g] if len(j) else j
        mt = x[x['status'] == 'matang'] if len(x) else x
        r = {'kelompok': g, 'tercatat': len(x), 'matang': len(mt)}
        for h in HORIZON:
            v = pd.to_numeric(mt['x%d' % h], errors='coerce').dropna() if len(mt) else pd.Series(dtype=float)
            r['x%d %%' % h] = round((np.exp(v.mean()) - 1) * 100, 2) if len(v) else None
            r['negatif x%d %%' % h] = round((v < 0).mean() * 100, 1) if len(v) else None
        if g in KALIBRASI:
            r['kalibrasi x5 %'], r['kalibrasi x20 %'] = KALIBRASI[g]['x5'], KALIBRASI[g]['x20']
        rows.append(r)
    return pd.DataFrame(rows).set_index('kelompok')


def periksa():
    try:
        j = muat()
    except Exception as exc:
        return ['pk_jurnal.csv tidak terbaca: %s' % exc]
    masalah = []
    log = _impor_log()
    ok = log[log['lengkap'] == '1'] if len(log) else log
    if not len(ok):
        masalah.append('Jurnal Pemantauan Khusus belum pernah diimpor -- jalankan skrip di '
                       '/perbarui-kepemilikan (kartu Pemantauan Khusus)')
    else:
        akhir = pd.Timestamp(ok['sampai'].max())
        umur = (hari_ini() - akhir).days
        if umur > IMPOR_BASI:
            masalah.append('Jurnal Pemantauan Khusus: pengumuman IDX terakhir ditarik s.d. %s (%d hari lalu) '
                           '-- jalankan skrip di /perbarui-kepemilikan' % (akhir.strftime('%Y-%m-%d'), umur))
    tak = [p['no'] for p in _pengumuman().values() if not p.get('n_baris')]
    if tak:
        masalah.append('Jurnal Pemantauan Khusus: %d PDF Peng-PK tidak terurai (%s) -- cek manual, '
                       'mungkin format tabel IDX berubah' % (len(tak), ', '.join(tak[:5])))
    return masalah


if __name__ == '__main__':
    perintah = sys.argv[1] if len(sys.argv) > 1 else ''
    if perintah == 'skrip':
        skrip, rentang = skrip_browser()
        sys.stderr.write('rentang %s\n' % rentang)
        print(skrip)
    elif perintah == 'impor':
        with open(sys.argv[2], 'rb') as fh:
            print('\n'.join(impor_browser(fh.read())['log']))
    else:
        h = jalankan()
        print('dinilai: %d baris berubah, total %d baris' % (h['dinilai'], h['baris']))
        pd.set_option('display.width', 200)
        print(ringkas().to_string())
        for m in periksa():
            print('MASALAH:', m)
