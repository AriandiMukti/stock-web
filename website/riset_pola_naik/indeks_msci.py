"""
Rebalancing indeks MSCI: saham Indonesia yang masuk / keluar MSCI Standard
dan Small Cap -- adakah arus paksa dana pasif yang bisa didahului atau
"dibalik" sesudahnya?

DATA
  Daftar perubahan konstituen tiap review (Feb/Mei/Agu/Nov) dari
  app2.msci.com/eqb/gimi/{stdindex,smallcap}/MSCI_<Bln><yy>_{ST,SC}PublicList.pdf,
  Feb 2012 - Agu 2026 (118 PDF, diunduh 18 Okt 2026 ke research_cache/msci/).
  Tiap PDF: tanggal pengumuman ("Geneva, <tgl>") dan tanggal efektif ("as of
  the close of <tgl>"). Bagian "MSCI INDONESIA INDEX": kolom Additions (x~28)
  dan Deletions (x~220). Nama MSCI -> ticker lewat PETA di bawah (ditulis
  tangan; nama ambigu "BANK PEMBANGUNAN DAERAH..." (BJBR/BJTM) dan "NUSANTARA
  PROPERTI INTL" dibuang).

DESAIN (didaftar SEBELUM hasil dilihat, 18 Okt 2026)
  Pengumuman MSCI keluar malam WIB (setelah tutup Eropa/AS) -> hari reaksi
  pertama D1 = hari bursa BEI pertama SETELAH tanggal pengumuman. Dana pasif
  berdagang di close tanggal efektif E.
  Kelompok per emiten-review:
     ST_naik    masuk MSCI Standard (baru, atau naik dari Small Cap)
     ST_turun   keluar dari Standard (termasuk turun ke Small Cap)
     SC_masuk   masuk Small Cap, bukan turunan dari Standard
     SC_keluar  keluar Small Cap, bukan naik ke Standard
  Jendela (selisih log vs rata-rata semua emiten tanggal sama):
     D1     gerak hari D1 (reaksi pengumuman -- tak bisa diambil, informasi)
     jalan  close D1 -> close E (BISA diambil: beli/jual setelah reaksi)
     balik5 / balik20  close E -> close E+5 / E+20 (pembalikan sesudah arus)
  Dua periode: review 2012-2019 vs 2020-2026; t klaster per review.
  LOLOS kalau jendela "jalan" atau "balik20": tanda sama dua periode
  (n >= 15 tiap periode) DAN |t| gabungan >= 2. Untuk dipakai beli harus
  > +0,4% (biaya pulang-pergi).

HASIL (18 Okt 2026, 415 emiten-review dari 50 review, 361 terukur): efek
indeks klasik, LOLOS di keempat kelompok, tahan kontrol momentum (pembanding
desil ret120 yang sama):
                 D1      jalan D1->E (median 11 hb)    balik E->E+20
  ST_naik  34  +3,0%    +4,2% (med +3,6, win 71%)     -6,2% (win 32%)
  ST_turun 50  -4,5%    -7,8% (med -5,4, win 24%)     +6,7% (med +4,8, win 72%)
  SC_masuk 121 +3,0%    +3,6% TAPI 2020-26 cuma +1,0  -4,2% (dua periode)
  SC_keluar156 -1,5%    -10,6% (med -9,1, win 15%)    +3,1% (2020-26 +2,6, t lemah)
  Bacaan: setelah pengumuman MSCI, arah ke tanggal efektif masih bisa diambil
  (ST_naik net biaya ~+3,8%), lalu berbalik sesudah dana pasif selesai
  berdagang. ST_turun -> beli di close E paling bersih (n 50, 1 hilang).
  Batas: ST n kecil (34/50); 25 SC_keluar & 24 SC_masuk tanpa data harga
  (kebanyakan delisting/suspensi) -> "balik" SC_keluar kemungkinan terlalu
  bagus; review 2012-2026 cuma 50 -> belum ada uji maju.

JURNAL MAJU: website/msci_jurnal.py (sejak 18 Okt 2026, aturan sama, review
Nov26 dst., PDF baru di research_cache/msci/maju/ -- set kalibrasi di atas
tidak berubah). Diuji setara dengan ukur(): 361/361 kejadian, selisih < 1e-6.

PEMAKAIAN: python -m website.riset_pola_naik.indeks_msci
"""
import glob
import os
import re

import numpy as np
import pandas as pd

from . import kalender_bursa as KB
from . import uji as U

DIR = os.path.join(KB.RESEARCH_CACHE, 'msci')
BELAH = pd.Timestamp('2020-01-01')

PETA = {
    'ABM INVESTAMA TBK': 'ABMM', 'ACE HARDWARE INDONESIA': 'ACES', 'ADARO ANDALAN INDONESIA': 'AADI',
    'ADARO MINERALS INDONESIA': 'ADMR', 'ADHI KARYA TBK': 'ADHI', 'ADI SARANA ARMADA': 'ASSA',
    'AGIS': 'TMPI', 'AGUNG PODOMORO LAND': 'APLN', 'AKR CORPORINDO': 'AKRA', 'ALAM SUTERA REALTY': 'ASRI',
    'ALAMTRI RES INDONESIA': 'ADRO', 'ALFA ENERGI INVESTAMA': 'FIRE', 'AMMAN MINERAL INTL': 'AMMN',
    'ANEKA TAMBANG': 'ANTM', 'ARWANA CITRAMULIA TBK PT': 'ARNA', 'ASAHIMAS FLAT GLASS': 'AMFG',
    'ASPIRASI HIDUP INDONESIA': 'ACES', 'ASTRA AGRO LESTARI': 'AALI', 'ASTRA OTOPARTS': 'AUTO',
    'ASTRINDO NUSANTRA INFRA': 'BIPI', 'AVIA AVIAN': 'AVIA', 'BAKRIE & BROTHERS': 'BNBR',
    'BAKRIE SUMATERA PLANTATI': 'UNSP', 'BAKRIE TELECOM': 'BTEL', 'BAKRIELAND DEV': 'ELTY',
    'BANK ALADIN SYARIAH': 'BANK', 'BANK BRISYARIAH': 'BRIS', 'BANK BTPN SYARIAH': 'BTPS',
    'BANK BUKOPIN': 'BBKP', 'BANK JAGO': 'ARTO', 'BANK KB BUKOPIN': 'BBKP', 'BANK NEO COMMERCE': 'BBYB',
    'BANK SYARIAH INDONESIA': 'BRIS', 'BANK TABUNGAN NEGARA': 'BBTN', 'BANK TABUNGAN PEN. NASIO': 'BTPN',
    'BARITO PACIFIC': 'BRPT', 'BARITO RENEWABLES ENERGY': 'BREN', 'BEKASI FAJAR INDL EST': 'BEST',
    'BEKASI FAJAR INDUS ESTA': 'BEST', 'BENAKAT PETR ENERGY': 'BIPI', 'BERKAH BETON SADAYA': 'BEBS',
    'BERLIAN LAJU TANKER': 'BLTA', 'BFI FINANCE INDONESIA': 'BFIN', 'BINTANG OTO GLOBAL': 'BOGA',
    'BISI INTERNATIONAL': 'BISI', 'BISI INTL': 'BISI', 'BLUE BIRD': 'BIRD', 'BORNEO LUMBUNG ENERGI': 'BORN',
    'BUANA LISTYA TAMA': 'BULL', 'BUKALAPAK.COM': 'BUKA', 'BUKIT ASAM': 'PTBA', 'BUMI RESOURCES': 'BUMI',
    'BUMI RESOURCES MINERALS': 'BRMS', 'BUMI SERPONG DAMAI': 'BSDE', 'CENTRAL OMEGA RES TBK': 'DKFT',
    'CHANDRA ASRI PACIFIC': 'TPIA', 'CHAROEN POKPHAND INDO': 'CPIN', 'CIPUTRA PROPERTY': 'CTRP',
    'CIPUTRA SURYA': 'CTRS', 'CISARUA MOUNTAIN DAIRY': 'CMRY', 'CITRA MARGA NUSAPHALA': 'CMNP',
    'CLIPAN FINANCE INDO': 'CFIN', 'DARMA HENWA': 'DEWA', 'DAYAMITRA TELEKOMUNIKASI': 'MTEL',
    'DELTA DUNIA MAKMUR': 'DOID', 'DHARMA SATYA NUSANTARA': 'DSNG', 'DIAN SWASTATIKA SENTOSA': 'DSSA',
    'DIGITAL MEDIATAMA MAXIMA': 'DMMX', 'EAGLE HIGH PLANTATIONS': 'BWPT', 'ELANG MAHKOTA TEKNOLOGI': 'EMTK',
    'ELECTRONIC CITY INDONES': 'ECII', 'ELNUSA PT': 'ELSA', 'ENERGI MEGA PERSADA': 'ENRG',
    'ERAJAYA SWASEMBADA TBK': 'ERAA', 'ESSA INDUSTRIES INDO': 'ESSA', 'EXPLOITASI ENERGI IND': 'CNKO',
    'EXPRESS TRANSINDO UTAMA': 'TAXI', 'FAJAR SURYA WISESA': 'FASW', 'GADING DEVELOPMENT TBK': 'GAMA',
    'GAJAH TUNGGAL': 'GJTL', 'GARUDA INDONESIA': 'GIAA', 'GLOBAL MEDIACOM': 'BMTR',
    'GOLDEN EAGLE ENERGY': 'SMMT', 'GOTO GOJEK TOKOPEDIA': 'GOTO', 'GUDANG GARAM': 'GGRM',
    'HANSON INTERNATIONAL': 'MYRX', 'HARUM ENERGY': 'HRUM', 'HEXINDO ADIPERKASA TBK P': 'HEXA',
    'HM SAMPOERNA': 'HMSP', 'HOLCIM INDONESIA': 'SMCB', 'INDAH KIAT PULP & PAPER': 'INKP',
    'INDIKA ENERGY TBK PT': 'INDY', 'INDO TAMBANGRAYA MEGAH': 'ITMG', 'INDOCEMENT TUNGGAL': 'INTP',
    'INDOFARMA TBK': 'INAF', 'INDOFOOD CBP SUKSES': 'ICBP', 'INDOFOOD CBP SUKSES MAK': 'ICBP',
    'INDOFOOD SUKSES MAKMUR': 'INDF', 'INDOSAT': 'ISAT', 'INDOSIAR KARYA MEDIA': 'IDKM',
    'INDUSTRI JAMU FARMASI': 'SIDO', 'INOVISI INFRACOM': 'INVS', "INT'L NICKEL INDONESIA": 'INCO',
    'INTI AGRI RESOURCES TBK': 'IIKP', 'INTILAND DEVELOPMENT': 'DILD', 'JASA MARGA (PERSERO)': 'JSMR',
    'KALBE FARMA': 'KLBF', 'KAWASAN IND JABABEKA': 'KIJA', 'KRAKATAU STEEL': 'KRAS',
    'KRESNA GRAHA SEKURINDO': 'KREN', 'LINK NET': 'LINK', 'LIPPO CIKARANG': 'LPCK',
    'LIPPO KARAWACI TBK': 'LPKR', 'M CASH INTEGRASI': 'MCAS', 'MALINDO FEEDMILL': 'MAIN',
    'MAP AKTIF ADIPERKASA': 'MAPA', 'MATAHARI DEPARTMENT': 'LPPF', 'MATAHARI PUTRA PRIMA': 'MPPA',
    'MD ENTERTAINMENT': 'FILM', 'MD PICTURES': 'FILM', 'MEDCO ENERGI INTL': 'MEDC',
    'MEDIA NUSANTARA CITRA': 'MNCN', 'MEDIKALOKA HERMINA': 'HEAL', 'MERDEKA BATTERY MATRLS': 'MBMA',
    'MERDEKA COPPER GOLD': 'MDKA', 'METRO HEALTHCARE INDO': 'CARE', 'METRODATA ELECTRONICS': 'MTDL',
    'METROPOLITAN LAND': 'MTLA', 'MIDI UTAMA INDONESIA': 'MIDI', 'MINNA PADI INVESTAMA TBK': 'PADI',
    'MITRA KELUARGA': 'MIKA', 'MITRA PINASTHIKA MUSTIKA': 'MPMX', 'MNC DIGITAL ENTMT': 'MSIN',
    'MNC INVESTAMA': 'BHIT', 'MNC KAPITAL INDONESIA': 'BCAP', 'MNC LAND TBK': 'KPIG',
    'MNC SKY VISION TBK PT': 'MSKY', 'MNC TOURISM INDONESIA': 'KPIG', 'MNC VISION NETWORKS': 'IPTV',
    'MODERNLAND REALTY TBK': 'MDLN', 'MULTIPOLAR CORP': 'MLPL', 'MULTISTRADA ARAH SARANA': 'MASA',
    'NIPPON INDOSARI': 'ROTI', 'NIPPON INDOSARI CORPINDO': 'ROTI', 'NIRVANA DEV TBK': 'NIRO',
    'NIRVANA DEVLOPMENT TBK': 'NIRO', 'NUSANTARA INFRA': 'META', 'NUSANTARA INFRASTRUCTURE': 'META',
    'PABRIK K TJIWI KIMIA': 'TKIM', 'PACIFIC STRATEGIC FINL': 'APIC', 'PAKUWON JATI': 'PWON',
    'PANIN FINANCIAL TBK PT': 'PNLF', 'PELAT TIMAH NUSANTARA': 'NIKL', 'PELAYARAN TAMARIN': 'TAMU',
    'PEMBANGUNAN PERUMAHAN': 'PTPP', 'PERUSAHAAN GAS NEGARA': 'PGAS', 'PETRINDO JAYA KREASI': 'CUAN',
    'PETROSEA': 'PTRO', 'POLYCHEM INDONESIA': 'ADMG', 'POOL ADVISTA INDONESIA': 'POOL',
    'PP LONDON SUMATRA INDONE': 'LSIP', 'PP PROPERTI': 'PPRO', 'PURADELTA LESTARI': 'DMAS',
    'RAHARJA ENERGI CEPU': 'RATU', 'RAMAYANA LESTARI SENTOSA': 'RALS', 'RESOURCE ALAM INDONESIA': 'KKGI',
    'RIMO INTL LESTARI': 'RIMO', 'RUKUN RAHARJA': 'RAJA', 'SALIM IVOMAS PRATAMA': 'SIMP',
    'SAMPOERNA AGRO': 'SGRO', 'SARANA MENARA NUSANTARA': 'TOWR', 'SARIGUNA PRIMATIRTA': 'CLEO',
    'SAWIT SUMBERMAS TBK': 'SSMS', 'SEKAWAN INTIPRATAMA': 'SIAP', 'SELAMAT SEMPURNA': 'SMSM',
    'SEMEN BATURAJA PT': 'SMBR', 'SEMEN INDONESIA': 'SMGR', 'SENTUL CITY': 'BKSL',
    'SIGMAGOLD INTI PERKASA': 'TMPI', 'SILOAM INTL HOSPITALS': 'SILO', 'SILOAM INTNL HOSPITA': 'SILO',
    'SITARA PROPERTINDO': 'TARA', 'SMARTFREN TELECOM': 'FREN', 'SOLUSI SINERGI DIGITAL': 'WIFI',
    'SRI REJEKI ISMAN': 'SRIL', 'SRI REJEKI ISMAN TBK PT': 'SRIL', 'SUGIH ENERGY TBK PT': 'SUGI',
    'SUMBER ALFARIA TRIJAYA': 'AMRT', 'SUMMARECON AGUNG': 'SMRA', 'SURYA CITRA MEDIA': 'SCMA',
    'SURYA ESA PERKASA': 'ESSA', 'SURYA PERMATA ANDALAN': 'NATO', 'SURYA SEMESTA INTERNUSA': 'SSIA',
    'TB BATUBARA BUKIT ASAM': 'PTBA', 'TEMAS TBK': 'TMAS', 'TEMPO SCAN PACIFIC': 'TSPC',
    'TIGA PILAR SEJAHTERA': 'AISA', 'TIMAH': 'TINS', 'TIPHONE MOBILE INDONESIA': 'TELE',
    'TOTAL BANGUN PERSADA': 'TOTL', 'TOTALINDO EKA PERSADA': 'TOPS', 'TOWER BERSAMA INFR': 'TBIG',
    'TOWER BERSAMA INFRA': 'TBIG', 'TRADA ALAM MINERA': 'TRAM', 'TRADA MARITIME': 'TRAM',
    'TRANSCOAL PACIFIC': 'TCPI', 'TRIPUTRA AGRO PERSADA': 'TAPG', 'TUNAS BARU LAMPUNG': 'TBLA',
    'ULTRAJAYA MILK IND & TRD': 'ULTJ', 'UNILEVER INDONESIA': 'UNVR', 'VALE INDONESIA': 'INCO',
    'VISI MEDIA ASIA TBK': 'VIVA', 'WASKITA BETON PRECAST': 'WSBP', 'WASKITA KARYA PERSERO': 'WSKT',
    'WIJAYA KARYA': 'WIKA', 'WIJAYA KARYA BETON': 'WTON', 'XL AXIATA TBK': 'EXCL',
}


def _tgl(s):
    return pd.Timestamp(pd.to_datetime(s.replace(',', ''), format='%B %d %Y'))


def baca_pdf():
    """Satu baris per (review, indeks, sisi, nama). Di-cache ke _perubahan.pkl."""
    cache = os.path.join(DIR, '_perubahan.pkl')
    if os.path.exists(cache):
        return pd.read_pickle(cache)
    rows = []
    for f in sorted(glob.glob(os.path.join(DIR, 'MSCI_*PublicList.pdf'))):
        rows += baca_satu_pdf(f)
    df = pd.DataFrame(rows)
    df.to_pickle(cache)
    return df


def baca_satu_pdf(f):
    """Baris-baris baca_pdf() untuk SATU PDF, tanpa cache. Dipakai juga oleh
    jurnal maju (website/msci_jurnal.py) untuk review baru, supaya cara
    membacanya tidak mungkin beda dengan kalibrasi."""
    import pdfplumber
    rows = []
    nama = os.path.basename(f)
    jenis = nama.split('_')[2][:2]
    with pdfplumber.open(f) as d:
        teks = (d.pages[0].extract_text() or '').replace('\n', ' ')
        umum = _tgl(re.search(r'Geneva,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', teks).group(1))
        efektif = _tgl(re.search(r'as of the close of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', teks).group(1))
        for p in d.pages:
            ws = p.extract_words()
            for k, w in enumerate(ws):
                if not (w['text'] == 'INDONESIA' and k > 0 and ws[k - 1]['text'] == 'MSCI'):
                    continue
                x_judul, top0 = ws[k - 1]['x0'], w['top']
                blok = []
                for v in ws[k + 1:]:
                    if v['text'] == 'MSCI' and abs(v['x0'] - x_judul) < 5 and v['top'] > top0:
                        break
                    blok.append(v)
                ad = [v for v in blok if v['text'] == 'Additions']
                de = [v for v in blok if v['text'] == 'Deletions']
                if not ad:
                    continue
                xa = ad[0]['x0']
                xd = de[0]['x0'] if de else xa + 190
                garis = {}
                for v in blok:
                    if v['top'] <= ad[0]['top'] + 1 or v['x0'] < xa - 5:
                        continue
                    sisi = 'A' if v['x0'] < xd - 5 else 'D'
                    garis.setdefault(round(v['top']), {'A': [], 'D': []})[sisi].append(v['text'])
                for g in garis.values():
                    for sisi in 'AD':
                        if g[sisi]:
                            rows.append({'review': nama[5:10], 'indeks': jenis, 'umum': umum,
                                         'efektif': efektif, 'sisi': sisi, 'nama': ' '.join(g[sisi])})
    return rows


def kejadian():
    df = baca_pdf()
    df = df[df['nama'].isin(PETA)].copy()
    df['stock'] = df['nama'].map(PETA)
    df = df.drop_duplicates(['review', 'indeks', 'sisi', 'stock'])
    ev = []
    for (rv, s), g in df.groupby(['review', 'stock']):
        kode = set(g['indeks'] + g['sisi'])
        if 'STA' in kode:
            grup = 'ST_naik'
        elif 'STD' in kode:
            grup = 'ST_turun'
        elif 'SCA' in kode:
            grup = 'SC_masuk'
        else:
            grup = 'SC_keluar'
        ev.append({'review': rv, 'stock': s, 'grup': grup,
                   'umum': g['umum'].iloc[0], 'efektif': g['efektif'].iloc[0]})
    return pd.DataFrame(ev)


def ukur(close, ev):
    lr = np.log(close)
    idx = close.index
    mk = lr.diff().mean(axis=1).fillna(0).cumsum()     # indeks log pasar bobot sama
    r = close.pct_change().abs()
    out = []
    for e in ev.itertuples():
        if e.stock not in close.columns:
            continue
        i1 = idx.searchsorted(e.umum, side='right')           # hari bursa pertama SETELAH pengumuman
        iE = idx.searchsorted(e.efektif, side='left')
        if i1 >= len(idx) or iE >= len(idx) or iE < i1 or (idx[iE] - e.efektif).days > 5:
            continue
        s = lr[e.stock].to_numpy()
        if not (np.isfinite(s[i1 - 1]) and np.isfinite(s[i1]) and np.isfinite(s[iE])):
            continue
        if (r[e.stock].iloc[i1 - 1:min(len(idx), iE + 21)] > 0.35).any():
            continue                                      # aksi korporasi tak disesuaikan
        m = mk.to_numpy()
        d = {'review': e.review, 'stock': e.stock, 'grup': e.grup, 'tE': idx[iE],
             'D1': (s[i1] - s[i1 - 1]) - (m[i1] - m[i1 - 1]),
             'jalan': (s[iE] - s[i1]) - (m[iE] - m[i1]) if iE > i1 else np.nan,
             'hari_jalan': iE - i1}
        for h in (5, 20):
            j = iE + h
            d['balik%d' % h] = (s[j] - s[iE]) - (m[j] - m[iE]) if j < len(idx) and np.isfinite(s[j]) else np.nan
        out.append(d)
    return pd.DataFrame(out)


def ringkas(d):
    rows = []
    for g in ('ST_naik', 'ST_turun', 'SC_masuk', 'SC_keluar'):
        for nama, m in (('semua', slice(None)), ('2012-19', d['tE'] < BELAH), ('2020-26', d['tE'] >= BELAH)):
            x = d[d['grup'] == g].loc[m] if not isinstance(m, slice) else d[d['grup'] == g]
            x = x[x['grup'] == g]
            r = {'kelompok': '%s %s' % (g, nama), 'n': len(x)}
            for k in ('D1', 'jalan', 'balik5', 'balik20'):
                v = x[k].dropna()
                if len(v) >= 8:
                    r[k + ' %'] = round((np.exp(v.mean()) - 1) * 100, 2)
                    r['t ' + k] = round(U.t_klaster(v, x.loc[v.index, 'review']), 1)
            rows.append(r)
    return pd.DataFrame(rows).set_index('kelompok')


def main():
    ev = kejadian()
    print('kejadian: %d emiten-review dari %d review' % (len(ev), ev['review'].nunique()))
    print(ev['grup'].value_counts().to_string())
    close = KB._panel_close()
    d = ukur(close, ev)
    print('terukur: %d | median hari D1->E: %d' % (len(d), d['hari_jalan'].median()))
    pd.set_option('display.width', 220)
    print(ringkas(d).to_string())

    print('\nKRITERIA (jalan / balik20: tanda sama dua periode, n>=15 tiap periode, |t|>=2):')
    for g in ('ST_naik', 'ST_turun', 'SC_masuk', 'SC_keluar'):
        x = d[d['grup'] == g]
        teks = []
        for k in ('jalan', 'balik20'):
            a, b = x.loc[x['tE'] < BELAH, k].dropna(), x.loc[x['tE'] >= BELAH, k].dropna()
            v = x[k].dropna()
            if len(a) < 15 or len(b) < 15:
                teks.append('%s n kurang (%d/%d)' % (k, len(a), len(b)))
                continue
            t = U.t_klaster(v, x.loc[v.index, 'review'])
            ok = np.sign(a.mean()) == np.sign(b.mean()) and abs(t) >= 2
            teks.append('%s %s (P1 %+.2f%%, P2 %+.2f%%, t %.1f)' % (
                k, 'LOLOS' if ok else 'gagal', (np.exp(a.mean()) - 1) * 100,
                (np.exp(b.mean()) - 1) * 100, t))
        print('  %-10s %s' % (g, ' | '.join(teks)))


if __name__ == '__main__':
    main()
