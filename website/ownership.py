"""
Kepemilikan Saham — komposisi kepemilikan satu emiten, bulan per bulan.

Dua sumber publik, keduanya gratis dan tanpa login:

1. KSEI "Kepemilikan Efek" (Balance Position of Securities), terbit tiap
   akhir bulan sebagai satu file ZIP berisi TXT pipe-delimited:
       https://www.ksei.co.id/storage/Download/BalanceposEfek<YYYYMMDD>.zip
   Isinya SELURUH efek (kurang lebih 3.700 baris, ~500 KB) dengan kolom:
       Date|Code|Type|Sec. Num|Price|<9 kolom Local>|Total|<9 kolom Foreign>|Total
   Sembilan kolom itu adalah tipe investor KSEI: IS (asuransi), CP
   (korporasi), PF (dana pensiun), IB (bank), ID (individu), MF (reksa
   dana), SC (perusahaan efek), FD (yayasan), OT (lain-lain).

   Dari situ semua angka besar di halaman ini bisa dihitung persis --
   diverifikasi terhadap BBRI Agustus 2026: market cap 492.567 M,
   scripless 709.398 ribu lot (46,81% dari saham tercatat), foreign
   56,06%, ritel 22,44%, lokal non-ritel 21,50%. Cocok sampai dua
   desimal dengan angka yang jadi acuan halaman ini.

2. IDX profil perusahaan tercatat, untuk daftar pemegang saham bernama:
       /primary/ListedCompany/GetCompanyProfilesDetail?KodeEmiten=<TICKER>
   Memberi nama, jumlah lembar, persentase, kategori (Lebih dari 5% /
   Masyarakat Warkat / Masyarakat Non Warkat / Direksi / Komisaris /
   Saham Treasury) dan flag pengendali. Ada di balik Cloudflare, jadi
   diakses lewat cloudscraper -- sama seperti scraper Stockbit di
   <external-tools>/BDM\\.

3. IDX keterbukaan informasi -> LBRPE (Laporan Bulanan Registrasi
   Pemegang Efek), PDF per emiten per bulan. Dicari lewat
       /primary/ListedCompany/GetAnnouncement?...&kodeEmiten=<TICKER>
   lalu PDF-nya diparse dengan pdfplumber. Ini satu-satunya sumber gratis
   untuk dua angka yang tidak ada di mana pun lagi:
       "% Saham Free Float"                        -> free float resmi I-A
       "Jumlah Pemegang Saham Nasabah Pemilik SID" -> jumlah pemegang saham
   Diverifikasi terhadap tiga acuan (posisi Juli 2026):
       ADRO  26,79% / 176.474 SID   vs acuan 26,80% / 176.470
       PADI  95,78% /  76.676 SID   vs acuan 95,80% /  76.680
       BBRI  42,54% / 782.991 SID   vs acuan 42,50% / 782.990
   Halaman tetap jalan tanpa LBRPE, hanya dua field itu yang kosong.

DUA BASIS PERSENTASE, jangan sampai tertukar -- ini sumber bug paling
halus di modul ini. Semua angka KSEI dihitung terhadap saham SCRIPLESS
(yang ada di C-BEST), sedangkan persentase pemegang saham dari IDX/LBRPE
dihitung terhadap saham TERCATAT. Untuk emiten yang belum 100% scripless
keduanya beda jauh, jadi konversi lewat to_scripless_basis() wajib
sebelum keduanya dijumlahkan. Terverifikasi: BBRI Foreign Named 1,25%
dari tercatat = 2,67% dari scripless, persis angka 2,7% di acuan.

Yang masih perlu diisi tangan lewat overrides.json:

  * Pemegang saham bernama rentang 1-5%. Registri IDX berhenti di 5%
    (plus direksi/komisaris) dan LBRPE juga, tapi justru rentang inilah
    yang menentukan "Foreign Named" dan carve-out ritel. Lihat
    extra_holders di overrides.json.
  * Nama grup konglomerasi, kalau LBRPE melaporkan pemilik manfaat
    "tidak ada" (ADRO ketebak otomatis jadi "Thohir Group", PADI tidak).
  * Jumlah SID ritel saja, sebagai pembagi rata-rata saham per investor
    ritel. LBRPE hanya memberi total SID termasuk institusi, jadi tanpa
    retail_sid angkanya ~2% lebih rendah daripada acuan.

Pemakaian sebagai script (sekali di awal, lalu tiap awal bulan):

    python -m website.ownership fetch --months 12      # tarik data KSEI
    python -m website.ownership sync ADRO BBRI         # registri IDX + LBRPE
    python -m website.ownership show ADRO              # cek hasilnya
    python -m website.ownership registry-all           # registri semua emiten
    python -m website.ownership lbrpe-all              # LBRPE semua emiten

Semuanya juga bisa dari menu Perbarui Kepemilikan (/perbarui-kepemilikan).
"""
import base64
import io
import json
import os
import random
import re
import sys
import threading
import time
import zipfile
from calendar import monthrange
from collections import deque
from datetime import date, datetime, timedelta

from .config import OWNERSHIP_PATH

KSEI_URL = 'https://www.ksei.co.id/storage/Download/BalanceposEfek{yyyymmdd}.zip'
IDX_DETAIL_URL = ('https://www.idx.co.id/primary/ListedCompany/'
                  'GetCompanyProfilesDetail?KodeEmiten={ticker}&language=id-id')
# Keterbukaan informasi IDX. indexFrom HARUS 0 -- dengan 1 endpoint-nya
# balas ResultCount benar tapi Replies kosong.
IDX_ANNOUNCEMENT_URL = (
    'https://www.idx.co.id/primary/ListedCompany/GetAnnouncement'
    '?indexFrom=0&pageSize={size}&dateFrom={date_from}&dateTo={date_to}'
    '&lang=id&keyword=&kodeEmiten={ticker}&emitenType=s')
LBRPE_TITLE = 'Registrasi Pemegang Efek'

KSEI_DIR = os.path.join(OWNERSHIP_PATH, 'ksei')
IDX_DIR = os.path.join(OWNERSHIP_PATH, 'idx')
LBRPE_DIR = os.path.join(OWNERSHIP_PATH, 'lbrpe')
OVERRIDES_FILE = os.path.join(OWNERSHIP_PATH, 'overrides.json')

# Pemegang saham bernama di bawah ambang ini tidak dikeluarkan dari
# hitungan ritel. Ambangnya mengikuti tabel "Daftar Pemegang Saham >1%"
# yang jadi acuan: individu di bawah 1% dianggap masih ritel.
NAMED_INDIVIDUAL_THRESHOLD = 1.0

# Urutan kolom investor persis seperti di header file KSEI.
INVESTOR_CODES = ['IS', 'CP', 'PF', 'IB', 'ID', 'MF', 'SC', 'FD', 'OT']
INVESTOR_LABELS = {
    'IS': 'Asuransi',
    'CP': 'Korporasi',
    'PF': 'Dana Pensiun',
    'IB': 'Bank',
    'ID': 'Individu',
    'MF': 'Reksa Dana',
    'SC': 'Perusahaan Efek',
    'FD': 'Yayasan',
    'OT': 'Lain-lain',
}

MONTH_ID = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
            'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']


def _scraper():
    """cloudscraper kalau ada (IDX di balik Cloudflare), requests kalau tidak."""
    try:
        import cloudscraper
        return cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    except ImportError:
        import requests
        return requests.Session()


# ---------------------------------------------------------------- KSEI

def ksei_candidate_dates(year, month):
    """
    KSEI memberi tanggal file = hari bursa terakhir bulan itu, yang tidak
    selalu tanggal terakhir kalender (29-Mei-2026, 27-Feb-2026, ...).
    Jadi mundur dari akhir bulan sampai ketemu file yang ada.
    """
    last = monthrange(year, month)[1]
    return [date(year, month, d) for d in range(last, max(last - 9, 0), -1)]


def fetch_ksei_month(year, month, force=False):
    """
    Unduh + parse satu bulan KSEI, simpan ke ksei/<YYYY-MM>.json.
    Mengembalikan path file hasil, atau None kalau bulan itu belum terbit.
    """
    out = os.path.join(KSEI_DIR, '%04d-%02d.json' % (year, month))
    if os.path.exists(out) and not force:
        return out

    session = _scraper()
    for candidate in ksei_candidate_dates(year, month):
        url = KSEI_URL.format(yyyymmdd=candidate.strftime('%Y%m%d'))
        try:
            resp = session.get(url, timeout=90,
                               headers={'User-Agent': 'Mozilla/5.0'})
        except Exception:
            continue
        if resp.status_code != 200 or resp.content[:2] != b'PK':
            continue

        parsed = parse_ksei_zip(resp.content, candidate)
        os.makedirs(KSEI_DIR, exist_ok=True)
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump(parsed, fh, ensure_ascii=False)
        return out
    return None


def parse_ksei_zip(blob, as_of):
    """
    ZIP -> {'as_of': 'YYYY-MM-DD', 'securities': {TICKER: {...}}}.

    Hanya baris Type == EQUITY yang diambil; file yang sama juga memuat
    obligasi, sukuk, ETF dan reksa dana yang tidak relevan di sini.
    """
    archive = zipfile.ZipFile(io.BytesIO(blob))
    name = archive.namelist()[0]
    text = archive.read(name).decode('utf-8', errors='replace')

    def num(raw):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    securities = {}
    for line in text.splitlines()[1:]:
        fields = line.split('|')
        if len(fields) < 25 or fields[2].strip().upper() != 'EQUITY':
            continue
        ticker = fields[1].strip().upper()
        if not ticker:
            continue

        securities[ticker] = {
            'sec_num': num(fields[3]),
            'price': num(fields[4]),
            'local': {code: num(fields[5 + i]) for i, code in enumerate(INVESTOR_CODES)},
            'local_total': num(fields[14]),
            'foreign': {code: num(fields[15 + i]) for i, code in enumerate(INVESTOR_CODES)},
            'foreign_total': num(fields[24]),
        }

    return {'as_of': as_of.isoformat(), 'securities': securities}


_KSEI_MEM = {'sig': None, 'months': []}


def ksei_signature():
    """(nama, mtime, ukuran) tiap berkas bulan KSEI -- berubah begitu ada
    bulan baru ditarik atau berkas lama ditulis ulang. Kunci cache memori
    load_ksei_months() dan scanner.ownership_panel()."""
    if not os.path.isdir(KSEI_DIR):
        return ()
    sig = []
    for name in sorted(os.listdir(KSEI_DIR)):
        if re.fullmatch(r'\d{4}-\d{2}\.json', name):
            st = os.stat(os.path.join(KSEI_DIR, name))
            sig.append((name, st.st_mtime_ns, st.st_size))
    return tuple(sig)


def load_ksei_months():
    """
    Semua bulan KSEI yang sudah tersimpan, terurut lama -> baru.

    Disimpan di memori selama berkasnya tidak berubah: /saham-data
    memanggil ini dua kali per permintaan (build_ownership dan
    ownership_panel), masing-masing ~0,1 detik mem-parse ~4,6 MB JSON yang
    isinya cuma berubah sebulan sekali. Hasilnya DIBAGI antar pemanggil --
    jangan diubah di tempat.
    """
    sig = ksei_signature()
    if sig and sig == _KSEI_MEM['sig']:
        return _KSEI_MEM['months']
    months = _load_ksei_months_disk()
    _KSEI_MEM.update(sig=sig, months=months)
    return months


def _load_ksei_months_disk():
    if not os.path.isdir(KSEI_DIR):
        return []
    months = []
    for name in sorted(os.listdir(KSEI_DIR)):
        if not re.fullmatch(r'\d{4}-\d{2}\.json', name):
            continue
        try:
            with open(os.path.join(KSEI_DIR, name), encoding='utf-8') as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        payload['month'] = name[:-5]
        months.append(payload)
    return months


# ----------------------------------------------------------------- IDX

def fetch_idx_registry(ticker, force=False):
    """
    Tarik daftar pemegang saham + profil dari IDX, simpan snapshot bulanan
    di idx/<YYYY-MM>/<TICKER>.json. Disimpan per bulan supaya perubahan
    komposisi pemegang saham bernama bisa dibandingkan antar bulan
    seiring waktu -- IDX sendiri hanya menyajikan posisi terkini, tidak
    ada arsipnya.
    """
    ticker = re.sub(r'[^A-Z0-9]', '', (ticker or '').upper())[:6]
    if not ticker:
        return None

    stamp = date.today().strftime('%Y-%m')
    folder = os.path.join(IDX_DIR, stamp)
    out = os.path.join(folder, ticker + '.json')
    if os.path.exists(out) and not force:
        return out

    session = _scraper()
    resp = session.get(
        IDX_DETAIL_URL.format(ticker=ticker),
        headers={'Accept': 'application/json',
                 'Referer': 'https://www.idx.co.id/id/perusahaan-tercatat/'
                            'profil-perusahaan-tercatat/' + ticker},
        timeout=60)
    resp.raise_for_status()
    return _simpan_registri(ticker, resp.json(), stamp)


def _simpan_registri(ticker, payload, stamp, fetched_at=None):
    """
    Payload GetCompanyProfilesDetail -> idx/<stamp>/<TICKER>.json. Dipakai
    tarikan langsung maupun impor dari browser, supaya bentuk snapshot-nya
    tidak mungkin beda antara keduanya.
    """
    if not payload.get('PemegangSaham'):
        # IDX kadang membalas profil tanpa daftar pemegang saham (ARKO, Okt
        # 2026: kosong, padahal Sep ada 7 baris). Snapshot kosong akan jadi
        # "terbaru" dan mengosongkan tabel di halaman, jadi jangan disimpan
        # -- snapshot bulan sebelumnya tetap dipakai, dan tarikan berikutnya
        # mencobanya lagi.
        return None
    profiles = payload.get('Profiles') or []
    profile = profiles[0] if profiles else {}
    snapshot = {
        'ticker': ticker,
        'fetched_at': fetched_at or datetime.now().isoformat(timespec='seconds'),
        'name': (profile.get('NamaEmiten') or '').strip(),
        'sector': (profile.get('Sektor') or '').strip(),
        'sub_sector': (profile.get('SubSektor') or '').strip(),
        'board': (profile.get('PapanPencatatan') or '').strip(),
        'holders': payload.get('PemegangSaham') or [],
    }
    folder = os.path.join(IDX_DIR, stamp)
    out = os.path.join(folder, ticker + '.json')
    os.makedirs(folder, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=1)
    return out


def load_idx_registries(ticker):
    """Snapshot IDX untuk satu emiten, terurut lama -> baru."""
    ticker = (ticker or '').upper()
    if not os.path.isdir(IDX_DIR):
        return []
    snapshots = []
    for stamp in sorted(os.listdir(IDX_DIR)):
        candidate = os.path.join(IDX_DIR, stamp, ticker + '.json')
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, encoding='utf-8') as fh:
                snapshot = json.load(fh)
        except (OSError, ValueError):
            continue
        snapshot['month'] = stamp
        snapshots.append(snapshot)
    return snapshots


# --------------------------------------------------------------- LBRPE

def _id_number(raw):
    """'176.474' / '26,79' / '(0,16)' -> float. Format Indonesia."""
    text = (raw or '').strip().strip('()')
    if not text:
        return None
    text = text.replace('.', '').replace(',', '.')
    try:
        return float(text)
    except ValueError:
        return None


_NUM_TOKEN = re.compile(r'\(?-?[\d.]+(?:,\d+)?\)?')


def parse_lbrpe_text(text):
    """
    Ambil angka yang dibutuhkan dari teks LBRPE (Laporan Bulanan
    Registrasi Pemegang Efek).

    Dua field ini tidak ada di sumber lain mana pun yang gratis:

      * "% Saham Free Float" -- free float resmi menurut Peraturan Bursa
        I-A, yang sudah mengeluarkan pengendali, afiliasi pengendali,
        direksi/komisaris, treasury dan saham lock-up. Jauh lebih ketat
        daripada sekadar menjumlah baris "Masyarakat" di registri IDX
        (ADRO: 26,79% resmi vs 40,38% versi registri).
      * "Jumlah Pemegang Saham Nasabah Pemilik SID" -- jumlah pemegang
        saham per emiten. KSEI hanya menerbitkan SID agregat nasional.

    Tata letak PDF-nya tidak konsisten antar Biro Administrasi Efek:
    kadang baris "% Saham Free Float" kebawa jumlah lembarnya juga
    ("% Saham Free Float 602.240.482 7,77"), kadang bersih ("... 26,37
    26,79"). Karena itu yang diambil selalu token angka TERAKHIR di baris
    itu -- itu yang selalu persentase bulan ini.
    """
    lines = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]
    result = {'free_float': None, 'sid': None, 'sid_prev': None,
              'listed_shares': None, 'free_float_shares': None,
              'period': None, 'beneficial_owners': []}

    for index, line in enumerate(lines):
        if line.startswith('% Saham Free Float'):
            tokens = _NUM_TOKEN.findall(line)
            if tokens:
                value = _id_number(tokens[-1])
                # Beberapa BAE salah isi baris ini -- jumlah lembar
                # tertulis ulang di situ, bukan persentasenya (ditemukan
                # di LBRPE JECX Juli 2026: "% Saham Free Float
                # 975.662.703", tanpa angka persen sama sekali di baris
                # itu). Token terakhir jadi 975 juta, bukan 0-100. Sebuah
                # persentase yang mustahil lebih baik ditolak jadi None
                # daripada disimpan mentah dan tampil sebagai "975662703%"
                # di halaman.
                if value is not None and 0 <= value <= 100:
                    result['free_float'] = value

        elif line.startswith('Jumlah saham Free Float'):
            tokens = _NUM_TOKEN.findall(line)
            if tokens:
                result['free_float_shares'] = _id_number(tokens[-1])

        elif line.startswith('Jumlah saham tercatat di Bursa'):
            tokens = _NUM_TOKEN.findall(line)
            if tokens:
                result['listed_shares'] = _id_number(tokens[-1])

        elif 'Pemilik SID' in line:
            # Header, lalu baris "Bulan Sebelumnya Bulan Sekarang Perubahan",
            # lalu baris angkanya. Dicari sampai 4 baris ke depan supaya
            # tahan kalau header-nya terpecah dua baris.
            for probe in lines[index + 1:index + 5]:
                tokens = _NUM_TOKEN.findall(probe)
                values = [_id_number(t) for t in tokens]
                values = [v for v in values if v is not None]
                if len(values) >= 2:
                    result['sid_prev'] = values[0]
                    result['sid'] = values[1]
                    break

        elif 'berakhir pada' in line:
            # "... berakhir pada akhir bulan Juli -" lalu baris berikutnya
            # "2026 Sebagai Berikut :" -- tahunnya kebawa ke baris lain,
            # jadi disambung balik supaya periodenya utuh.
            period = line.split('berakhir pada', 1)[1].strip(' :-')
            following = lines[index + 1] if index + 1 < len(lines) else ''
            year = re.match(r'^(\d{4})\b', following)
            if year and not re.search(r'\d{4}', period):
                period = '%s %s' % (period, year.group(1))
            result['period'] = period.strip()

        # Pemilik manfaat: "1 Garibaldi Thohir Jakarta, Indonesia Ya 6,863 %"
        # Nama ditangkap greedy supaya nama lengkap ikut -- kalau lazy,
        # "Christian Ariano Rachmat" terpotong jadi "Christian" saja, dan
        # marga itulah yang dipakai konglo_from_owners().
        owner = re.match(r'^\d+\s+(.+)\s+([A-Z][\w .\'-]*),\s*([A-Za-z ]+?)\s+'
                         r'(Ya|Tidak)\b\s*([\d.,]*)\s*%?$', line)
        if owner:
            name = owner.group(1).strip()
            if name.lower() not in ('tidak ada', 'nama pemilik manfaat'):
                result['beneficial_owners'].append(
                    {'name': name, 'pct': _id_number(owner.group(5))})

    return result


def fetch_lbrpe(ticker, force=False):
    """
    Cari LBRPE terbaru satu emiten di keterbukaan informasi IDX, unduh
    PDF-nya, parse, simpan ke lbrpe/<YYYY-MM>/<TICKER>.json.

    LBRPE dilaporkan awal bulan untuk posisi akhir bulan sebelumnya, jadi
    dicari 4 bulan ke belakang -- cukup untuk menembus emiten yang
    terlambat lapor tanpa memindai arsip bertahun-tahun.
    """
    ticker = re.sub(r'[^A-Z0-9]', '', (ticker or '').upper())[:6]
    if not ticker:
        return None

    stamp = date.today().strftime('%Y-%m')
    folder = os.path.join(LBRPE_DIR, stamp)
    out = os.path.join(folder, ticker + '.json')
    if os.path.exists(out) and not force:
        return out

    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError('LBRPE butuh pdfplumber: pip install pdfplumber')

    today = date.today()
    start = today.replace(day=1)
    for _ in range(4):
        start = (start - timedelta(days=1)).replace(day=1)

    session = _scraper()
    headers = {'Accept': 'application/json',
               'Referer': 'https://www.idx.co.id/id/perusahaan-tercatat/'
                          'keterbukaan-informasi/'}
    listing = session.get(
        IDX_ANNOUNCEMENT_URL.format(size=60, ticker=ticker,
                                    date_from=start.strftime('%Y%m%d'),
                                    date_to=today.strftime('%Y%m%d')),
        headers=headers, timeout=60)
    listing.raise_for_status()

    replies = listing.json().get('Replies') or []
    # Terbaru lebih dulu; ambil yang pertama cocok. Lampiran (IsAttachment
    # True) adalah scan DPS dari BAE yang formatnya beda-beda -- yang
    # dipakai selalu dokumen utamanya.
    for reply in replies:
        title = (reply.get('pengumuman') or {}).get('JudulPengumuman') or ''
        if LBRPE_TITLE not in title:
            continue
        for attachment in reply.get('attachments') or []:
            if attachment.get('IsAttachment'):
                continue
            url = attachment.get('FullSavePath')
            if not url:
                continue
            pdf = session.get(url, headers={'Referer': 'https://www.idx.co.id/'},
                              timeout=120)
            if pdf.status_code != 200:
                continue
            hasil = _simpan_lbrpe(ticker, pdf.content,
                                  reply['pengumuman'].get('TglPengumuman') or '', url, stamp)
            if hasil:
                return hasil
    return None


def _simpan_lbrpe(ticker, pdf_bytes, announced_at, url, stamp, fetched_at=None):
    """
    Parse satu PDF LBRPE dan simpan ke lbrpe/<stamp>/<TICKER>.json. None
    kalau bukan PDF atau dua angka utamanya tidak terbaca. Dipakai tarikan
    langsung maupun impor dari browser, jadi parsernya cuma satu.
    """
    parsed = parse_pdf_lbrpe(pdf_bytes)
    if parsed is None:
        return None
    return _tulis_lbrpe(ticker, parsed, announced_at, url, stamp, fetched_at)


# Halaman pertama bagian Bahasa Inggris LBRPE selalu bertuliskan ini (ada
# di 880/880 PDF Okt 2026). parse_lbrpe_text() cuma memakai label Bahasa
# Indonesia, jadi bagian Inggris -- separuh PDF -- tidak perlu dibaca.
# Diuji pada 880 PDF: hasil parse identik dengan membaca seluruh halaman,
# waktu baca turun 1,65 -> 0,92 detik per PDF.
PENANDA_BAGIAN_INGGRIS = 'Go To Indonesian Page'


def parse_pdf_lbrpe(pdf_bytes):
    """
    PDF LBRPE -> dict parse_lbrpe_text(), atau None kalau bukan PDF atau
    free float & SID dua-duanya tidak terbaca. Fungsi murni tanpa tulis
    berkas, supaya bisa dijalankan di proses pekerja (impor paralel).
    """
    if pdf_bytes[:4] != b'%PDF':
        return None
    import pdfplumber
    halaman = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
        for i, page in enumerate(doc.pages):
            teks = page.extract_text() or ''
            if i > 0 and PENANDA_BAGIAN_INGGRIS in teks:
                break
            halaman.append(teks)

    parsed = parse_lbrpe_text('\n'.join(halaman))
    if parsed['free_float'] is None and parsed['sid'] is None:
        return None
    return parsed


def _tulis_lbrpe(ticker, parsed, announced_at, url, stamp, fetched_at=None):
    parsed = dict(parsed)
    parsed.update({
        'ticker': ticker,
        'announced_at': announced_at or '',
        'source_url': url,
        'fetched_at': fetched_at or datetime.now().isoformat(timespec='seconds'),
    })
    folder = os.path.join(LBRPE_DIR, stamp)
    out = os.path.join(folder, ticker + '.json')
    os.makedirs(folder, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(parsed, fh, ensure_ascii=False, indent=1)
    return out


def load_lbrpe(ticker):
    """LBRPE tersimpan paling baru untuk satu emiten, atau None."""
    ticker = (ticker or '').upper()
    if not os.path.isdir(LBRPE_DIR):
        return None
    for stamp in sorted(os.listdir(LBRPE_DIR), reverse=True):
        candidate = os.path.join(LBRPE_DIR, stamp, ticker + '.json')
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, encoding='utf-8') as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        payload['month'] = stamp
        return payload
    return None


# ----------------------------------------------------------- overrides

def load_overrides():
    """
    Koreksi manual untuk hal yang tidak diterbitkan sumber publik.

    Bentuknya:
        {
          "BBRI": {
            "sid": 782990,                      # jumlah pemegang saham
            "konglo": "Danantara",
            "foreign_names": ["Employees Provident Fund Board"],
            "local_names":   ["PT Danantara Asset Management"]
          }
        }

    foreign_names / local_names hanya dipakai untuk MENIMPA tebakan
    heuristik nasionalitas di daftar pemegang saham bernama.
    """
    try:
        with open(OVERRIDES_FILE, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


# Badan hukum Indonesia di registri IDX praktis selalu berawalan "PT"
# atau "Perusahaan Perseroan"; entitas asing datang dengan akhiran
# hukum negaranya. Itu yang dipakai untuk menebak, dan hasilnya selalu
# ditandai sebagai tebakan di UI -- bukan fakta dari sumber.
_FOREIGN_MARKERS = re.compile(
    r'\b(pte|ltd|limited|plc|inc|incorporated|corp|corporation|n\.?v|b\.?v|'
    r'gmbh|s\.?a|sarl|llc|llp|holdings?|group|international|investments?|'
    r'capital|partners|fund|funds|asset management|provident|authority|'
    r'pension|sdn|bhd|co\.,?\s*ltd|company limited)\b',
    re.IGNORECASE)
_LOCAL_PREFIX = re.compile(r'^\s*(pt\b|perusahaan\s+perseroan|perum\b|'
                           r'republik\s+indonesia|negara\s+republik|koperasi\b)',
                           re.IGNORECASE)


def classify_nationality(name, category='', override=None):
    """
    Golongkan satu baris registri IDX jadi salah satu dari:

        'public'   baris agregat, bukan pemegang saham bernama
                   (Masyarakat Warkat / Non Warkat / Saham Treasury)
        'person'   orang perorangan -- direksi & komisaris
        'local'    badan hukum Indonesia
        'foreign'  badan hukum asing
        'unknown'  badan hukum yang tidak bisa ditebak

    Kategori dicek lebih dulu karena itu data dari IDX, bukan tebakan;
    heuristik nama hanya dipakai untuk baris yang tersisa. Cuma 'foreign'
    yang masuk hitungan "Foreign Named", dan cuma 'person' yang masuk
    carve-out ritel (named_individual_rows), jadi salah tebak di sini
    berpengaruh langsung ke angka di halaman -- karena itu bisa ditimpa
    lewat overrides.json.

    Kategori resmi IDX cuma menandai Direksi/Komisaris sebagai perorangan.
    Pemegang saham individu >5% yang BUKAN pengurus -- ahli waris,
    keluarga pendiri -- tidak punya kategori yang membedakannya dari
    badan hukum, dan namanya (nama orang biasa, tanpa "PT" atau penanda
    badan hukum asing) akan jatuh ke 'unknown', bukan 'person'. Contoh
    nyata: JECX punya dua pemegang bernama "Rayyan Farrel Wardhana
    Istiantoro" dan "Nabill Wardhana Istiantoro", 8,9% masing-masing,
    marga sama -- jelas perorangan tapi kategori IDX-nya cuma "Lebih dari
    5%". person_names di overrides.json menutup celah ini.
    """
    clean = (name or '').strip()
    if not clean:
        return 'unknown'

    override = override or {}
    lowered = clean.lower()
    for entry in override.get('foreign_names', []):
        if entry.strip().lower() == lowered:
            return 'foreign'
    for entry in override.get('local_names', []):
        if entry.strip().lower() == lowered:
            return 'local'
    for entry in override.get('person_names', []):
        if entry.strip().lower() == lowered:
            return 'person'

    kategori = (category or '').lower()
    if 'masyarakat' in kategori or 'treasury' in kategori:
        return 'public'
    if 'direksi' in kategori or 'komisaris' in kategori:
        return 'person'

    if _LOCAL_PREFIX.search(clean):
        return 'local'
    if _FOREIGN_MARKERS.search(clean):
        return 'foreign'
    return 'unknown'


# ------------------------------------------------------------ perhitungan

def _pct(part, whole):
    return (part / whole * 100.0) if whole else 0.0


def month_label(stamp):
    """'2026-08' -> 'Agu 26'."""
    try:
        year, month = stamp.split('-')
        return '%s %s' % (MONTH_ID[int(month)], year[2:])
    except (ValueError, IndexError):
        return stamp


def build_month_metrics(record):
    """
    Satu baris KSEI -> semua angka turunan yang dipakai halaman.

    Rumusnya sengaja eksplisit karena inilah yang diverifikasi terhadap
    angka acuan BBRI:
        scripless  = local_total + foreign_total   (saham yang ada di C-BEST)
        ribu lot   = scripless / 100 lembar / 1.000
        % foreign  = foreign_total / scripless     (BUKAN / sec_num)
        % ritel    = local ID / scripless
    Pembaginya scripless, bukan saham tercatat, karena KSEI hanya
    "melihat" saham yang tercatat elektronik; saham warkat tidak punya
    rincian tipe investor sama sekali.
    """
    local = record.get('local') or {}
    foreign = record.get('foreign') or {}
    local_total = record.get('local_total') or 0.0
    foreign_total = record.get('foreign_total') or 0.0
    sec_num = record.get('sec_num') or 0.0
    price = record.get('price') or 0.0

    scripless = local_total + foreign_total
    retail = local.get('ID', 0.0)

    return {
        'sec_num': sec_num,
        'price': price,
        'market_cap': sec_num * price,
        'scripless': scripless,
        'scripless_ribu_lot': scripless / 100.0 / 1000.0,
        'scripless_pct_of_listed': _pct(scripless, sec_num),
        'local_total': local_total,
        'foreign_total': foreign_total,
        'retail_shares': retail,
        'pct_foreign': _pct(foreign_total, scripless),
        'pct_retail': _pct(retail, scripless),
        'pct_local_non_retail': _pct(local_total - retail, scripless),
        'local': local,
        'foreign': foreign,
        'local_pct': {code: _pct(local.get(code, 0.0), scripless) for code in INVESTOR_CODES},
        'foreign_pct': {code: _pct(foreign.get(code, 0.0), scripless) for code in INVESTOR_CODES},
    }


def _extra_holder_rows(overrides, latest_metrics, existing_names):
    """
    Pemegang saham bernama yang ditambahkan manual lewat overrides.json.

    Registri IDX hanya memuat pemegang >=5%, treasury, agregat masyarakat
    dan direksi/komisaris. Yang hilang justru rentang 1-5% yang menentukan
    dua angka di halaman ini:

      * individu 1-5% yang bukan pengurus (ADRO: T P Rachmat 4,11%,
        Sandiaga Uno 2,12%) -- harus dikeluarkan dari hitungan ritel;
      * institusi asing 1-5% (ADRO: Korea South East Power 1,67%, Lazard
        1,05%) -- itulah "Foreign Named" 2,7% di acuan.

    Keduanya cuma ada di feed KSEI berbayar, jadi di sini disediakan
    jalur manual. Setiap baris ditandai from_override supaya di tabel
    kelihatan mana yang dari IDX dan mana yang diisi tangan.
    """
    price = (latest_metrics or {}).get('price') or 0.0
    rows = []
    entries = list((overrides or {}).get('extra_holders') or [])
    # Alias lama: named_individuals hanya berisi orang.
    for legacy in (overrides or {}).get('named_individuals') or []:
        entries.append(dict(legacy, type='person'))

    for entry in entries:
        name = (entry.get('name') or '').strip()
        pct = entry.get('pct')
        if not name or pct is None or name.lower() in existing_names:
            continue
        existing_names.add(name.lower())

        pct = float(pct)
        sec_num = (latest_metrics or {}).get('sec_num') or 0.0
        shares = sec_num * pct / 100.0
        # pct_prev opsional: kalau diisi, kolom perbandingan bulan lalu dan
        # delta ritel jadi tepat. Tanpa itu posisi dianggap tidak berubah,
        # yang bikin delta ritel terlalu kecil -- PADI: -0,18pp padahal
        # seharusnya -0,37pp, karena Theja turun dan Bahroji naik.
        prev_pct = entry.get('pct_prev')
        prev_pct = float(prev_pct) if prev_pct is not None else None
        prev_shares = (sec_num * prev_pct / 100.0) if prev_pct is not None else None
        rows.append({
            'name': name,
            'category': entry.get('category') or 'Override (1-5%)',
            'controller': bool(entry.get('controller')),
            'nationality': entry.get('type') or 'unknown',
            'lot': shares / 100.0,
            'pct': pct,
            'value': shares * price,
            'prev_lot': (prev_shares / 100.0) if prev_shares is not None else None,
            'prev_pct': prev_pct,
            'change_lot': ((shares - prev_shares) / 100.0) if prev_shares is not None else None,
            'from_override': True,
        })
    return rows


def build_holder_table(registries, latest_metrics, overrides):
    """
    Daftar pemegang saham bernama dari IDX plus tambahan manual, dengan
    perbandingan bulan sebelumnya kalau snapshot bulan itu sudah pernah
    diambil.

    Bulan pertama pemakaian otomatis tidak punya pembanding -- kolom
    perubahan sengaja dikosongkan (None), bukan diisi nol, supaya
    "belum ada datanya" tidak terbaca sebagai "tidak berubah".
    """
    if not registries:
        extra = _extra_holder_rows(overrides, latest_metrics, set())
        extra.sort(key=lambda row: row['pct'], reverse=True)
        return extra, None, None

    current = registries[-1]
    previous = registries[-2] if len(registries) > 1 else None
    prev_by_name = {}
    if previous:
        for holder in previous.get('holders') or []:
            prev_by_name[(holder.get('Nama') or '').strip().lower()] = holder

    price = (latest_metrics or {}).get('price') or 0.0
    rows = []
    for holder in current.get('holders') or []:
        name = (holder.get('Nama') or '').strip()
        shares = float(holder.get('Jumlah') or 0.0)
        pct = float(holder.get('Persentase') or 0.0)
        if not name or (shares <= 0 and pct <= 0):
            continue

        before = prev_by_name.get(name.lower())
        prev_shares = float(before.get('Jumlah') or 0.0) if before else None
        prev_pct = float(before.get('Persentase') or 0.0) if before else None

        rows.append({
            'name': name,
            'category': (holder.get('Kategori') or '').strip(),
            'controller': bool(holder.get('Pengendali')),
            'nationality': classify_nationality(name, holder.get('Kategori'), overrides),
            'lot': shares / 100.0,
            'pct': pct,
            'value': shares * price,
            'prev_lot': (prev_shares / 100.0) if prev_shares is not None else None,
            'prev_pct': prev_pct,
            'change_lot': ((shares - prev_shares) / 100.0) if prev_shares is not None else None,
            'from_override': False,
        })

    extra = _extra_holder_rows(
        overrides, latest_metrics, {row['name'].lower() for row in rows})
    rows.extend(extra)
    _deduct_overrides_from_public(rows, extra)
    rows.sort(key=lambda row: row['pct'], reverse=True)
    return rows, current.get('month'), (previous or {}).get('month')


# Kategori agregat tempat pemegang <5% "disembunyikan" oleh registri IDX.
# Urutan ini juga urutan pengurangan: scripless dulu, sisanya baru warkat.
PUBLIC_POOL_CATEGORIES = ('Masyarakat Non Warkat', 'Masyarakat Warkat')


def _deduct_overrides_from_public(rows, extra):
    """
    Kurangi agregat "Masyarakat" sebesar total baris override.

    Registri IDX cuma merinci pemegang >=5%, treasury, dan direksi/
    komisaris -- SEMUA pemegang di bawah itu dilebur ke agregat
    "Masyarakat". Jadi begitu overrides.json memunculkan pemegang 1-5%
    sebagai baris sendiri, orang/institusi itu terhitung DUA KALI: sekali
    sebagai baris barunya, sekali lagi karena masih ikut terhitung di
    dalam agregat Masyarakat.

    Terbukti dari audit seluruh 881 emiten: cuma 3 emiten punya baris
    override (ADRO, BBRI, PADI), dan ketiganya persis 100,00% TANPA
    override lalu melonjak jadi 113,03 / 105,97 / 115,32 dengan override
    -- selisihnya persis sama dengan total override masing-masing. 878
    emiten lain (tanpa override) semuanya sudah 100% +/- 1pp.

    Pengurangan dilakukan di sini, bukan di _extra_holder_rows(), supaya
    baris override tetap apa adanya sesuai overrides.json -- yang
    dikoreksi agregatnya, bukan angka yang diisi tangan.
    """
    total_pct = sum(row['pct'] or 0.0 for row in extra)
    if total_pct <= 0:
        return

    total_prev_pct = sum(
        (row['pct'] if row.get('prev_pct') is None else row['prev_pct']) or 0.0
        for row in extra)
    total_lot = sum(row['lot'] or 0.0 for row in extra)
    total_value = sum(row['value'] or 0.0 for row in extra)

    for category in PUBLIC_POOL_CATEGORIES:
        if total_pct <= 0:
            break
        pool = next((r for r in rows
                     if (r.get('category') or '').strip() == category
                     and not r.get('from_override')), None)
        if pool is None or not pool.get('pct'):
            continue

        # Satu kantong bisa saja lebih kecil daripada total override
        # (mis. sebagian pemegangnya ternyata warkat) -- ambil sebanyak
        # yang muat, sisanya dilanjutkan ke kantong berikutnya, jangan
        # sampai ada baris yang jadi negatif.
        take_pct = min(pool['pct'], total_pct)
        share = take_pct / total_pct if total_pct else 0.0

        pool['pct'] -= take_pct
        pool['lot'] = (pool['lot'] or 0.0) - total_lot * share
        pool['value'] = (pool['value'] or 0.0) - total_value * share

        if pool.get('prev_pct') is not None:
            take_prev = min(pool['prev_pct'], total_prev_pct)
            pool['prev_pct'] -= take_prev
            total_prev_pct -= take_prev
        if pool.get('prev_lot') is not None:
            pool['prev_lot'] -= total_lot * share
            pool['change_lot'] = (pool['lot'] or 0.0) - pool['prev_lot']

        total_pct -= take_pct
        total_lot -= total_lot * share
        total_value -= total_value * share


def named_foreign_pct(rows):
    """
    Bagian kepemilikan asing yang bisa ditempelkan ke nama tertentu dari
    registri IDX. Sisanya -- "hidden player" -- adalah asing yang hanya
    terlihat sebagai angka agregat di KSEI, tanpa nama.
    """
    return sum(row['pct'] for row in rows if row['nationality'] == 'foreign')


def named_individual_rows(rows, overrides=None):
    """
    Individu bernama yang cukup besar untuk tidak dihitung ritel.

    "Retail (Pahlawan Bursa)" bukan seluruh bucket Individu (Local ID) di
    KSEI: taipan dan insider perorangan yang namanya muncul di daftar
    pemegang saham >1% dikeluarkan, lalu dipindahkan ke Lokal Non-Ritel.
    Terverifikasi terhadap dua acuan:

        ADRO  Local ID 25,45% - 16,74% (Thohir, TP Rachmat, Soeryadjaya,
              Uno) = 8,71%   vs acuan 8,70%
        PADI  Local ID 89,12% - 10,70% (Theja, Tan, Ekawati, Hermawan,
              Bahroji) = 78,42%   vs acuan 78,42%

    Registri IDX hanya memuat pemegang >=5% plus direksi/komisaris, jadi
    individu di rentang 1-5% yang bukan pengurus (TP Rachmat, Sandiaga
    Uno di ADRO) harus dilengkapi lewat overrides.json.
    """
    result = [
        {'name': row['name'], 'pct': row['pct'], 'pct_prev': row.get('prev_pct'),
         'source': 'override' if row.get('from_override') else 'IDX'}
        for row in rows
        if row['nationality'] == 'person' and row['pct'] >= NAMED_INDIVIDUAL_THRESHOLD
    ]
    result.sort(key=lambda item: item['pct'], reverse=True)
    return result


def free_float_pct(rows):
    """
    Cadangan free float kalau LBRPE belum ada: jumlah baris berkategori
    "Masyarakat" di registri IDX. Ini JAUH lebih longgar daripada free
    float resmi Peraturan I-A karena tidak mengeluarkan afiliasi
    pengendali (ADRO: 40,38% di sini vs 26,79% resmi), jadi di UI selalu
    diberi label sumbernya dan LBRPE didahulukan.
    """
    return sum(row['pct'] for row in rows if 'masyarakat' in row['category'].lower())


def konglo_from_owners(beneficial_owners):
    """
    Tebak nama grup konglomerasi dari pemilik manfaat terbesar di LBRPE:
    marga orangnya + " Group" (Garibaldi Thohir 6,863% -> "Thohir Group",
    cocok dengan acuan ADRO).

    Tidak selalu bisa: PADI melaporkan pemilik manfaat "tidak ada" tapi
    acuannya menyebut "Hapsoro Group", jadi itu memang kurasi manual dan
    harus lewat overrides.json.
    """
    candidates = [owner for owner in (beneficial_owners or [])
                  if owner.get('pct') and owner.get('name')]
    if not candidates:
        return ''
    top = max(candidates, key=lambda owner: owner['pct'])
    parts = [part for part in top['name'].split() if len(part) > 2]
    return (parts[-1] + ' Group') if parts else ''


def build_ownership(ticker):
    """
    Semua yang dibutuhkan halaman untuk satu emiten. Selalu mengembalikan
    dict; kalau datanya belum ada, 'available' False dan 'message' berisi
    langkah yang harus dijalankan.
    """
    ticker = re.sub(r'[^A-Z0-9]', '', (ticker or '').upper())[:6]
    if not ticker:
        return {'available': False, 'message': 'Kode saham tidak valid.'}

    months = load_ksei_months()
    series = [(payload['month'], payload['as_of'], payload['securities'][ticker])
              for payload in months if ticker in payload.get('securities', {})]

    if not series:
        return {
            'available': False,
            'ticker': ticker,
            'message': ('Belum ada data KSEI untuk %s. Jalankan: '
                        'python -m website.ownership fetch --months 12' % ticker),
        }

    overrides = load_overrides().get(ticker, {})
    registries = load_idx_registries(ticker)
    lbrpe = load_lbrpe(ticker) or {}

    latest = build_month_metrics(series[-1][2])
    previous = build_month_metrics(series[-2][2]) if len(series) > 1 else None

    holders, holder_month, holder_prev_month = build_holder_table(
        registries, latest, overrides)
    individuals = named_individual_rows(holders, overrides)

    # Persentase pemegang saham bernama dihitung terhadap SAHAM TERCATAT
    # (itu dasar yang dipakai IDX), sedangkan semua angka KSEI dihitung
    # terhadap SAHAM SCRIPLESS. Untuk emiten yang belum 100% scripless
    # keduanya beda, jadi harus dikonversi dulu sebelum dikurangkan.
    # Terverifikasi di PADI: 10,65% dari tercatat = 10,70% dari scripless,
    # dan 89,12% - 10,70% = 78,42% persis seperti acuan.
    def to_scripless_basis(pct_of_listed, metrics):
        if not metrics['scripless']:
            return 0.0
        return pct_of_listed * metrics['sec_num'] / metrics['scripless']

    def split_retail(metrics, individual_pcts):
        """Pisah bucket Individu KSEI jadi ritel kecil vs individu bernama."""
        carved = sum(to_scripless_basis(pct, metrics) for pct in individual_pcts)
        carved = min(carved, metrics['pct_retail'])
        return metrics['pct_retail'] - carved, metrics['pct_local_non_retail'] + carved

    individual_pcts = [item['pct'] for item in individuals]
    # Posisi bulan sebelumnya kalau diketahui; kalau tidak, dianggap sama.
    individual_pcts_prev = [
        item['pct'] if item.get('pct_prev') is None else item['pct_prev']
        for item in individuals
    ]
    retail_pct, local_non_retail_pct = split_retail(latest, individual_pcts)

    # Daftar individu bernama cuma diketahui untuk bulan terakhir dan --
    # kalau overrides mengisi pct_prev -- bulan sebelumnya. Bulan-bulan
    # yang lebih tua memakai daftar terakhir. Itu asumsi eksplisit:
    # komposisi pemegang besar bergerak jauh lebih lambat daripada
    # agregat ritel, jadi bentuk trennya tetap benar.
    prev_stamp = series[-2][0] if len(series) > 1 else None
    trend = []
    for stamp, as_of, record in series:
        metrics = build_month_metrics(record)
        pcts = individual_pcts_prev if stamp == prev_stamp else individual_pcts
        month_retail, month_local_non_retail = split_retail(metrics, pcts)
        trend.append({
            'month': stamp,
            'label': month_label(stamp),
            'as_of': as_of,
            'pct_foreign': round(metrics['pct_foreign'], 2),
            'pct_retail': round(month_retail, 2),
            'pct_local_non_retail': round(month_local_non_retail, 2),
            'market_cap': metrics['market_cap'],
            'scripless_ribu_lot': metrics['scripless_ribu_lot'],
            'price': metrics['price'],
        })

    # Pemegang saham bernama yang "foreign" di registri IDX kadang bukan
    # bagian dari saham scripless sama sekali -- sahamnya warkat, di luar
    # pantauan KSEI. Menyamaratakan pct-nya ke basis scripless lewat
    # to_scripless_basis() diam-diam MENGASUMSIKAN sahamnya tersebar
    # proporsional antara scripless/warkat sama seperti rata-rata
    # perusahaan -- asumsi yang runtuh untuk pengendali yang justru
    # sengaja memegang warkat. Ditemukan di WBSA: pengendali "Tiga
    # Beruang Kalifornia Pte. Ltd" 79,01% + Masyarakat Warkat 0,24% =
    # PERSIS 79,25%, yaitu seluruh porsi warkat perusahaan (scripless
    # cuma 20,75%) -- sahamnya 0% scripless, tapi rumus lama tetap
    # mengatribusikan seluruh 73,66% "Foreign" scripless ke dia.
    #
    # Perbaikan: kolam warkat perusahaan dianggap menyerap dulu sebanyak
    # mungkin dari total pct asing bernama (basis tercatat) SEBELUM
    # sisanya -- yang memang tidak muat lagi di kolam warkat, jadi mesti
    # ada di scripless -- dihitung sebagai "Named". Untuk emiten 100%
    # scripless kolam warkatnya nol, jadi rumus ini otomatis identik
    # dengan versi lama -- tidak mengubah ADRO/PADI/BBRI yang sudah
    # cocok dengan acuan.
    named_foreign_of_listed = named_foreign_pct(holders)
    warkat_pct_of_listed = 100.0 - latest['scripless_pct_of_listed']
    guaranteed_scripless_of_listed = max(0.0, named_foreign_of_listed - warkat_pct_of_listed)
    foreign_named = to_scripless_basis(guaranteed_scripless_of_listed, latest)
    # Jepit tambahan: registri IDX bisa juga beda tanggal potong dengan
    # KSEI, jadi tetap tidak boleh melebihi total asing scripless bulan ini.
    foreign_named = min(foreign_named, latest['pct_foreign'])
    foreign_hidden = max(latest['pct_foreign'] - foreign_named, 0.0)

    profile = registries[-1] if registries else {}

    # Free float resmi (Peraturan I-A) dari LBRPE kalau ada; kalau belum
    # ditarik, pakai jumlah baris "Masyarakat" di registri dan katakan
    # apa adanya di UI bahwa itu basis yang berbeda.
    if lbrpe.get('free_float') is not None:
        free_float, free_float_source = lbrpe['free_float'], 'LBRPE'
    elif holders:
        free_float, free_float_source = round(free_float_pct(holders), 2), 'registri IDX'
    else:
        free_float, free_float_source = None, None

    sid = overrides.get('sid') or lbrpe.get('sid')
    sid_source = 'override' if overrides.get('sid') else ('LBRPE' if lbrpe.get('sid') else None)
    if not sid and lbrpe.get('sid_prev'):
        # Pelapor kadang mengisi "Bulan Sekarang" dengan 0 (BBRI, LBRPE
        # Agustus 2026: 782.991 -> 0, "perubahan" 782.991). Emiten
        # tercatat tidak mungkin punya nol pemegang saham, jadi itu salah
        # isi -- pakai angka bulan sebelumnya dan katakan terus terang.
        sid = lbrpe['sid_prev']
        sid_source = 'LBRPE bulan sebelumnya (bulan ini dilaporkan 0)'

    # Saham ritel dalam lembar, dari persentase ritel yang sudah dikurangi
    # individu bernama -- bukan dari bucket Individu mentah.
    retail_shares = latest['scripless'] * retail_pct / 100.0

    # SID dari LBRPE mencakup SEMUA pemegang rekening, termasuk institusi.
    # Rata-rata per investor ritel idealnya dibagi jumlah SID ritel saja,
    # yang tidak diterbitkan; pembaginya jadi total SID dan hasilnya
    # sedikit lebih rendah (acuan konsisten ~2% lebih tinggi di ADRO,
    # PADI dan BBRI). Isi retail_sid di overrides.json kalau punya
    # angka ritelnya.
    retail_sid = overrides.get('retail_sid') or sid
    retail_sid_source = 'override' if overrides.get('retail_sid') else sid_source

    konglo = overrides.get('konglo') or konglo_from_owners(lbrpe.get('beneficial_owners'))

    prev_split = split_retail(previous, individual_pcts_prev) if previous else None

    def delta(current, before):
        if before is None:
            return None
        return round(current - before, 2)

    return {
        'available': True,
        'ticker': ticker,
        'name': profile.get('name') or '',
        'sector': profile.get('sector') or '',
        'sub_sector': profile.get('sub_sector') or '',
        'as_of': series[-1][1],
        'month_label': month_label(series[-1][0]),
        'prev_month_label': month_label(series[-2][0]) if len(series) > 1 else None,

        'market_cap': latest['market_cap'],
        'sec_num': latest['sec_num'],
        'price': latest['price'],
        'scripless_ribu_lot': latest['scripless_ribu_lot'],
        'scripless_pct_of_listed': round(latest['scripless_pct_of_listed'], 2),
        'free_float': free_float,
        'free_float_source': free_float_source,
        'sid': sid,
        'sid_source': sid_source,
        'retail_sid': retail_sid,
        'retail_sid_source': retail_sid_source,
        'avg_retail_lot': (retail_shares / 100.0 / retail_sid) if retail_sid else None,
        'avg_retail_value': (retail_shares * latest['price'] / retail_sid) if retail_sid else None,
        'konglo': konglo,

        'pct_foreign': round(latest['pct_foreign'], 2),
        'pct_retail': round(retail_pct, 2),
        'pct_local_non_retail': round(local_non_retail_pct, 2),
        'pct_retail_raw': round(latest['pct_retail'], 2),
        'pct_foreign_named': round(foreign_named, 2),
        'pct_foreign_hidden': round(foreign_hidden, 2),

        'delta_foreign': delta(latest['pct_foreign'],
                               previous['pct_foreign'] if previous else None),
        'delta_retail': delta(retail_pct, prev_split[0] if prev_split else None),
        # Pasangan mentah dari pct_retail_raw. Dibuka karena scanner.py menilai
        # bucket individu KSEI (yang mentah) -- tanpa ini Halaman Saham terpaksa
        # menyuapkan delta hasil carve-out ke aturan yang disusun dari yang
        # mentah, dua variabel berbeda lewat satu nama.
        'delta_retail_raw': delta(latest['pct_retail'],
                                  previous['pct_retail'] if previous else None),
        'delta_local_non_retail': delta(local_non_retail_pct,
                                        prev_split[1] if prev_split else None),

        'named_individuals': individuals,
        'lbrpe': {
            'period': lbrpe.get('period'),
            'announced_at': lbrpe.get('announced_at'),
            'source_url': lbrpe.get('source_url'),
            'sid_prev': lbrpe.get('sid_prev'),
            'beneficial_owners': lbrpe.get('beneficial_owners') or [],
        } if lbrpe else None,

        'breakdown': [{
            'code': code,
            'label': INVESTOR_LABELS[code],
            'local_shares': latest['local'].get(code, 0.0),
            'local_pct': round(latest['local_pct'].get(code, 0.0), 2),
            'foreign_shares': latest['foreign'].get(code, 0.0),
            'foreign_pct': round(latest['foreign_pct'].get(code, 0.0), 2),
        } for code in INVESTOR_CODES],

        'trend': trend,
        'holders': holders,
        'holder_month': month_label(holder_month) if holder_month else None,
        'holder_prev_month': month_label(holder_prev_month) if holder_prev_month else None,
        'has_registry': bool(registries),
        'has_lbrpe': bool(lbrpe),
    }


def available_tickers():
    """Emiten yang punya data KSEI, untuk autocomplete di halaman."""
    tickers = set()
    for payload in load_ksei_months():
        tickers.update(payload.get('securities', {}).keys())
    return sorted(tickers)


def load_all_sid():
    """
    {TICKER: sid} dari semua LBRPE yang pernah ditarik, snapshot terbaru
    yang menang. Dipakai tabel peringkat supaya kolom SID terisi untuk
    emiten yang sudah pernah dibuka, tanpa menarik ulang PDF-nya.
    """
    result = {}
    if not os.path.isdir(LBRPE_DIR):
        return result
    for stamp in sorted(os.listdir(LBRPE_DIR)):
        folder = os.path.join(LBRPE_DIR, stamp)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if not name.endswith('.json'):
                continue
            try:
                with open(os.path.join(folder, name), encoding='utf-8') as fh:
                    payload = json.load(fh)
            except (OSError, ValueError):
                continue
            if payload.get('sid'):
                result[name[:-5].upper()] = {
                    'sid': payload['sid'],
                    'free_float': payload.get('free_float'),
                    'period': payload.get('period'),
                }
    return result


def build_ranking():
    """
    Satu baris per emiten dari bulan KSEI terakhir, untuk tabel peringkat
    yang bisa disortir.

    Sengaja TIDAK memanggil build_ownership() per emiten: itu memuat
    registri IDX + LBRPE tiap tickernya, ~900 kali, dan jadi lambat tanpa
    guna. Konsekuensinya kolom ritel di sini adalah bucket Individu KSEI
    APA ADANYA -- tanpa mengeluarkan individu bernama >1%, karena itu
    butuh overrides per emiten. Halaman memberi label soal ini supaya
    tidak dibaca sebagai angka yang sama dengan kartu di atas.
    """
    months = load_ksei_months()
    if not months:
        return {'month': None, 'as_of': None, 'rows': []}

    latest = months[-1]
    prev = months[-2] if len(months) > 1 else None
    prev_securities = (prev or {}).get('securities', {})
    sid_map = load_all_sid()

    rows = []
    for ticker, record in latest.get('securities', {}).items():
        metrics = build_month_metrics(record)
        if not metrics['scripless']:
            continue

        before = prev_securities.get(ticker)
        prev_metrics = build_month_metrics(before) if before else None
        extra = sid_map.get(ticker) or {}

        rows.append({
            'ticker': ticker,
            'market_cap': metrics['market_cap'],
            'price': metrics['price'],
            'scripless_ribu_lot': metrics['scripless_ribu_lot'],
            'scripless_pct_of_listed': round(metrics['scripless_pct_of_listed'], 2),
            'pct_foreign': round(metrics['pct_foreign'], 2),
            'pct_retail_raw': round(metrics['pct_retail'], 2),
            'pct_local_non_retail': round(metrics['pct_local_non_retail'], 2),
            'delta_foreign': (round(metrics['pct_foreign'] - prev_metrics['pct_foreign'], 2)
                              if prev_metrics else None),
            'delta_retail': (round(metrics['pct_retail'] - prev_metrics['pct_retail'], 2)
                             if prev_metrics else None),
            'sid': extra.get('sid'),
            'free_float': extra.get('free_float'),
        })

    rows.sort(key=lambda row: row['market_cap'], reverse=True)
    return {
        'month': latest['month'],
        'label': month_label(latest['month']),
        'as_of': latest['as_of'],
        'prev_label': month_label(prev['month']) if prev else None,
        'sid_count': sum(1 for row in rows if row['sid']),
        'rows': rows,
    }


# ------------------------------------------------- perawatan (CLI + UI)

def refresh_ksei(months=2, force=False):
    """
    Tarik `months` bulan KSEI terakhir. Dipakai CLI `fetch` dan tombol di
    halaman, jadi hasilnya dikembalikan sebagai daftar baris log supaya
    keduanya bisa menampilkan hal yang sama.
    """
    today = date.today()
    year, month = today.year, today.month
    log = []
    saved = 0
    for _ in range(max(int(months), 1)):
        stamp = '%04d-%02d' % (year, month)
        existed = os.path.exists(os.path.join(KSEI_DIR, stamp + '.json'))
        try:
            result = fetch_ksei_month(year, month, force=force)
        except Exception as exc:
            log.append('fail %s: %s' % (stamp, exc))
            result = None
        if result:
            saved += 1
            log.append('ok   %s%s' % (stamp, ' (sudah ada)' if existed and not force else ''))
        else:
            log.append('--   %s (belum terbit / gagal unduh)' % stamp)
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return {'saved': saved, 'log': log}


def sync_ticker(ticker, force=False):
    """
    Registri IDX + LBRPE untuk satu emiten. Kegagalan salah satu tidak
    membatalkan yang lain -- halaman masih berguna dengan sebagian data.
    """
    ticker = re.sub(r'[^A-Z0-9]', '', (ticker or '').upper())[:6]
    log = []
    if not ticker:
        return {'ticker': '', 'log': ['fail: kode saham tidak valid']}

    try:
        result = fetch_idx_registry(ticker, force=force)
        log.append('ok   registri IDX -> %s' % os.path.basename(result or '-'))
    except Exception as exc:
        log.append('fail registri IDX: %s' % exc)

    try:
        result = fetch_lbrpe(ticker, force=force)
        if result:
            log.append('ok   LBRPE -> %s' % os.path.basename(result))
        else:
            log.append('--   LBRPE: tidak ada laporan 4 bulan terakhir')
    except Exception as exc:
        log.append('fail LBRPE: %s' % exc)

    return {'ticker': ticker, 'log': log}


# ------------------------------------------------- tarik massal + status

def _semesta_registry(semua=False):
    """Emiten yang perlu registri IDX / LBRPE.

    Default cuma yang punya berkas Summary -- sisanya tidak pernah muncul
    di halaman mana pun, jadi menariknya cuma membebani server IDX tanpa
    ada yang membacanya. `semua=True` mengambil seluruh emiten KSEI.
    """
    ksei = set(available_tickers())
    if semua:
        return sorted(ksei)
    try:
        from .live_scan import _all_stocks
        return sorted(ksei & set(_all_stocks()))
    except Exception:
        return sorted(ksei)


# Dua jenis tarik massal. Keduanya menyimpan ke <DIR>/<YYYY-MM>/<T>.json,
# jadi "sudah ada" = berkas bulan ini ada, dan menjalankan ulang otomatis
# melanjutkan dari sisa.
BATAS_GAGAL_BERUNTUN = 5

_JENIS_MASSAL = {
    'registry': {'label': 'registri IDX', 'dir': IDX_DIR, 'tarik': fetch_idx_registry},
    'lbrpe': {'label': 'LBRPE', 'dir': LBRPE_DIR, 'tarik': fetch_lbrpe},
}


def tarik_massal(jenis, daftar, jeda=2.0, ulang=3, lapor=print, berhenti=None):
    """
    Tarik registri IDX atau LBRPE untuk banyak emiten, sopan dan bisa
    dilanjutkan. Dipakai CLI `registry-all` dan menu Perbarui Kepemilikan.

    KENAPA BUKAN PERULANGAN BIASA
    Menembak ratusan emiten berturut-turut ke IDX yang ada di balik
    Cloudflare adalah cara efektif untuk diblokir di tengah jalan, dan
    begitu diblokir tidak ada jejak sampai mana tadi. Jadi: jeda acak,
    ulang-coba dengan backoff, dan catatan yang gagal.

    `berhenti` (threading.Event) diperiksa di antara emiten dan selama
    jeda, supaya tombol Hentikan di halaman bereaksi dalam hitungan detik.
    Mengembalikan dict ringkasan; `lapor` menerima satu baris teks.
    """
    spek = _JENIS_MASSAL[jenis]
    stamp = date.today().strftime('%Y-%m')
    folder = os.path.join(spek['dir'], stamp)

    def _dihentikan():
        return berhenti is not None and berhenti.is_set()

    def _tidur(detik):
        if berhenti is None:
            time.sleep(detik)
        else:
            berhenti.wait(detik)

    perlu = [t for t in daftar if not os.path.exists(os.path.join(folder, t + '.json'))]
    ringkas = {'total': len(perlu), 'selesai': 0, 'berhasil': 0, 'kosong': 0,
               'gagal': [], 'dihentikan': False}
    lapor('%s: %d emiten, %d sudah ada, %d akan diambil (jeda %.1f dtk + acak)'
          % (spek['label'], len(daftar), len(daftar) - len(perlu), len(perlu), jeda))
    if not perlu:
        lapor('Tidak ada yang perlu diambil.')
        return ringkas

    t0 = time.time()
    beruntun = 0
    for i, ticker in enumerate(perlu, 1):
        if _dihentikan():
            ringkas['dihentikan'] = True
            lapor('Dihentikan di %d/%d. Jalankan lagi untuk melanjutkan.' % (i - 1, len(perlu)))
            break
        galat, hasil = None, None
        for percobaan in range(1, ulang + 1):
            try:
                hasil = spek['tarik'](ticker)
                galat = None
                break
            except Exception as exc:
                galat = exc
                if percobaan >= ulang or _dihentikan():
                    break
                # Backoff menaik: kalau IDX sedang menolak, menembak
                # ulang secepatnya cuma memperdalam lubangnya.
                _tidur(jeda * (2 ** percobaan))
        if galat is not None and _dihentikan():
            # Ulang-coba diputus tombol Hentikan -- emiten ini belum
            # benar-benar gagal, jadi jangan dicatat sebagai gagal.
            ringkas['dihentikan'] = True
            lapor('Dihentikan di %d/%d. Jalankan lagi untuk melanjutkan.' % (i - 1, len(perlu)))
            break
        ringkas['selesai'] = i
        if galat is not None:
            ringkas['gagal'].append((ticker, str(galat)[:90]))
            tanda = 'GAGAL'
            beruntun += 1
            if beruntun >= BATAS_GAGAL_BERUNTUN:
                # Lima emiten berturut-turut gagal setelah ulang-coba itu
                # bukan masalah emitennya, tapi sumbernya menolak kita
                # (Sep-Okt 2026: Cloudflare IDX membalas 403 "Just a
                # moment..." ke semua request). Meneruskan cuma membuang
                # jam-jaman backoff dan memperparah blokirnya.
                lapor('[%4d/%d] GAGAL %-6s | %s' % (i, len(perlu), ticker, str(galat)[:90]))
                lapor('BERHENTI: %d emiten berturut-turut gagal -- sumbernya sedang '
                      'menolak (403 = Cloudflare). Coba lagi nanti.' % beruntun)
                ringkas['dihentikan'] = True
                break
        elif hasil:
            ringkas['berhasil'] += 1
            tanda = 'ok   '
            beruntun = 0
        else:
            # Hanya LBRPE: tidak ada laporan 4 bulan terakhir. Bukan galat.
            ringkas['kosong'] += 1
            tanda = 'kosong'
            beruntun = 0
        if i % 25 == 0 or i == len(perlu) or galat is not None:
            lewat = time.time() - t0
            sisa = (lewat / i) * (len(perlu) - i)
            lapor('[%4d/%d] %s %-6s | %d ok, %d kosong, %d gagal | sisa ~%.0f menit'
                  % (i, len(perlu), tanda, ticker, ringkas['berhasil'], ringkas['kosong'],
                     len(ringkas['gagal']), sisa / 60.0))
        if i < len(perlu):
            _tidur(jeda + random.uniform(0, jeda * 0.5))

    lapor('selesai %.1f menit | %d ok, %d kosong, %d gagal'
          % ((time.time() - t0) / 60.0, ringkas['berhasil'], ringkas['kosong'],
             len(ringkas['gagal'])))
    if ringkas['gagal']:
        catatan = os.path.join(OWNERSHIP_PATH, '%s_gagal_%s.log' % (jenis, stamp))
        with open(catatan, 'w', encoding='utf-8') as fh:
            for ticker, pesan in ringkas['gagal']:
                fh.write('%s\t%s\n' % (ticker, pesan))
        lapor('daftar gagal -> %s' % catatan)
        lapor('Jalankan ulang untuk menyapu sisanya.')
    return ringkas


# Satu pekerjaan latar sekaligus untuk seluruh proses web. Registri dan
# LBRPE sama-sama menembak IDX, jadi menjalankan dua bersamaan cuma
# menggandakan risiko diblokir.
_latar_kunci = threading.Lock()
_latar = {'jalan': False, 'jenis': None, 'label': None, 'mulai': None, 'akhir': None,
          'total': 0, 'selesai': 0, 'berhasil': 0, 'kosong': 0, 'gagal': 0,
          'log': deque(maxlen=300), 'hasil': None}
_latar_berhenti = threading.Event()


def _mulai_latar(jenis, label, kerja_inti):
    """
    Jalankan `kerja_inti(lapor, berhenti)` di thread latar sebagai satu-
    satunya pekerjaan kepemilikan yang berjalan. kerja_inti mengembalikan
    dict ringkasan bergaya tarik_massal(). Mengembalikan (ok, pesan).
    """
    luar = _baca_status_impor()
    if luar and luar.get('jalan'):
        return False, 'Impor LBRPE masih berjalan, tunggu selesai dulu.'
    with _latar_kunci:
        if _latar['jalan']:
            return False, 'Masih ada pekerjaan %s yang berjalan.' % _latar['label']
        _latar.update(jalan=True, jenis=jenis, label=label,
                      mulai=datetime.now().isoformat(timespec='seconds'),
                      akhir=None, total=0, selesai=0, berhasil=0, kosong=0, gagal=0, hasil=None)
        _latar['log'].clear()
        _latar_berhenti.clear()

    def lapor(baris):
        _latar['log'].append('%s  %s' % (datetime.now().strftime('%H:%M:%S'), baris))
        # Angka kemajuan dibaca ulang dari baris "[  i/n]" supaya fungsi
        # kerjanya tidak perlu tahu apa-apa soal pekerjaan latar.
        m = re.match(r'\[\s*(\d+)/(\d+)\].*\|\s*(\d+) ok, (\d+) kosong, (\d+) gagal', baris)
        if m:
            _latar.update(selesai=int(m.group(1)), total=int(m.group(2)), berhasil=int(m.group(3)),
                          kosong=int(m.group(4)), gagal=int(m.group(5)))

    def kerja():
        try:
            hasil = kerja_inti(lapor, _latar_berhenti)
            _latar.update(total=hasil['total'], selesai=hasil['selesai'], berhasil=hasil['berhasil'],
                          kosong=hasil['kosong'], gagal=len(hasil['gagal']),
                          hasil='dihentikan' if hasil['dihentikan'] else 'selesai')
        except Exception as exc:
            lapor('GALAT: %s: %s' % (type(exc).__name__, exc))
            _latar['hasil'] = 'galat'
        finally:
            with _latar_kunci:
                _latar['jalan'] = False
                _latar['akhir'] = datetime.now().isoformat(timespec='seconds')

    threading.Thread(target=kerja, daemon=True, name='ownership-%s' % jenis).start()
    return True, 'Dimulai.'


def mulai_tarik_latar(jenis, semua=False, daftar=None, jeda=2.0):
    """
    Jalankan tarik_massal() di thread latar. `daftar` (kode saham) menang
    atas semesta bawaan. Mengembalikan (ok, pesan).
    """
    if jenis not in _JENIS_MASSAL:
        return False, 'Jenis tidak dikenal: %s' % jenis

    def inti(lapor, berhenti):
        if daftar:
            kode = sorted({re.sub(r'[^A-Z0-9]', '', t.upper())[:6] for t in daftar} - {''})
        else:
            lapor('Menyusun semesta emiten...')
            kode = _semesta_registry(semua=semua)
        return tarik_massal(jenis, kode, jeda=jeda, lapor=lapor, berhenti=berhenti)

    return _mulai_latar(jenis, _JENIS_MASSAL[jenis]['label'], inti)


def hentikan_tarik_latar():
    luar = _baca_status_impor()
    if luar and luar.get('jalan'):
        # Impor LBRPE jalan di proses terpisah; ia memeriksa berkas ini
        # di antara PDF.
        open(BERHENTI_IMPOR, 'w').close()
        return True
    if not _latar['jalan']:
        return False
    _latar_berhenti.set()
    return True


def status_tarik_latar():
    """
    Pekerjaan yang paling relevan untuk ditampilkan: impor LBRPE di proses
    terpisah kalau sedang jalan atau lebih baru, selain itu thread latar.
    """
    data = {k: v for k, v in _latar.items() if k != 'log'}
    data['log'] = list(_latar['log'])
    luar = _baca_status_impor()
    if luar and not data['jalan'] and (luar.get('jalan') or (luar.get('mulai') or '') > (data.get('mulai') or '')):
        return luar
    return data


def _bulan_sebelumnya(hari):
    awal = hari.replace(day=1) - timedelta(days=1)
    return awal.strftime('%Y-%m')


def _hitung_json(folder):
    if not os.path.isdir(folder):
        return 0
    return sum(1 for n in os.listdir(folder) if n.endswith('.json'))


def status_data():
    """
    Posisi tiap sumber kepemilikan dibanding yang seharusnya sudah ada,
    untuk menu Perbarui Kepemilikan. Cuma membaca nama berkas, kecuali
    semesta emiten (sekali baca arsip KSEI, ~1 detik).

    Yang "seharusnya": KSEI = posisi akhir bulan lalu (terbit awal bulan
    ini), registri IDX & LBRPE = folder bulan berjalan.
    """
    today = date.today()
    stamp = today.strftime('%Y-%m')

    ksei_bulan = sorted(n[:-5] for n in (os.listdir(KSEI_DIR) if os.path.isdir(KSEI_DIR) else [])
                        if re.fullmatch(r'\d{4}-\d{2}\.json', n))
    ksei_target = _bulan_sebelumnya(today)
    ksei_terakhir = ksei_bulan[-1] if ksei_bulan else None

    try:
        semesta = len(_semesta_registry())
    except Exception:
        semesta = 0

    def _sumber(direktori, jenis):
        bulan = sorted(n for n in (os.listdir(direktori) if os.path.isdir(direktori) else [])
                       if re.fullmatch(r'\d{4}-\d{2}', n))
        gagal_log = os.path.join(OWNERSHIP_PATH, '%s_gagal_%s.log' % (jenis, stamp))
        gagal = 0
        if os.path.exists(gagal_log):
            with open(gagal_log, encoding='utf-8') as fh:
                gagal = sum(1 for baris in fh if baris.strip())
        return {
            'bulan_terakhir': bulan[-1] if bulan else None,
            'target': stamp,
            'jumlah_bulan_ini': _hitung_json(os.path.join(direktori, stamp)),
            'jumlah_terakhir': _hitung_json(os.path.join(direktori, bulan[-1])) if bulan else 0,
            'gagal_bulan_ini': gagal,
            'semesta': semesta,
        }

    return {
        'hari_ini': today.isoformat(),
        'ksei': {
            'bulan': ksei_bulan,
            'bulan_terakhir': ksei_terakhir,
            'target': ksei_target,
            'segar': bool(ksei_terakhir and ksei_terakhir >= ksei_target),
        },
        'registry': _sumber(IDX_DIR, 'registry'),
        'lbrpe': _sumber(LBRPE_DIR, 'lbrpe'),
        'latar': status_tarik_latar(),
    }



# ---------------------------------------------- registri lewat browser
#
# KENAPA LEWAT BROWSER
# Sampai 10 Sep 2026 registri ditarik langsung dari Python (cloudscraper).
# Sejak itu Cloudflare di IDX membalas 403 "Just a moment..." ke semua
# klien yang bukan browser asli, sementara browser biasa di komputer dan
# IP yang sama tetap dilayani. Jadi tarikannya dipindah ke browser kamu
# sendiri: menu membuat skrip berisi daftar emiten yang kurang, skrip itu
# dijalankan di Console tab idx.co.id (fetch same-origin, jeda sopan sama
# seperti registry-all), hasilnya terunduh sebagai satu JSON, lalu
# diimpor lewat menu. Bentuk snapshot-nya lewat _simpan_registri() yang
# sama dengan tarikan langsung.

FORMAT_REGISTRI_BROWSER = 'bdm-registri-idx-v1'

_SKRIP_REGISTRI = r"""// Registri IDX untuk BDM -- jalankan di Console tab www.idx.co.id
// (F12 -> Console -> tempel -> Enter). Berhenti: bdmBerhenti = true
// Simpan sebagian kapan saja: bdmSimpan()
(async () => {
  if (!/(^|\.)idx\.co\.id$/.test(location.hostname)) {
    console.error('Buka dulu https://www.idx.co.id di tab ini, lalu tempel skrip lagi.');
    return;
  }
  const KODE = __KODE__;
  const JEDA = __JEDA__;
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  const BULAN = d.getFullYear() + '-' + pad(d.getMonth() + 1);
  const hasil = {}, gagal = [];
  let beruntun = 0;
  window.bdmBerhenti = false;
  // Fungsi simpan LOKAL: kalau skrip registri dan LBRPE ditempel di tab
  // yang sama, window.bdmSimpan milik yang satu tidak boleh dipakai yang
  // lain di akhir -- dulu begitu, dan hasil skrip pertama hilang.
  const simpan = () => {
    const isi = JSON.stringify({ format: '__FORMAT__', bulan: BULAN,
      diambil: BULAN + '-' + pad(d.getDate()) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':00',
      data: hasil, gagal: gagal });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([isi], { type: 'application/json' }));
    a.download = 'registri_idx_' + BULAN + '_' + Object.keys(hasil).length + '.json';
    document.body.appendChild(a); a.click(); a.remove();
    console.log('Tersimpan: ' + Object.keys(hasil).length + ' emiten -> ' + a.download);
  };
  window.bdmSimpan = simpan;
  console.log('Registri IDX: ' + KODE.length + ' emiten, jeda ~' + (JEDA / 1000) + ' dtk. Biarkan tab ini terbuka.');
  const t0 = Date.now();
  for (let i = 0; i < KODE.length; i++) {
    if (window.bdmBerhenti) { console.warn('Dihentikan di ' + i + '/' + KODE.length); break; }
    const t = KODE[i];
    let j = null;
    try {
      const r = await fetch('/primary/ListedCompany/GetCompanyProfilesDetail?KodeEmiten=' + t + '&language=id-id',
                            { headers: { Accept: 'application/json' } });
      if (r.ok) { try { j = JSON.parse(await r.text()); } catch (e) { j = null; } }
    } catch (e) { j = null; }
    if (j) {
      beruntun = 0;
      const p = (j.Profiles || [])[0] || {};
      hasil[t] = { Profiles: [{ NamaEmiten: p.NamaEmiten, Sektor: p.Sektor, SubSektor: p.SubSektor,
                                PapanPencatatan: p.PapanPencatatan }],
                   PemegangSaham: j.PemegangSaham || [] };
    } else {
      gagal.push(t);
      if (++beruntun >= 5) {
        console.warn('IDX menolak 5x beruntun (mungkin minta verifikasi ulang). Hasil yang sudah ada disimpan. '
                   + 'Muat ulang halaman idx.co.id, lalu ambil skrip baru dari menu -- yang sudah diimpor otomatis dilewati.');
        break;
      }
    }
    if ((i + 1) % 25 === 0 || i === KODE.length - 1) {
      const sisa = (Date.now() - t0) / (i + 1) * (KODE.length - i - 1) / 60000;
      console.log('[' + (i + 1) + '/' + KODE.length + '] ' + Object.keys(hasil).length + ' ok, '
                  + gagal.length + ' gagal | sisa ~' + sisa.toFixed(0) + ' menit');
    }
    if (i < KODE.length - 1) { await new Promise(res => setTimeout(res, JEDA + Math.random() * JEDA * 0.5)); }
  }
  simpan();
  console.log('Selesai. Impor file tadi lewat menu Perbarui Kepemilikan.');
})();
"""


def skrip_registri_browser(semua=False, jeda=2.0):
    """
    Skrip Console untuk menarik registri IDX dari browser. Hanya berisi
    emiten yang belum punya snapshot bulan ini, jadi mengambil skrip baru
    setelah impor otomatis melanjutkan dari sisanya.
    """
    folder = os.path.join(IDX_DIR, date.today().strftime('%Y-%m'))
    kode = [t for t in _semesta_registry(semua=semua)
            if not os.path.exists(os.path.join(folder, t + '.json'))]
    skrip = (_SKRIP_REGISTRI
             .replace('__KODE__', json.dumps(kode))
             .replace('__JEDA__', str(int(jeda * 1000)))
             .replace('__FORMAT__', FORMAT_REGISTRI_BROWSER))
    return skrip, len(kode)


def impor_registri_browser(raw):
    """
    Impor file hasil skrip_registri_browser(). Mengembalikan dict ringkasan
    dengan daftar log, bentuknya sama dengan tombol lain di menu.
    """
    try:
        payload = json.loads(raw.decode('utf-8-sig') if isinstance(raw, bytes) else raw)
    except (ValueError, UnicodeDecodeError) as exc:
        return {'ok': False, 'log': ['File bukan JSON yang valid: %s' % exc]}
    if not isinstance(payload, dict) or payload.get('format') != FORMAT_REGISTRI_BROWSER:
        return {'ok': False, 'log': ['Bukan file registri dari skrip menu ini.']}
    stamp = payload.get('bulan') or ''
    if not re.fullmatch(r'\d{4}-\d{2}', stamp):
        return {'ok': False, 'log': ['Bulan di file tidak valid: %r' % stamp]}
    diambil = payload.get('diambil') or None

    simpan, kosong, aneh, tanpa_pemegang = 0, [], [], []
    for ticker, isi in (payload.get('data') or {}).items():
        ticker = str(ticker).upper()
        if not re.fullmatch(r'[A-Z0-9]{1,6}', ticker) or not isinstance(isi, dict):
            aneh.append(ticker)
            continue
        if not (isi.get('Profiles') or [{}])[0].get('NamaEmiten'):
            # Kode yang tidak dikenal IDX (sudah delisting / salah ketik):
            # jangan bikin snapshot kosong yang menimpa riwayat.
            kosong.append(ticker)
            continue
        if _simpan_registri(ticker, isi, stamp, fetched_at=diambil):
            simpan += 1
        else:
            tanpa_pemegang.append(ticker)

    log = ['ok   %d snapshot registri disimpan ke idx/%s/' % (simpan, stamp)]
    if tanpa_pemegang:
        log.append('--   %d emiten tanpa daftar pemegang saham dari IDX, snapshot lama tetap dipakai: %s'
                   % (len(tanpa_pemegang), ', '.join(tanpa_pemegang[:20])))
    if kosong:
        log.append('--   %d kode tanpa profil di IDX, dilewati: %s' % (len(kosong), ', '.join(kosong[:20])))
    if aneh:
        log.append('--   %d entri tidak dikenali, dilewati' % len(aneh))
    gagal = payload.get('gagal') or []
    if gagal:
        log.append('--   %d emiten gagal di browser; ambil skrip baru untuk menyapu sisanya' % len(gagal))
    return {'ok': True, 'saved': simpan, 'log': log}

# ------------------------------------------------- LBRPE lewat browser
#
# Sama alasannya dengan registri: IDX menolak Python sejak Sep 2026.
# Bedanya, LBRPE adalah PDF yang harus diparse pdfplumber, dan parser itu
# tidak ada di browser. Jadi browser cuma MENGAMBIL: cari pengumuman LBRPE
# terbaru per emiten, unduh PDF utamanya (~40-50 KB), kumpulkan sebagai
# base64 dalam satu file. Parsenya tetap di server lewat _simpan_lbrpe(),
# parser yang sama dengan tarikan langsung, jadi angkanya tidak mungkin
# beda. Parse ratusan PDF butuh beberapa menit, jadi impornya pekerjaan
# latar.
#
# Emiten yang pengumuman terbarunya sama dengan yang sudah tersimpan tidak
# diunduh ulang PDF-nya (browser diberi tanggal yang sudah diketahui);
# server cukup menyalin catatan lama ke folder bulan ini, sama seperti
# fetch_lbrpe() yang menyimpan laporan terbaru -- walau lama -- ke folder
# bulan berjalan.

FORMAT_LBRPE_BROWSER = 'bdm-lbrpe-idx-v1'

_SKRIP_LBRPE = r"""// LBRPE untuk BDM -- jalankan di Console tab www.idx.co.id
// (F12 -> Console -> tempel -> Enter). Berhenti: bdmBerhenti = true
// Simpan sebagian kapan saja: bdmSimpan()
(async () => {
  if (!/(^|\.)idx\.co\.id$/.test(location.hostname)) {
    console.error('Buka dulu https://www.idx.co.id di tab ini, lalu tempel skrip lagi.');
    return;
  }
  const KODE = __KODE__;
  const DIKETAHUI = __DIKETAHUI__;
  const JEDA = __JEDA__;
  const JUDUL = 'Registrasi Pemegang Efek';
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  const ymd = x => x.getFullYear() + pad(x.getMonth() + 1) + pad(x.getDate());
  const BULAN = d.getFullYear() + '-' + pad(d.getMonth() + 1);
  const awal = new Date(d.getFullYear(), d.getMonth() - 4, 1);
  const hasil = {}, gagal = [];
  let beruntun = 0, pdfN = 0;
  const tidur = ms => new Promise(res => setTimeout(res, ms));
  const keBase64 = blob => new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result).split(',')[1]);
    fr.onerror = rej;
    fr.readAsDataURL(blob);
  });
  window.bdmBerhenti = false;
  // Fungsi simpan LOKAL: kalau skrip registri dan LBRPE ditempel di tab
  // yang sama, window.bdmSimpan milik yang satu tidak boleh dipakai yang
  // lain di akhir -- dulu begitu, dan hasil skrip pertama hilang.
  const simpan = () => {
    const isi = JSON.stringify({ format: '__FORMAT__', bulan: BULAN,
      diambil: BULAN + '-' + pad(d.getDate()) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':00',
      data: hasil, gagal: gagal });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([isi], { type: 'application/json' }));
    a.download = 'lbrpe_idx_' + BULAN + '_' + Object.keys(hasil).length + '.json';
    document.body.appendChild(a); a.click(); a.remove();
    console.log('Tersimpan: ' + Object.keys(hasil).length + ' emiten (' + pdfN + ' PDF, '
                + (isi.length / 1048576).toFixed(1) + ' MB) -> ' + a.download);
  };
  window.bdmSimpan = simpan;
  console.log('LBRPE: ' + KODE.length + ' emiten, jeda ~' + (JEDA / 1000) + ' dtk. Biarkan tab ini terbuka.');
  const t0 = Date.now();
  for (let i = 0; i < KODE.length; i++) {
    if (window.bdmBerhenti) { console.warn('Dihentikan di ' + i + '/' + KODE.length); break; }
    const t = KODE[i];
    let ok = false;
    try {
      const r = await fetch('/primary/ListedCompany/GetAnnouncement?indexFrom=0&pageSize=60&dateFrom=' + ymd(awal)
                            + '&dateTo=' + ymd(d) + '&lang=id&keyword=&kodeEmiten=' + t + '&emitenType=s',
                            { headers: { Accept: 'application/json' } });
      let j = null;
      if (r.ok) { try { j = JSON.parse(await r.text()); } catch (e) { j = null; } }
      if (j) {
        ok = true;
        let pilih = null;
        for (const rep of (j.Replies || [])) {
          const p = rep.pengumuman || {};
          if (!(p.JudulPengumuman || '').includes(JUDUL)) continue;
          const att = (rep.attachments || []).find(a => !a.IsAttachment && a.FullSavePath);
          if (att) { pilih = { tgl: p.TglPengumuman || '', url: att.FullSavePath }; break; }
        }
        if (!pilih) {
          hasil[t] = { kosong: true };
        } else if (DIKETAHUI[t] && DIKETAHUI[t] === pilih.tgl) {
          hasil[t] = { sama: true, announced_at: pilih.tgl };
        } else {
          await tidur(500);
          const pr = await fetch(new URL(pilih.url).pathname);
          const blob = pr.ok ? await pr.blob() : null;
          if (blob && blob.size > 0) {
            hasil[t] = { announced_at: pilih.tgl, url: pilih.url, pdf: await keBase64(blob) };
            pdfN++;
          } else {
            ok = false;
          }
        }
      }
    } catch (e) { ok = false; }
    if (ok) {
      beruntun = 0;
    } else {
      gagal.push(t);
      if (++beruntun >= 5) {
        console.warn('IDX menolak 5x beruntun (mungkin minta verifikasi ulang). Hasil yang sudah ada disimpan. '
                   + 'Muat ulang halaman idx.co.id, lalu ambil skrip baru dari menu -- yang sudah diimpor otomatis dilewati.');
        break;
      }
    }
    if ((i + 1) % 25 === 0 || i === KODE.length - 1) {
      const sisa = (Date.now() - t0) / (i + 1) * (KODE.length - i - 1) / 60000;
      console.log('[' + (i + 1) + '/' + KODE.length + '] ' + Object.keys(hasil).length + ' ok ('
                  + pdfN + ' PDF baru), ' + gagal.length + ' gagal | sisa ~' + sisa.toFixed(0) + ' menit');
    }
    if (i < KODE.length - 1) { await tidur(JEDA + Math.random() * JEDA * 0.5); }
  }
  simpan();
  console.log('Selesai. Impor file tadi lewat menu Perbarui Kepemilikan.');
})();
"""


def _lbrpe_terbaru_semua():
    """{TICKER: (stamp, payload)} LBRPE tersimpan paling baru per emiten."""
    hasil = {}
    if not os.path.isdir(LBRPE_DIR):
        return hasil
    for stamp in sorted(os.listdir(LBRPE_DIR)):
        folder = os.path.join(LBRPE_DIR, stamp)
        if not (re.fullmatch(r'\d{4}-\d{2}', stamp) and os.path.isdir(folder)):
            continue
        for name in os.listdir(folder):
            if not name.endswith('.json'):
                continue
            try:
                with open(os.path.join(folder, name), encoding='utf-8') as fh:
                    hasil[name[:-5].upper()] = (stamp, json.load(fh))
            except (OSError, ValueError):
                continue
    return hasil


def skrip_lbrpe_browser(semua=False, jeda=2.0):
    """
    Skrip Console untuk LBRPE. Melewati emiten yang catatannya di folder
    bulan ini berasal dari laporan yang TERBIT bulan ini -- yang itu pasti
    sudah terbaru. Sisanya dicek, dan PDF hanya diunduh kalau
    pengumumannya lebih baru daripada yang tersimpan.
    """
    stamp = date.today().strftime('%Y-%m')
    terbaru = _lbrpe_terbaru_semua()
    kode, diketahui = [], {}
    for t in _semesta_registry(semua=semua):
        lama = terbaru.get(t)
        if lama and lama[0] == stamp and (lama[1].get('announced_at') or '')[:7] == stamp:
            continue
        kode.append(t)
        if lama and lama[1].get('announced_at'):
            diketahui[t] = lama[1]['announced_at']
    skrip = (_SKRIP_LBRPE
             .replace('__KODE__', json.dumps(kode))
             .replace('__DIKETAHUI__', json.dumps(diketahui))
             .replace('__JEDA__', str(int(jeda * 1000)))
             .replace('__FORMAT__', FORMAT_LBRPE_BROWSER))
    return skrip, len(kode)


IMPOR_DIR = os.path.join(OWNERSHIP_PATH, '_impor')
STATUS_IMPOR = os.path.join(IMPOR_DIR, 'status.json')
BERHENTI_IMPOR = os.path.join(IMPOR_DIR, 'berhenti')
# Detak status lebih tua dari ini = proses impornya sudah mati (ditutup,
# komputer tidur, dsb.), bukan sekadar sedang membaca PDF yang lambat.
DETAK_MATI_DETIK = 120


def _parse_b64_lbrpe(b64):
    """Untuk proses pekerja: base64 PDF -> dict parse, None, atau galat str."""
    try:
        return parse_pdf_lbrpe(base64.b64decode(b64 or ''))
    except Exception as exc:
        return 'GALAT %s: %s' % (type(exc).__name__, str(exc)[:80])


def _impor_lbrpe_inti(jalur, nama, lapor, berhenti, proses=1):
    """
    Parse file hasil skrip_lbrpe_browser(); ringkasan bergaya tarik_massal().

    BISA DILANJUTKAN: emiten yang folder bulan ini sudah berisi laporan
    dengan tanggal pengumuman yang sama dilewati, jadi mengimpor ulang file
    yang sama setelah terputus cuma mengerjakan sisanya.

    PARALEL: PDF dibaca `proses` pekerja sekaligus. Hanya aman dari proses
    yang __main__-nya bukan main.py (lihat jalankan_impor_lbrpe) -- di
    Windows tiap pekerja mengimpor ulang modul __main__, dan main.py akan
    membangun aplikasi Flask lengkap di tiap pekerja.
    """
    with open(jalur, encoding='utf-8-sig') as fh:
        payload = json.load(fh)
    stamp = payload.get('bulan') or ''
    if payload.get('format') != FORMAT_LBRPE_BROWSER or not re.fullmatch(r'\d{4}-\d{2}', stamp):
        raise ValueError('format/bulan file tidak valid')
    diambil = payload.get('diambil') or None
    data = payload.get('data') or {}
    del payload
    terbaru = _lbrpe_terbaru_semua()
    ringkas = {'total': len(data), 'selesai': 0, 'berhasil': 0, 'kosong': 0,
               'gagal': [], 'dihentikan': False}
    hitung = {'sama': 0, 'lewat': 0}
    lapor('impor %s: %d emiten, bulan %s, %d proses' % (nama, len(data), stamp, proses))

    # Pisahkan yang perlu baca PDF dari yang cukup dicatat. Yang sudah
    # tersimpan bulan ini dengan pengumuman yang sama = sudah diimpor.
    tugas = []
    for ticker, isi in sorted(data.items()):
        ticker = str(ticker).upper()
        if not re.fullmatch(r'[A-Z0-9]{1,6}', ticker) or not isinstance(isi, dict):
            ringkas['gagal'].append((ticker, 'entri tidak dikenali'))
        elif isi.get('kosong'):
            ringkas['kosong'] += 1
        elif isi.get('sama'):
            lama = terbaru.get(ticker)
            if lama:
                if lama[0] != stamp:
                    folder = os.path.join(LBRPE_DIR, stamp)
                    os.makedirs(folder, exist_ok=True)
                    with open(os.path.join(folder, ticker + '.json'), 'w', encoding='utf-8') as fh:
                        json.dump(lama[1], fh, ensure_ascii=False, indent=1)
                hitung['sama'] += 1
                ringkas['berhasil'] += 1
            else:
                ringkas['gagal'].append((ticker, 'ditandai sama tapi catatan lamanya tidak ada'))
        else:
            lama = terbaru.get(ticker)
            if (lama and lama[0] == stamp and isi.get('announced_at')
                    and lama[1].get('announced_at') == isi.get('announced_at')):
                hitung['lewat'] += 1
                ringkas['berhasil'] += 1
            else:
                tugas.append((ticker, isi))
    selesai_awal = len(data) - len(tugas)
    ringkas['selesai'] = selesai_awal
    if hitung['lewat']:
        lapor('%d sudah diimpor sebelumnya, dilewati' % hitung['lewat'])
    lapor('[%4d/%d] %-6s | %d ok, %d kosong, %d gagal -- %d PDF perlu dibaca'
          % (selesai_awal, len(data), '', ringkas['berhasil'], ringkas['kosong'],
             len(ringkas['gagal']), len(tugas)))

    def _catat(i, ticker, isi, hasil):
        ringkas['selesai'] = selesai_awal + i
        if isinstance(hasil, str):
            ringkas['gagal'].append((ticker, hasil[6:]))
        elif hasil is None:
            ringkas['gagal'].append((ticker, 'PDF tidak terbaca (free float & SID kosong)'))
        else:
            _tulis_lbrpe(ticker, hasil, isi.get('announced_at'), isi.get('url') or '',
                         stamp, fetched_at=diambil)
            ringkas['berhasil'] += 1
        if i % 25 == 0 or i == len(tugas):
            lapor('[%4d/%d] %-6s | %d ok, %d kosong, %d gagal'
                  % (ringkas['selesai'], len(data), ticker, ringkas['berhasil'],
                     ringkas['kosong'], len(ringkas['gagal'])))

    t0 = time.time()
    if proses > 1 and len(tugas) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(proses) as ex:
            hasil_iter = ex.map(_parse_b64_lbrpe, [isi.get('pdf') for _, isi in tugas], chunksize=4)
            for i, ((ticker, isi), hasil) in enumerate(zip(tugas, hasil_iter), 1):
                _catat(i, ticker, isi, hasil)
                if berhenti is not None and berhenti.is_set():
                    ringkas['dihentikan'] = True
                    ex.shutdown(wait=False, cancel_futures=True)
                    break
    else:
        for i, (ticker, isi) in enumerate(tugas, 1):
            if berhenti is not None and berhenti.is_set():
                ringkas['dihentikan'] = True
                break
            _catat(i, ticker, isi, _parse_b64_lbrpe(isi.get('pdf')))
    if ringkas['dihentikan']:
        lapor('Dihentikan. Impor ulang file yang sama untuk melanjutkan -- yang sudah tersimpan dilewati.')

    baru = ringkas['berhasil'] - hitung['sama'] - hitung['lewat']
    lapor('selesai %.1f menit: %d tersimpan (%d PDF baru, %d tidak berubah, %d sudah ada), '
          '%d tanpa LBRPE 4 bulan terakhir, %d gagal'
          % ((time.time() - t0) / 60.0, ringkas['berhasil'], baru, hitung['sama'], hitung['lewat'],
             ringkas['kosong'], len(ringkas['gagal'])))
    for ticker, pesan in ringkas['gagal'][:30]:
        lapor('  gagal %-6s %s' % (ticker, pesan))
    return ringkas


def _baca_status_impor():
    try:
        with open(STATUS_IMPOR, encoding='utf-8') as fh:
            status = json.load(fh)
    except (OSError, ValueError):
        return None
    if status.get('jalan'):
        try:
            detak = datetime.fromisoformat(status.get('detak') or status.get('mulai'))
        except (TypeError, ValueError):
            detak = None
        if detak is None or (datetime.now() - detak).total_seconds() > DETAK_MATI_DETIK:
            status.update(jalan=False, hasil='terputus')
            status.setdefault('log', []).append(
                'Proses impor berhenti tanpa pamit (ditutup / komputer tidur?). '
                'Impor ulang file yang sama untuk melanjutkan.')
    return status


def jalankan_impor_lbrpe(jalur, nama='lbrpe.json', proses=None):
    """
    Badan proses impor terpisah (CLI `impor-lbrpe`). Kemajuan ditulis ke
    _impor/status.json supaya menu bisa membacanya, dan tombol Hentikan
    bekerja lewat berkas _impor/berhenti.

    KENAPA PROSES TERPISAH, BUKAN THREAD DI FLASK
    8 Okt 2026 dua impor yang jalan sebagai thread di server mati di
    tengah jalan karena reloader Werkzeug me-restart server. Proses
    terpisah tidak ikut mati, dan cuma dari proses yang __main__-nya modul
    ini pembacaan PDF bisa diparalelkan dengan aman.
    """
    proses = proses or max(1, (os.cpu_count() or 2) - 2)
    status = {'jalan': True, 'jenis': 'impor-lbrpe', 'label': 'impor LBRPE',
              'mulai': datetime.now().isoformat(timespec='seconds'), 'akhir': None,
              'detak': datetime.now().isoformat(timespec='seconds'),
              'total': 0, 'selesai': 0, 'berhasil': 0, 'kosong': 0, 'gagal': 0,
              'hasil': None, 'log': [], 'pid': os.getpid()}
    log = deque(maxlen=300)

    def _tulis():
        status['detak'] = datetime.now().isoformat(timespec='seconds')
        status['log'] = list(log)
        sementara = STATUS_IMPOR + '.tmp'
        with open(sementara, 'w', encoding='utf-8') as fh:
            json.dump(status, fh, ensure_ascii=False)
        os.replace(sementara, STATUS_IMPOR)

    def lapor(baris):
        log.append('%s  %s' % (datetime.now().strftime('%H:%M:%S'), baris))
        print(baris, flush=True)
        m = re.match(r'\[\s*(\d+)/(\d+)\].*\|\s*(\d+) ok, (\d+) kosong, (\d+) gagal', baris)
        if m:
            status.update(selesai=int(m.group(1)), total=int(m.group(2)), berhasil=int(m.group(3)),
                          kosong=int(m.group(4)), gagal=int(m.group(5)))
        _tulis()

    class _Berhenti:
        @staticmethod
        def is_set():
            return os.path.exists(BERHENTI_IMPOR)

    os.makedirs(IMPOR_DIR, exist_ok=True)
    if os.path.exists(BERHENTI_IMPOR):
        os.remove(BERHENTI_IMPOR)
    _tulis()
    try:
        ringkas = _impor_lbrpe_inti(jalur, nama, lapor, _Berhenti, proses=proses)
        status.update(total=ringkas['total'], selesai=ringkas['selesai'], berhasil=ringkas['berhasil'],
                      kosong=ringkas['kosong'], gagal=len(ringkas['gagal']),
                      hasil='dihentikan' if ringkas['dihentikan'] else 'selesai')
        if not ringkas['dihentikan']:
            os.remove(jalur)
    except Exception as exc:
        lapor('GALAT: %s: %s' % (type(exc).__name__, exc))
        status['hasil'] = 'galat'
    finally:
        status.update(jalan=False, akhir=datetime.now().isoformat(timespec='seconds'))
        if os.path.exists(BERHENTI_IMPOR):
            os.remove(BERHENTI_IMPOR)
        _tulis()
    return status


def mulai_impor_lbrpe(raw, nama='lbrpe.json'):
    """
    Simpan file upload ke _impor/ lalu jalankan `python -m website.ownership
    impor-lbrpe <file>` sebagai proses terpisah yang lepas dari server.
    Mengembalikan (ok, pesan).
    """
    if FORMAT_LBRPE_BROWSER.encode() not in raw[:400]:
        return False, 'Bukan file LBRPE dari skrip menu ini.'
    if _latar['jalan']:
        return False, 'Masih ada pekerjaan %s yang berjalan.' % _latar['label']
    luar = _baca_status_impor()
    if luar and luar.get('jalan'):
        return False, 'Impor LBRPE sebelumnya masih berjalan.'

    import subprocess
    os.makedirs(IMPOR_DIR, exist_ok=True)
    jalur = os.path.join(IMPOR_DIR, datetime.now().strftime('lbrpe_%Y%m%d_%H%M%S.json'))
    with open(jalur, 'wb') as fh:
        fh.write(raw)
    # Status awal ditulis di sini juga, supaya polling pertama dari halaman
    # sudah melihat "berjalan" sebelum proses barunya sempat menulis.
    with open(STATUS_IMPOR, 'w', encoding='utf-8') as fh:
        json.dump({'jalan': True, 'jenis': 'impor-lbrpe', 'label': 'impor LBRPE',
                   'mulai': datetime.now().isoformat(timespec='seconds'),
                   'detak': datetime.now().isoformat(timespec='seconds'),
                   'total': 0, 'selesai': 0, 'berhasil': 0, 'kosong': 0, 'gagal': 0,
                   'hasil': None, 'log': ['Menyalakan proses impor...']}, fh)

    akar = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bendera = 0
    if os.name == 'nt':
        bendera = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    with open(os.path.join(IMPOR_DIR, 'impor_lbrpe.log'), 'ab') as keluaran:
        subprocess.Popen([sys.executable, '-m', 'website.ownership', 'impor-lbrpe', jalur,
                          '--nama', nama], cwd=akar, stdout=keluaran, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=bendera, close_fds=True)
    return True, 'Dimulai.'


# --------------------------------------------------------------- CLI

def _cli_fetch(argv):
    count = 12
    if '--months' in argv:
        try:
            count = int(argv[argv.index('--months') + 1])
        except (IndexError, ValueError):
            pass

    result = refresh_ksei(count, force='--force' in argv)
    for line in result['log']:
        print('  ' + line)
    print('Selesai: %d bulan tersimpan di %s' % (result['saved'], KSEI_DIR))


def _cli_registry(tickers, force=False):
    for ticker in tickers:
        try:
            result = fetch_idx_registry(ticker, force=force)
            print('  ok   registri %s -> %s' % (ticker.upper(), result))
        except Exception as exc:
            print('  fail registri %s: %s' % (ticker.upper(), exc))


def _cli_registry_all(argv, jenis='registry'):
    """
    Tarik registri IDX (atau LBRPE) untuk banyak emiten sekaligus, sopan
    dan bisa dilanjutkan -- lihat tarik_massal(). Sama dengan tombol di
    menu Perbarui Kepemilikan.

    Pemakaian:
        python -m website.ownership registry-all
        python -m website.ownership registry-all --limit 5     # uji dulu
        python -m website.ownership registry-all --semua       # + non-Summary
        python -m website.ownership registry-all --jeda 3.0
        python -m website.ownership lbrpe-all                  # LBRPE massal
    """
    def _angka(nama, bawaan):
        if nama in argv:
            try:
                return float(argv[argv.index(nama) + 1])
            except (IndexError, ValueError):
                pass
        return bawaan

    jeda = _angka('--jeda', 2.0)
    batas = int(_angka('--limit', 0))
    ulang = int(_angka('--ulang', 3))
    daftar = _semesta_registry(semua='--semua' in argv)
    if batas:
        folder = os.path.join(_JENIS_MASSAL[jenis]['dir'], date.today().strftime('%Y-%m'))
        daftar = [t for t in daftar if not os.path.exists(os.path.join(folder, t + '.json'))][:batas]
    tarik_massal(jenis, daftar, jeda=jeda, ulang=ulang)


def _cli_lbrpe(tickers, force=False):
    for ticker in tickers:
        try:
            result = fetch_lbrpe(ticker, force=force)
            if result:
                print('  ok   lbrpe %s -> %s' % (ticker.upper(), result))
            else:
                print('  --   lbrpe %s: tidak ada laporan 4 bulan terakhir' % ticker.upper())
        except Exception as exc:
            print('  fail lbrpe %s: %s' % (ticker.upper(), exc))


def _cli_show(ticker):
    data = build_ownership(ticker)
    if not data.get('available'):
        print(data.get('message'))
        return
    print('%s %s  (per %s)' % (data['ticker'], data['name'], data['as_of']))
    print('  Market cap            : %.3f T' % (data['market_cap'] / 1e12))
    print('  Scripless (ribu lot)  : %.3f' % data['scripless_ribu_lot'])
    print('  %% dari saham tercatat : %.2f%%' % data['scripless_pct_of_listed'])
    print('  Free float            : %s%% (%s)' % (data['free_float'], data['free_float_source']))
    print('  Jumlah pemegang saham : %s (%s)' % (data['sid'], data['sid_source']))
    print('  Foreign total         : %.2f%%' % data['pct_foreign'])
    print('    - named             : %.2f%%' % data['pct_foreign_named'])
    print('    - hidden player     : %.2f%%' % data['pct_foreign_hidden'])
    print('  Retail                : %.2f%%' % data['pct_retail'])
    print('  Lokal non-ritel       : %.2f%%' % data['pct_local_non_retail'])
    print('  Bulan tersedia        : %d' % len(data['trend']))
    print('  Pemegang saham IDX    : %d baris' % len(data['holders']))


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    command = argv[0]
    if command == 'fetch':
        _cli_fetch(argv[1:])
    elif command == 'registry':
        args = [a for a in argv[1:] if not a.startswith('--')]
        _cli_registry(args, force='--force' in argv)
    elif command == 'registry-all':
        _cli_registry_all(argv[1:])
    elif command == 'lbrpe-all':
        _cli_registry_all(argv[1:], jenis='lbrpe')
    elif command == 'impor-lbrpe':
        # Dipanggil menu lewat mulai_impor_lbrpe(); bisa juga manual:
        #   python -m website.ownership impor-lbrpe <file.json> [--proses 8]
        args = [a for a in argv[1:] if not a.startswith('--')]
        nama = argv[argv.index('--nama') + 1] if '--nama' in argv else None
        proses = int(argv[argv.index('--proses') + 1]) if '--proses' in argv else None
        if nama in args:
            args.remove(nama)
        if not args:
            print('Pakai: python -m website.ownership impor-lbrpe <file.json>')
            return 1
        hasil = jalankan_impor_lbrpe(args[0], nama=nama or os.path.basename(args[0]), proses=proses)
        return 0 if hasil.get('hasil') == 'selesai' else 1
    elif command == 'lbrpe':
        args = [a for a in argv[1:] if not a.startswith('--')]
        _cli_lbrpe(args, force='--force' in argv)
    elif command == 'sync':
        # Sekali jalan untuk satu emiten: registri IDX + LBRPE. Jalur yang
        # sama dipakai tombol Sync di halaman, lewat sync_ticker().
        args = [a for a in argv[1:] if not a.startswith('--')]
        force = '--force' in argv
        for ticker in args:
            result = sync_ticker(ticker, force=force)
            print('== %s' % result['ticker'])
            for line in result['log']:
                print('  ' + line)
    elif command == 'show':
        _cli_show(argv[1] if len(argv) > 1 else '')
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
