try:
    from .runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
except ImportError:
    from website.runtime_paths import runtime_file as _runtime_file, market_file as _market_file, WEBSITE_DIR as _WEBSITE_DIR, PROJECT_DIR as _PROJECT_DIR, RUNTIME_DIR as _RUNTIME_DIR
from flask import Blueprint, render_template, redirect, request, flash, jsonify, url_for, send_from_directory, current_app
from flask_login import login_required, current_user
from .models  import *
from sqlalchemy import asc, desc
import os
import re
import math
from datetime import datetime, timedelta
from .utilities import *
from .flow_health import check as flow_check

views = Blueprint('views', __name__)


@views.route('/sw.js')
def serviceWorker():
    """
    Served from the root path (not /static/js/sw.js) so its default scope
    covers the whole app — a service worker registered from a subpath is
    normally confined to that subpath, which would stop the browser from
    treating this as an installable app covering every page.
    """
    return send_from_directory(
        os.path.join(current_app.static_folder, 'js'), 'sw.js',
        mimetype='application/javascript',
    )

# Columns a user is allowed to sort stock-list tables by. Whitelisting these
# (rather than passing request.args.get('sort') straight into order_by)
# avoids letting someone pass an arbitrary/invalid column name.
SORTABLE_COLUMNS = {
    'stock': 'data',
    'diff5': 'diff5',
    'retail': 'retail',
    'avgPrice': 'avgPrice',
    'retailValue': 'retailValue',
}


def get_order_by(default_column='retailValue'):
    """
    Reads ?sort=<col>&dir=<asc|desc> from the query string and returns the
    corresponding SQLAlchemy order_by clause, falling back to a sane
    default (ascending by retailValue, matching the original behavior)
    when the params are missing or invalid.
    """
    sort_key = request.args.get('sort', default_column)
    column_name = SORTABLE_COLUMNS.get(sort_key, default_column)
    direction = desc if request.args.get('dir') == 'desc' else asc
    return direction(column_name)


BULAN_ID = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']


def tanggal_id(s):
    """'2026-09-22' -> '22 Sep 2026'. Apa pun yang lain dikembalikan apa adanya."""
    try:
        d = datetime.strptime(str(s)[:10], '%Y-%m-%d')
        return '%d %s %d' % (d.day, BULAN_ID[d.month - 1], d.year)
    except (TypeError, ValueError):
        return s


_FAKTA = {'ts': 0.0, 'isi': None}


def fakta_data():
    """
    Fakta ringan tentang datanya: jumlah emiten, tanggal data terakhir, jumlah
    hari bursa. Dipakai landing page DAN chip kesegaran di topbar -- yang
    terakhir berarti dipanggil di SETIAP render halaman lewat context
    processor, jadi di-cache 10 menit di memori (~30 ms kalau dingin).
    """
    import glob
    import time as _time
    import pandas as _pd
    from .config import DAILY_PATH

    if _FAKTA['isi'] is not None and _time.time() - _FAKTA['ts'] < 600:
        return _FAKTA['isi']
    isi = {'n_emiten': 0, 'data_sampai': None, 'n_hari': 0}
    try:
        berkas = glob.glob(os.path.join(DAILY_PATH, 'Summary', '*_Summary.csv'))
        isi['n_emiten'] = len(berkas)
        if berkas:
            d = _pd.read_csv(max(berkas, key=os.path.getsize), usecols=['Date'])
            t = _pd.to_datetime(d['Date'], format='%d-%b-%y', errors='coerce').dropna()
            if len(t):
                isi['data_sampai'] = t.max().strftime('%Y-%m-%d')
                isi['n_hari'] = int(t.nunique())
    except Exception:
        pass
    _FAKTA.update(ts=_time.time(), isi=isi)
    return isi


def _cache_tembus_basis():
    """Hasil Tembus Basis dari pickle-nya saja -- tidak pernah memindai."""
    import pickle
    from .tembus_basis import CACHE_FILE
    try:
        with open(CACHE_FILE, 'rb') as fh:
            return pickle.load(fh).get('result') or None
    except Exception:
        return None


def _seri_contoh(stock, tanggal, lebar=560, n_sebelum=50):
    """
    Titik-titik SVG untuk chart contoh di landing page: harga ASLI emiten
    contoh dari berkas Summary-nya, basis 30 hari sebelum hari tembus, dan
    volume. Koordinatnya dihitung di sini supaya template cuma menggambar.
    None kalau berkasnya tidak terbaca -- template lalu memakai ilustrasi.

    Basisnya digambar dari Summary saja, sedangkan angka basis30 di cache
    dihitung dari harga yang sudah disambung dengan riwayat Yahoo. Keduanya
    hampir sama (rasio close Summary/Yahoo ~1,000, lihat tembus_basis.py);
    kotaknya ilustrasi rentang, angkanya tetap dari cache.
    """
    from .tembus_basis import SUMMARY_DIR, _baca_summary, C as TB_C
    df = _baca_summary(os.path.join(SUMMARY_DIR, '%s_Summary.csv' % stock))
    if df is None:
        return None
    try:
        i = int(df.index.get_loc(datetime.strptime(tanggal, '%Y-%m-%d')))
    except (KeyError, TypeError, ValueError):
        return None
    if i < TB_C['BASIS_W']:
        return None
    w = df.iloc[max(0, i - n_sebelum):]
    k = i - max(0, i - n_sebelum)                    # posisi hari sinyal di dalam jendela
    n = len(w)
    if n < 10:
        return None
    hi = float(w['High'].fillna(w['Close']).max())
    lo = float(w['Low'].fillna(w['Close']).min())
    pad = (hi - lo) * 0.08 or hi * 0.02
    hi, lo = hi + pad, lo - pad
    atas, bawah = 30.0, 196.0                        # pita harga; volume di bawahnya
    x0, x1 = 20.0, lebar - 20.0
    langkah = (x1 - x0) / (n - 1)
    x = [x0 + j * langkah for j in range(n)]

    def y(p):
        return bawah - (float(p) - lo) / (hi - lo) * (bawah - atas)

    close = w['Close'].tolist()
    garis = ' '.join('%s%.1f %.1f' % ('M' if j == 0 else 'L', x[j], y(c)) for j, c in enumerate(close))
    area = '%s L%.1f %.1f L%.1f %.1f Z' % (garis, x[-1], bawah + 4, x[0], bawah + 4)

    b = w.iloc[k - TB_C['BASIS_W']:k]
    ph = float(max(b['High'].fillna(b['Close']).max(), b['Close'].max()))
    pl = float(min(b['Low'].fillna(b['Close']).min(), b['Close'].min()))
    basis = {'x': x[k - TB_C['BASIS_W']] - langkah / 2, 'y': y(ph),
             'w': langkah * TB_C['BASIS_W'], 'h': max(y(pl) - y(ph), 4)}

    vmax = float(w['Volume'].max()) or 1.0
    lebar_bar = max(min(langkah * 0.62, 10), 2)
    volume = [{'x': x[j] - lebar_bar / 2, 'y': 240 - max(v / vmax * 36, 1.5), 'h': max(v / vmax * 36, 1.5),
               'sinyal': j == k} for j, v in enumerate(w['Volume'].tolist())]
    return {
        'garis': garis, 'area': area, 'basis': basis, 'volume': volume, 'lebar_bar': lebar_bar,
        'titik': {'x': x[k], 'y': y(close[k])},
        'label_x': min(max(x[k] - 54, 8), lebar - 116),
        'label_y': max(y(close[k]) - 44, 4),
        'mulai_id': tanggal_id(w.index[0].strftime('%Y-%m-%d')),
        'akhir_id': tanggal_id(w.index[-1].strftime('%Y-%m-%d')),
    }


def _landing():
    """
    Halaman depan untuk pengunjung yang belum masuk.

    SENGAJA hanya fakta agregat tentang data dan app (jumlah emiten, tanggal
    data, status bukti tiap menu, satu contoh sinyal) -- tidak ada posisi,
    watchlist, atau cash. Halaman ini terbuka tanpa login.
    """
    from .status_bukti import ringkasan

    fakta = dict(fakta_data())
    fakta['data_sampai_id'] = tanggal_id(fakta.get('data_sampai'))
    try:
        bukti = ringkasan()
    except Exception:
        bukti = None
    contoh = None
    tb = _cache_tembus_basis()
    if tb:
        pertama = [b for b in tb.get('baris') or [] if b.get('pertama')]
        if pertama:
            from .tembus_basis import BUKTI as TB_BUKTI
            peta = {r['kunci']: r for r in TB_BUKTI['validasi']}
            p = pertama[0]
            try:
                seri = _seri_contoh(p['stock'], p['tanggal'])
            except Exception:
                seri = None
            contoh = dict(p, as_of_id=tanggal_id(p.get('tanggal')), seri=seri,
                          bukti=peta.get(p.get('aturan')), pembanding=peta.get('pembanding'),
                          label={'keduanya': 'Tembus basis + puncak 52 minggu',
                                 'basis': 'Tembus basis tenang',
                                 'puncak': 'Puncak 52 minggu'}.get(p.get('aturan')))
    return render_template('landing.html', fakta=fakta, bukti=bukti, contoh=contoh)


_JURNAL_CACHE = {}


def _tanggal_terakhir(path, kolom='tanggal'):
    """Tanggal terbesar di satu jurnal CSV, di-cache per mtime (jurnal Penemu
    Pola tumbuh ~900 baris per hari bursa)."""
    import pandas as _pd
    try:
        m = os.path.getmtime(path)
    except OSError:
        return None
    lama = _JURNAL_CACHE.get(path)
    if lama and lama[0] == m:
        return lama[1]
    try:
        v = str(_pd.read_csv(path, usecols=[kolom], dtype=str)[kolom].max())
    except Exception:
        v = None
    _JURNAL_CACHE[path] = (m, v)
    return v


def _hari_ini():
    """Baris "hari ini" di dashboard: data, Tembus Basis, jurnal maju.
    Semua dari berkas yang SUDAH ada -- tidak ada yang dihitung di sini."""
    here = os.path.dirname(__file__)
    fd = fakta_data()
    out = {'data_sampai': fd.get('data_sampai'), 'data_sampai_id': tanggal_id(fd.get('data_sampai')),
           'n_emiten': fd.get('n_emiten')}
    tb = _cache_tembus_basis()
    if tb and tb.get('available'):
        out['tembus'] = {'as_of': tb.get('as_of'), 'as_of_id': tanggal_id(tb.get('as_of')),
                         'hitung': tb.get('hitung_hari_ini') or {}, 'n_layak': tb.get('n_layak')}
    jurnal = []
    for nama, berkas, url in (('Penemu Pola', 'pola_jurnal.csv', '/penemu-pola'),
                              ('Tembus Basis', 'tembus_basis_hari.csv', '/tembus-basis'),
                              ('Skor Kecondongan', 'kecondongan_hari.csv', '/skor-kecondongan'),
                              ('Insider', 'insider_jurnal_hari.csv', '/radar-insider')):
        akhir = _tanggal_terakhir(str(_runtime_file('', berkas)))
        jurnal.append({'nama': nama, 'url': url, 'terakhir': akhir, 'terakhir_id': tanggal_id(akhir),
                       'terkini': bool(akhir and out['data_sampai'] and akhir >= out['data_sampai'])})
    out['jurnal'] = jurnal
    out['jurnal_terkini'] = sum(1 for j in jurnal if j['terkini'])
    return out


@views.route('/', methods=['GET', 'POST'])
def home():
    # Pengunjung yang belum masuk mendapat landing page, bukan dilempar ke
    # /login -- halaman lain tetap dijaga login_required seperti biasa.
    if not current_user.is_authenticated:
        return _landing()

    watchlists = {
        'Portfolio': PortfolioStocks,
        'Best': BestStocks,
        'Best Low': BestLowStocks,
        'Pattern Up': PatternUpStocks,
    }

    stats = {}
    flow = {}
    for label, model in watchlists.items():
        records = scoped_query(model).all()
        stats[label] = len(records)

        # Flow meter: share of the list where retail is a net seller
        # (retail < 0), i.e. big money is absorbing supply. This is the
        # accumulation-vs-distribution question the app exists to answer,
        # so the bar reflects real data rather than being decorative.
        if records:
            accumulating = sum(1 for r in records if (r.retail or 0) < 0)
            flow[label] = round(accumulating / len(records) * 100)
        else:
            flow[label] = 0

    # Current accumulation-signal tickers across all watchlists — the
    # client compares this against a snapshot saved in localStorage from
    # the last visit to show "what's new since you were last here".
    current_signals = []
    seen = set()
    for label, model in watchlists.items():
        for r in scoped_query(model).all():
            if r.data in seen:
                continue
            seen.add(r.data)
            flow_data = compute_cumulative_flow(r.data)
            if flow_data and flow_data['confidence'] == 3:
                current_signals.append(r.data)

    jam = datetime.now().hour
    sapaan = ('Selamat pagi' if 4 <= jam < 11 else 'Selamat siang' if 11 <= jam < 15
              else 'Selamat sore' if 15 <= jam < 18 else 'Selamat malam')
    return render_template(
        "home.html", stats=stats, flow=flow, user=current_user,
        current_signals=sorted(current_signals),
        total_watchlist_count=sum(stats.values()),
        ringkas=_ringkasan_dashboard(),
        hari_ini=_hari_ini(),
        sapaan=sapaan,
    )


def _ringkasan_dashboard():
    """
    Ringkasan untuk Dashboard: regime pasar, sebaran sinyal, umur cache.

    SEMUANYA DIBACA DARI CACHE YANG SUDAH HANGAT, tidak ada yang dihitung
    di sini. Dashboard adalah halaman yang paling sering dibuka; menaruh
    perhitungan mahal di sini persis mengulang kesalahan yang bikin Kering
    Screener 33 detik. Yang dipakai: market_regime (pkl), live_scan
    days_back=14 (pkl), dan mtime berkas cache -- ketiganya di bawah 0,1
    detik setelah modulnya terimpor.

    Tiap bagian dibungkus sendiri: sumber yang gagal menghilangkan satu
    kartu, bukan menjatuhkan halaman depan.
    """
    out = {}

    try:
        # Cache basi TIDAK lagi berarti kartu hilang: angka terakhirnya tetap
        # tampil dengan tanda `basi` sampai pemeriksaan kesehatan malam itu
        # membangunnya ulang (lihat market_regime.get_regime_tersimpan).
        from .market_regime import get_regime_tersimpan
        r, segar = get_regime_tersimpan()
        r = r or {}
        if r.get('available'):
            out['regime'] = {
                'label': r.get('label'),
                'pct_up': r.get('pct_up'),
                'median_pct': r.get('median_pct'),
                'mean_pct': r.get('mean_pct'),
                'n': r.get('n'),
                'window_days': r.get('window_days'),
                'as_of': r.get('as_of'),
                'as_of_id': tanggal_id(r.get('as_of')),
                'basi': not segar,
            }
    except Exception:
        out['regime'] = None

    try:
        from .live_scan import cached_scan_if_ready
        # cached_scan_if_ready (bukan cached_scan) - dashboard ini harus
        # SELALU baca cache yang sudah hangat, tidak pernah memicu scan
        # sendiri. cached_scan() biasa punya fallback blocking (~50 detik)
        # kalau cache belum ada, dan itu bisa balapan sama thread warmup
        # _start_cache_warmup di __init__.py yang lagi ngisi cache yang
        # sama persis di background pas server baru start - request
        # pengunjung pertama jadi ikut nunggu scan penuh dobel.
        payload = cached_scan_if_ready(days_back=14)
        df = payload.get('df') if payload else None
        if df is not None and len(df):
            hitung = df['scanner'].value_counts()
            teratas = int(hitung.iloc[0])
            out['sinyal'] = {
                'total': int(len(df)),
                'pending': int(df['pending'].sum()),
                'as_of': str(payload.get('last_data_date'))[:10],
                'as_of_id': tanggal_id(str(payload.get('last_data_date'))[:10]),
                'per_detektor': [
                    {'nama': str(k), 'n': int(v),
                     'pct': round(int(v) / teratas * 100.0, 1)}
                    for k, v in hitung.items()
                ],
            }
        else:
            out['sinyal'] = {'total': 0, 'pending': 0, 'as_of': None, 'per_detektor': []}
    except Exception:
        out['sinyal'] = None

    try:
        from .kesehatan import TUGAS, BASI_JAM, _berkas, _umur_jam
        berkas = [(t['nama'], f, _umur_jam(f)) for t in TUGAS for f in _berkas(t)]
        hilang = [n for n, _f, u in berkas if u is None]
        # Dulu `[n for _n, _f, u in ...]` -- `n` tidak terdefinisi di
        # comprehension ini, NameError-nya ditelan except di bawah, dan
        # kartu kesehatan cache di dashboard TIDAK PERNAH muncul.
        basi = [n for n, _f, u in berkas if u is not None and u >= BASI_JAM]
        out['cache'] = {
            'total': len(berkas),
            'segar': len(berkas) - len(hilang) - len(basi),
            'basi': sorted(set(basi)),
            'hilang': sorted(set(hilang)),
        }
    except Exception:
        out['cache'] = None

    return out


@views.route('/display-stocks/')
@login_required
def displayStocks() :
    """
    "All Charts" browse view — lets you page through every known ticker's
    dynamic chart. Previously this walked a folder of pre-generated .jpg
    files; now it just hands the full ticker universe to the chart
    viewer, which fetches each one live via /stock-chart-data/<stock>.
    """
    rangeDate = getRangeDate()
    return render_template(
        "stocks_image.html",
        user=current_user,
        tickers=stockList,
        rangeDate=rangeDate,
        context='browse',
        db_type_name=None,
        add_targets=compute_add_targets(),
        allow_delete=False,
    )


# Watchlist types the "quick add" buttons can target. Portfolio is
# intentionally excluded — the original UI never offered "add to
# Portfolio" from the browse view, only from managing Portfolio itself.
ADD_TARGET_TYPES = ['BestStocks', 'BestLowStocks', 'PatternUpStocks']


def compute_add_targets(exclude_type=None):
    return [t for t in ADD_TARGET_TYPES if t != exclude_type]


@views.route('/display-analyze')
@login_required
def displayAnalyze() :
    """
    Read-only algorithmic screens (Retail Sell, Consol, etc). Stocks here
    get added to a real watchlist with this screen recorded as the
    'source' (so admin() can clear them out of the screen once promoted),
    but the screen itself isn't directly editable/deletable.
    """
    rangeDate = getRangeDate()
    dbType = TypeDB.main(request.args.get("type"))
    if dbType is None:
        # Jalur galat ini dulu merender tanpa db_type_name/context, sehingga
        # `{{ db_type_name|tojson }}` di template kena Undefined dan halaman
        # balas 500 -- galat 500 untuk sesuatu yang cuma salah parameter.
        flash('Unknown stock list type', category='error')
        return render_template(
            "stocks_image.html", user=current_user, rangeDate=rangeDate,
            tickers=[], context='watchlist', db_type_name=None,
            add_targets=[], allow_delete=False)

    records = scoped_query(dbType).order_by(get_order_by()).all()
    tickers = [r.data for r in records]

    if not tickers:
        flash('Stock does not exist', category='error')

    return render_template(
        "stocks_image.html",
        user=current_user,
        tickers=tickers,
        rangeDate=rangeDate,
        context='screen',
        db_type_name=dbType.__name__,
        add_targets=['BestStocks', 'BestLowStocks', 'PatternUpStocks'],
        allow_delete=False,
    )

@views.route('/search', methods=['GET', 'POST'])
@login_required
def search() :
    rangeDate = getRangeDate()
    tickers = []
    # request.values covers both a POST form submit (command palette) and
    # a plain GET link with ?searched=TICKER (e.g. clicking a stock name
    # on Watchlist History) -- same lookup either way.
    raw = request.values.get('searched') or ''
    if raw:
        # Sanitize: stock tickers are alphanumeric only. Stripping to
        # alphanumeric chars (and capping the length) prevents path
        # traversal via things like "..\\..\\Windows\\...".
        data = re.sub(r'[^A-Za-z0-9]', '', raw).strip()[:6].upper()

        if not data:
            flash('Please enter a valid stock code', category='error')
        else:
            tickers = [data]

    return render_template(
        "stocks_image.html",
        user=current_user,
        tickers=tickers,
        rangeDate=rangeDate,
        context='browse',
        db_type_name=None,
        add_targets=compute_add_targets(),
        allow_delete=False,
    )
        

@views.route('/display-stock-list', methods=['GET', 'POST'])
@login_required
def display():
    """
    A user-managed watchlist (Portfolio / Best / Best Low / Pattern Up):
    editable, so the chart viewer also offers "delete from this list" in
    addition to "add to another list".
    """
    rangeDate = getRangeDate()
    dbType = TypeDB.main(request.args.get("type"))
    if dbType is None:
        # Sama seperti di displayAnalyze: jalur galat ini dulu merender tanpa
        # db_type_name/add_targets, sehingga tojson kena Undefined dan halaman
        # balas 500 untuk sesuatu yang cuma salah parameter URL.
        flash('Unknown stock list type', category='error')
        return render_template(
            "stocks_image.html", user=current_user, rangeDate=rangeDate,
            tickers=[], context='watchlist', db_type_name=None,
            add_targets=[], allow_delete=False)

    stocks = scoped_query(dbType).order_by(get_order_by()).all()
    tickers = [s.data for s in stocks]

    return render_template(
        "stocks_image.html",
        user=current_user,
        tickers=tickers,
        rangeDate=rangeDate,
        context='watchlist',
        db_type_name=dbType.__name__,
        add_targets=compute_add_targets(exclude_type=dbType.__name__),
        allow_delete=True,
    )


@views.route('/watchlist-history')
@login_required
def watchlistHistory():
    """
    Add/remove log for the user-managed watchlists — admin() writes an
    entry here every time a stock is added to or removed from Portfolio /
    Best / Best Low / Pattern Up, so that history survives past the
    stock's removal from the live list. A Pattern Up -> Best/Best Low
    promotion is not logged as a Pattern Up removal (see admin()'s "add"
    branch) since the stock is still being watched, just under a
    different list -- only a genuine standalone delete from Pattern Up
    shows up here.
    """
    listType = request.args.get('type')
    query = scoped_query(WatchlistHistory)
    if listType and listType in WATCHLIST_HISTORY_TYPES:
        query = query.filter_by(listType=listType)

    entries = query.order_by(WatchlistHistory.timestamp.desc()).limit(300).all()

    # For every entry (added AND removed), work out how the price has
    # moved since -- answers "did this actually pay off" instead of just
    # logging that it happened. `avgPrice` on a 'removed' row is still the
    # price it was originally *added* at (admin() carries the list row's
    # own avgPrice through unchanged to the removal log), so the same
    # calculation applies to both: % move from that add-time price to
    # today, whether or not the stock is still on the list now. Cached
    # per-stock since the same ticker often repeats across multiple rows.
    flow_cache = {}
    for e in entries:
        e.pctSinceAdded = None
        e.currentClose = None
        if e.avgPrice:
            if e.stock not in flow_cache:
                flow_cache[e.stock] = compute_cumulative_flow(e.stock)
            flow = flow_cache[e.stock]
            if flow and flow.get('lastClose'):
                e.currentClose = flow['lastClose']
                # Percent move expressed against the entry close: (current
                # close - entry close) / entry close * 100.
                e.pctSinceAdded = round((flow['lastClose'] - e.avgPrice) / e.avgPrice * 100, 2)

    return render_template(
        "watchlist_history.html",
        user=current_user,
        entries=entries,
        listType=listType,
        list_types=sorted(WATCHLIST_HISTORY_TYPES),
        now=datetime.utcnow(),
    )


@views.route('/akuisisi')
@login_required
def akuisisi():
    """
    Lists real acquisition/change-of-control news found for watchlist
    tickers (see acquisition_signals.csv) -- replaces the old Breakout
    Signals page. Backtesting several technical patterns (sideways+spike,
    retail crossover, foreign/domestic divergence) found no reliable
    predictor of big rallies; the actual biggest movers in this watchlist
    all turned out to be driven by real M&A news or exchange-flagged
    speculative activity, so this tracks that directly instead.
    """
    return render_template(
        "acquisitions.html",
        user=current_user,
        signals=load_acquisition_signals(),
    )


@views.route('/akuisisi/search')
@login_required
def akuisisiSearch():
    """
    Live search over Google News RSS (no API key needed) for acquisition /
    change-of-control news, so new candidates can be found from inside the
    app instead of asking for a manual news lookup each time. ?from=&to=
    (YYYY-MM-DD) narrow the date range; ?q= adds one extra search term on
    top of the ACQUISITION_NEWS_QUERIES list in utilities.py. ?saved=1
    shows the persisted cache of every past search instead of hitting
    Google News again.
    """
    date_from = request.args.get('from') or None
    date_to = request.args.get('to') or None
    extra_query = request.args.get('q') or None
    show_saved = request.args.get('saved') == '1'

    results = []
    error = None
    if show_saved:
        results = load_news_cache(date_from=date_from, date_to=date_to)
    elif date_from or date_to or request.args.get('searched'):
        try:
            results = search_acquisition_news(date_from=date_from, date_to=date_to, extra_query=extra_query)
        except Exception:
            logger.exception('Akuisisi news search failed')
            error = 'Gagal mengambil berita. Coba lagi.'

    return render_template(
        "acquisitions_search.html",
        user=current_user,
        results=results,
        date_from=date_from,
        date_to=date_to,
        extra_query=extra_query,
        error=error,
        show_saved=show_saved,
        searched=bool(show_saved or date_from or date_to or request.args.get('searched')),
    )


@views.route('/akuisisi/add', methods=['POST'])
@login_required
def akuisisiAdd():
    """
    Adds one row to acquisition_signals.csv from a search-result "Tambah"
    action (or manual entry) on the search page.
    """
    stock = request.form.get('stock', '')
    announcement_date = request.form.get('announcement_date', '')
    new_controller = request.form.get('new_controller', '')
    stake_pct = request.form.get('stake_pct', '')
    value_idr_b = request.form.get('value_idr_b', '')
    description = request.form.get('description', '')

    ok, err = add_acquisition_signal(
        stock, announcement_date,
        new_controller=new_controller, stake_pct=stake_pct or None,
        value_idr_b=value_idr_b or None, description=description,
    )
    if not ok:
        return jsonify(rsp='error', message=err), 400
    return jsonify(rsp='success')


@views.route('/akuisisi/chart')
@login_required
def akuisisiChart():
    """
    Same multi-stock chart viewer used everywhere else, but walking the
    Akuisisi list specifically — each entry carries its own announcement
    date, so the chart opens centered on the day the news broke instead of
    always showing "now".
    """
    signals = load_acquisition_signals()
    tickers = [s['stock'] for s in signals]
    focus_dates = [s['announcement_date'] for s in signals]

    start_index = 0
    index_param = request.args.get('index')
    if index_param and index_param.isdigit() and tickers:
        start_index = min(int(index_param), len(tickers) - 1)

    return render_template(
        "stocks_image.html",
        user=current_user,
        tickers=tickers,
        focusDates=focus_dates,
        startIndex=start_index,
        rangeDate=getRangeDate(),
        context='browse',
        db_type_name='Akuisisi',
        add_targets=compute_add_targets(),
        allow_delete=False,
    )


@views.route('/compare')
@login_required
def compare():
    """
    Overlay 2-6 tickers on one normalized (% change from the first bar)
    chart, so relative performance is easy to read side by side instead
    of eyeballing separate single-stock charts. Data comes from the same
    /stock-chart-data/<stock> endpoint the single-stock viewer uses.
    """
    watchlists = [
        {'label': 'Portfolio', 'type': 'PortfolioStocks'},
        {'label': 'Best', 'type': 'BestStocks'},
        {'label': 'Best Low', 'type': 'BestLowStocks'},
        {'label': 'Pattern Up', 'type': 'PatternUpStocks'},
    ]
    return render_template("compare.html", user=current_user, watchlists=watchlists)


@views.route('/weekly-report')
@login_required
def weeklyReport():
    """
    Combines the last 7 days of watchlist add/remove activity with a
    live scan of the current watchlists for accumulation signals (Net
    Top5 Lot cumulative positive, Retail cumulative negative) — a single
    page to check instead of piecing it together from History + Compare.
    """
    since = datetime.utcnow() - timedelta(days=7)
    activity = scoped_query(WatchlistHistory).filter(WatchlistHistory.timestamp >= since) \
        .order_by(WatchlistHistory.timestamp.desc()).all()

    watchlists = {
        'Portfolio': PortfolioStocks,
        'Best': BestStocks,
        'Best Low': BestLowStocks,
        'Pattern Up': PatternUpStocks,
    }
    signals = []
    crossings = []
    seen = set()
    for label, model in watchlists.items():
        for r in scoped_query(model).all():
            if r.data in seen:
                continue
            seen.add(r.data)
            flow = compute_cumulative_flow(r.data)
            if not flow:
                continue
            flow['list'] = label
            if flow['confidence'] == 3:
                signals.append(flow)
            if flow['crossing']:
                crossings.append(flow)

    signals.sort(key=lambda f: f['netTop5ValueB'], reverse=True)
    crossings.sort(key=lambda f: f['crossing']['daysAgo'])

    return render_template(
        "weekly_report.html",
        user=current_user,
        activity=activity,
        signals=signals,
        crossings=crossings,
        since=since,
        now=datetime.utcnow(),
    )


@views.route('/watchlist-history/latest')
@login_required
def watchlistHistoryLatest():
    """Latest history entry timestamp — lets the sidebar show an unread dot without loading the full page."""
    latest = scoped_query(WatchlistHistory).order_by(WatchlistHistory.timestamp.desc()).first()
    return jsonify(latest=latest.timestamp.isoformat() if latest and latest.timestamp else None)


@views.route('/watchlist-tickers')
@login_required
def watchlistTickers():
    """JSON list of tickers in a watchlist — powers the "load preset" buttons on /compare."""
    dbType = TypeDB.main(request.args.get('type'))
    if dbType is None:
        return jsonify(tickers=[])
    tickers = [r.data for r in scoped_query(dbType).order_by(dbType.data).all()]
    return jsonify(tickers=tickers)


def _finite_number(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError('Expected a finite number')
    return value


@views.route('/pnl')
@login_required
def pnl():
    """
    Real owned positions (buy price + lots actually paid for), separate
    from the watchlists — those only track what's being monitored, not
    what's actually been bought. P&L is computed against each stock's
    latest close via compute_cumulative_flow().
    """
    positions = Position.query.filter_by(userId=current_user.id).order_by(Position.buyDate.desc()).all()
    cash = CashBalance.query.filter_by(userId=current_user.id).first()
    cashAmount = cash.amount if cash else 0.0
    rows = []
    totalInvested = 0.0
    totalCurrent = 0.0

    # Posisi tertutup dipisah dan TIDAK ikut ringkasan atas. Mencampurnya
    # membuat "Total P&L" berarti dua hal sekaligus: untung yang masih
    # bergerak dan untung yang sudah final.
    tutup = [p for p in positions if p.sellDate and p.sellPrice]
    positions = [p for p in positions if not (p.sellDate and p.sellPrice)]

    closedRows = []
    realInvested = 0.0
    realProceeds = 0.0
    realMenang = 0
    for p in sorted(tutup, key=lambda x: x.sellDate, reverse=True):
        invested = p.buyPrice * p.lots * 100
        proceeds = p.sellPrice * p.lots * 100
        pnlValue = proceeds - invested
        realInvested += invested
        realProceeds += proceeds
        if pnlValue > 0:
            realMenang += 1
        closedRows.append({
            'id': p.id, 'stock': p.stock, 'buyPrice': p.buyPrice, 'lots': p.lots,
            'buyDate': p.buyDate, 'sellPrice': p.sellPrice, 'sellDate': p.sellDate,
            'invested': invested, 'proceeds': proceeds, 'pnlValue': pnlValue,
            'pnlPct': round((p.sellPrice - p.buyPrice) / p.buyPrice * 100, 2) if p.buyPrice else None,
            'holdDays': (p.sellDate - p.buyDate).days if p.buyDate and p.sellDate else None,
        })

    for p in positions:
        flow = compute_cumulative_flow(p.stock)
        lastClose = flow['lastClose'] if flow else None
        invested = p.buyPrice * p.lots * 100
        current = (lastClose * p.lots * 100) if lastClose is not None else None
        pnlValue = (current - invested) if current is not None else None
        pnlPct = round((lastClose - p.buyPrice) / p.buyPrice * 100, 2) if lastClose is not None and p.buyPrice else None
        totalInvested += invested
        if current is not None:
            totalCurrent += current

        # Kesehatan Arus SEJAK BELI -- flow_health.py yang sama dipakai
        # Scanner Lab/Kering Screener/Halaman Saham, tapi di-anchor ke
        # buyDate posisi ini, bukan tanggal sinyal scanner. Menjawab
        # "sejak saya pegang, arus institusional masih mendukung atau
        # sudah diam-diam berbalik" -- alat pemantauan posisi, bukan
        # pencari sinyal beli baru (beda dari semua kartu keputusan
        # lainnya di app ini yang selalu anchor ke sinyal, bukan ke
        # keputusan pribadi pengguna).
        flow_checkpoints = []
        best_flow = None
        if p.buyDate:
            try:
                fh = flow_check(p.stock, p.buyDate.strftime('%Y-%m-%d'))
                if fh.get('available'):
                    flow_checkpoints = fh['checkpoints']
                    available_cps = [c for c in flow_checkpoints if c['available']]
                    if available_cps:
                        best_flow = max(available_cps, key=lambda c: c['horizon'])
            except Exception:
                pass

        rows.append({
            'id': p.id, 'stock': p.stock, 'buyPrice': p.buyPrice, 'lots': p.lots,
            'buyDate': p.buyDate, 'lastClose': lastClose,
            'invested': invested, 'current': current, 'pnlValue': pnlValue, 'pnlPct': pnlPct,
            'flowCheckpoints': flow_checkpoints, 'bestFlow': best_flow,
        })

    return render_template(
        "pnl.html",
        user=current_user,
        rows=rows,
        totalInvested=totalInvested,
        totalCurrent=totalCurrent,
        totalPnl=totalCurrent - totalInvested,
        cashAmount=cashAmount,
        totalPortfolio=totalCurrent + cashAmount,
        closedRows=closedRows,
        realInvested=realInvested,
        realProceeds=realProceeds,
        realPnl=realProceeds - realInvested,
        realMenang=realMenang,
    )


def _get_cash():
    """Return only the current account's balance; leave legacy unowned rows untouched."""
    cash = CashBalance.query.filter_by(userId=current_user.id).first()
    if cash is None:
        cash = CashBalance(amount=0.0, userId=current_user.id)
        db.session.add(cash)
        db.session.flush()
    return cash


@views.route('/pnl/add', methods=['POST'])
@login_required
def pnlAdd():
    stock = re.sub(r'[^A-Za-z0-9]', '', request.form.get('stock', '')).strip()[:6].upper()
    if len(stock) < 4:
        return jsonify(rsp='error', message='Stock name is too short'), 400

    try:
        buyPrice = _finite_number(request.form.get('buyPrice'))
        lots = _finite_number(request.form.get('lots'))
    except (TypeError, ValueError):
        return jsonify(rsp='error', message='Buy price and lots must be finite numbers'), 400
    if buyPrice <= 0 or lots <= 0:
        return jsonify(rsp='error', message='Buy price and lots must be positive'), 400

    buyDateStr = request.form.get('buyDate')
    try:
        buyDate = datetime.strptime(buyDateStr, '%Y-%m-%d').date() if buyDateStr else datetime.utcnow().date()
    except ValueError:
        return jsonify(rsp='error', message='Invalid date format'), 400

    # Pembelian ditarik dari cash -- kalau saldonya tidak cukup, posisi
    # tidak dibuat sama sekali (bukan dibuat lalu cash-nya jadi minus).
    cost = buyPrice * lots * 100
    if not math.isfinite(cost):
        return jsonify(rsp='error', message='Transaction value is too large'), 400
    cash = _get_cash()
    if cash.amount + 1e-6 < cost:
        return jsonify(rsp='error', message='Cash tidak cukup: tersedia %s, butuh %s'
                                              % ('{:,.0f}'.format(cash.amount), '{:,.0f}'.format(cost))), 400

    cash.amount -= cost
    db.session.add(Position(
        stock=stock, buyPrice=buyPrice, lots=lots, buyDate=buyDate, userId=current_user.id,
    ))
    db.session.commit()
    return jsonify(rsp='success', message=stock + ' added to positions')


@views.route('/pnl/cash', methods=['POST'])
@login_required
def pnlCash():
    """Simpan saldo cash nganggur -- satu baris CashBalance, dibuat kalau belum ada."""
    try:
        amount = _finite_number(request.form.get('amount'))
    except (TypeError, ValueError):
        return jsonify(rsp='error', message='Cash amount must be a finite number'), 400
    if amount < 0:
        return jsonify(rsp='error', message='Cash amount cannot be negative'), 400

    cash = CashBalance.query.filter_by(userId=current_user.id).first()
    if cash is None:
        cash = CashBalance(amount=amount, userId=current_user.id)
        db.session.add(cash)
    else:
        cash.amount = amount
    db.session.commit()
    return jsonify(rsp='success', message='Cash balance updated')


@views.route('/pnl/edit', methods=['POST'])
@login_required
def pnlEdit():
    """
    `sellPrice`/`sellDate` OPSIONAL -- form edit posisi TERBUKA tidak
    mengirim keduanya (Position.query di atas tetap None/kosong buat
    posisi itu, tidak berubah). Form edit posisi TERTUTUP (perbaiki
    salah input pas Tutup: harga/tanggal jual, atau data belinya)
    mengirim keduanya -- itu satu-satunya cara memperbaiki posisi yang
    sudah dijual selain Hapus permanen (yang membuang riwayat P&L-nya).
    """
    posId = request.form.get('id')
    position = Position.query.filter_by(id=posId, userId=current_user.id).first() if posId else None
    if not position:
        return jsonify(rsp='error', message='Position not found'), 404

    stock = re.sub(r'[^A-Za-z0-9]', '', request.form.get('stock', '')).strip()[:6].upper()
    if len(stock) < 4:
        return jsonify(rsp='error', message='Stock name is too short'), 400

    try:
        buyPrice = _finite_number(request.form.get('buyPrice'))
        lots = _finite_number(request.form.get('lots'))
    except (TypeError, ValueError):
        return jsonify(rsp='error', message='Buy price and lots must be finite numbers'), 400
    if buyPrice <= 0 or lots <= 0:
        return jsonify(rsp='error', message='Buy price and lots must be positive'), 400

    buyDateStr = request.form.get('buyDate')
    try:
        buyDate = datetime.strptime(buyDateStr, '%Y-%m-%d').date() if buyDateStr else position.buyDate
    except ValueError:
        return jsonify(rsp='error', message='Invalid date format'), 400

    sellPrice = position.sellPrice
    sellDate = position.sellDate
    sellPriceStr = request.form.get('sellPrice')
    sellDateStr = request.form.get('sellDate')
    if sellPriceStr is not None or sellDateStr is not None:
        try:
            sellPrice = float(sellPriceStr)
        except (TypeError, ValueError):
            return jsonify(rsp='error', message='Harga jual harus angka terbatas'), 400
        if sellPrice <= 0:
            return jsonify(rsp='error', message='Harga jual harus positif'), 400
        try:
            sellDate = datetime.strptime(sellDateStr, '%Y-%m-%d').date() if sellDateStr else position.sellDate
        except ValueError:
            return jsonify(rsp='error', message='Format tanggal jual salah'), 400
        if sellDate and sellDate < buyDate:
            return jsonify(rsp='error', message='Tanggal jual lebih awal dari tanggal beli'), 400

    # Cash disesuaikan dengan SELISIH, bukan ditulis ulang: posisi terbuka
    # cuma punya sisi beli (delta = invested lama - invested baru), posisi
    # tertutup punya dua sisi (beli & jual) yang dua-duanya bisa berubah
    # lewat form edit posisi tertutup. Kalau saldo hasilnya jadi negatif
    # (mis. lots dinaikkan jauh melebihi cash yang ada), ditolak sebelum
    # apa pun disimpan -- position dan cash harus berubah bersama, bukan
    # position berubah lalu cash menyusul gagal.
    oldInvested = position.buyPrice * position.lots * 100
    wasClosed = bool(position.sellPrice and position.sellDate)
    oldProceeds = (position.sellPrice * position.lots * 100) if wasClosed else 0.0

    newInvested = buyPrice * lots * 100
    willBeClosed = bool(sellPrice and sellDate)
    newProceeds = (sellPrice * lots * 100) if willBeClosed else 0.0

    cashDelta = (oldInvested - newInvested) + (newProceeds - oldProceeds)
    cash = _get_cash()
    if not all(math.isfinite(v) for v in [newInvested, newProceeds, cashDelta, cash.amount + cashDelta]):
        return jsonify(rsp='error', message='Transaction value is too large'), 400
    if cash.amount + cashDelta < -1e-6:
        return jsonify(rsp='error', message='Cash tidak cukup untuk perubahan ini: tersedia %s, butuh %s lagi'
                                              % ('{:,.0f}'.format(cash.amount), '{:,.0f}'.format(-cashDelta - cash.amount))), 400
    cash.amount += cashDelta

    position.stock = stock
    position.buyPrice = buyPrice
    position.lots = lots
    position.buyDate = buyDate
    position.sellPrice = sellPrice
    position.sellDate = sellDate
    db.session.commit()
    return jsonify(rsp='success', message=stock + ' updated')


@views.route('/pnl/close', methods=['POST'])
@login_required
def pnlClose():
    """
    Tutup posisi: isi sellPrice + sellDate, barisnya TETAP tersimpan.

    Ini yang menggantikan "Delete" untuk posisi yang selesai. /pnl/delete
    masih ada, tapi sekarang maknanya sempit -- untuk baris yang salah
    input, bukan untuk posisi yang sudah dijual. Lihat Position di
    models.py soal kenapa riwayatnya tidak boleh hilang.

    `sellLot` opsional -- kalau diisi dan LEBIH KECIL dari lot yang
    dipegang (jual sebagian, bukan seluruh posisi), posisi lama DIPECAH:
    baris ini (`position`) jadi baris TERTUTUP untuk porsi yang dijual
    (lots-nya dikurangi jadi cuma porsi itu), dan baris BARU dibuat untuk
    sisanya yang masih dipegang (lots = sisa, sellPrice/sellDate kosong
    -- tetap terbuka). Tanggal & harga beli porsi yang masih dipegang
    tidak ikut berubah.
    """
    posId = request.form.get('id')
    position = Position.query.filter_by(id=posId, userId=current_user.id).first() if posId else None
    if not position:
        return jsonify(rsp='error', message='Position not found'), 404
    if position.sellDate and position.sellPrice:
        return jsonify(rsp='error', message='Posisi ini sudah ditutup'), 400

    try:
        sellPrice = _finite_number(request.form.get('sellPrice'))
    except (TypeError, ValueError):
        return jsonify(rsp='error', message='Harga jual harus angka terbatas'), 400
    if sellPrice <= 0:
        return jsonify(rsp='error', message='Harga jual harus positif'), 400

    sellDateStr = request.form.get('sellDate')
    try:
        sellDate = (datetime.strptime(sellDateStr, '%Y-%m-%d').date()
                    if sellDateStr else datetime.utcnow().date())
    except ValueError:
        return jsonify(rsp='error', message='Format tanggal salah'), 400
    if position.buyDate and sellDate < position.buyDate:
        return jsonify(rsp='error', message='Tanggal jual lebih awal dari tanggal beli'), 400

    sellLotStr = request.form.get('sellLot')
    sellLot = position.lots
    if sellLotStr not in (None, ''):
        try:
            sellLot = float(sellLotStr)
        except (TypeError, ValueError):
            return jsonify(rsp='error', message='Lot jual harus angka terbatas'), 400
        if sellLot <= 0:
            return jsonify(rsp='error', message='Lot jual harus positif'), 400
        if sellLot > position.lots + 1e-9:
            return jsonify(rsp='error', message='Lot jual (%s) lebih besar dari lot yang dipegang (%s)'
                                                  % (sellLot, position.lots)), 400

    new_cash = _get_cash().amount + sellPrice * sellLot * 100
    if not math.isfinite(new_cash):
        return jsonify(rsp='error', message='Transaction value is too large'), 400

    sisa = position.lots - sellLot
    if sisa > 1e-9:
        db.session.add(Position(
            stock=position.stock, buyPrice=position.buyPrice, lots=sisa,
            buyDate=position.buyDate, userId=position.userId,
        ))
        position.lots = sellLot

    # Hasil jual masuk balik ke cash -- sisi beli sudah didebit waktu
    # /pnl/add, ini pasangannya supaya Total Portfolio (cash + nilai
    # saham) tidak diam-diam menyusut tiap kali posisi ditutup.
    _get_cash().amount = new_cash

    position.sellPrice = sellPrice
    position.sellDate = sellDate
    db.session.commit()
    return jsonify(rsp='success', message=position.stock + ' ditutup')


@views.route('/pnl/delete', methods=['POST'])
@login_required
def pnlDelete():
    """
    Hapus permanen -- untuk baris yang SALAH INPUT.

    Posisi yang benar-benar dijual ditutup lewat /pnl/close supaya
    riwayatnya tinggal; kalau dihapus di sini, catatan hasil sungguhannya
    hilang dan tidak bisa dibuat ulang dari mana pun.
    """
    posId = request.form.get('id')
    position = Position.query.filter_by(id=posId, userId=current_user.id).first() if posId else None
    if not position:
        return jsonify(rsp='error', message='Position not found'), 404

    # Balikkan efek cash-nya sebelum baris hilang -- kalau tidak, debit
    # beli (dan kredit jual, kalau sudah ditutup) tetap tersangkut di
    # cash padahal posisinya sudah tidak ada. Sengaja TIDAK diblokir
    # walau hasilnya bikin cash negatif (mis. menghapus posisi tertutup
    # yang untungnya sudah "dibelanjakan" lewat posisi lain) -- ini
    # koreksi baris salah input, bukan transaksi baru, jadi harus tetap
    # bisa jalan; saldo negatif di situ jadi sinyal ada yang perlu dicek.
    invested = position.buyPrice * position.lots * 100
    wasClosed = bool(position.sellPrice and position.sellDate)
    proceeds = (position.sellPrice * position.lots * 100) if wasClosed else 0.0
    cash = _get_cash()
    updated = cash.amount + invested - proceeds
    if not math.isfinite(updated):
        return jsonify(rsp='error', message='Invalid stored transaction value'), 400
    cash.amount = updated

    db.session.delete(position)
    db.session.commit()
    return jsonify(rsp='success', message='Position removed')


@views.route('/broker-footprint')
@login_required
def brokerFootprint():
    """
    Aggregate broker activity across a whole watchlist over a date range
    — "who's buying/selling the most across everything I'm watching",
    instead of piecing it together one stock at a time.
    """
    watchlists = [
        {'label': 'Portfolio', 'type': 'PortfolioStocks'},
        {'label': 'Best', 'type': 'BestStocks'},
        {'label': 'Best Low', 'type': 'BestLowStocks'},
        {'label': 'Pattern Up', 'type': 'PatternUpStocks'},
    ]
    return render_template(
        "broker_footprint.html",
        user=current_user,
        watchlists=watchlists,
        rangeDate=getRangeDate(),
    )


@views.route('/konsistensi-broker')
@login_required
def konsistensiBroker():
    from .broker_consistency import build
    stock = (request.args.get('stock') or 'ADRO').strip().upper()
    try:
        report = build(stock)
    except ValueError as exc:
        return render_template('konsistensi_broker.html', user=current_user,
                               stock=stock, report=None, error=str(exc)), 400
    backtest = None
    if request.args.get('backtest') == '1':
        from .broker_consistency_backtest import build as backtest_build
        backtest = backtest_build(stock)
    return render_template('konsistensi_broker.html', user=current_user,
                           stock=stock, report=report, error=None, backtest=backtest)


@views.route('/broker-trend')
@login_required
def brokerTrend():
    """One broker's net position in one stock over time — a trend line instead of a single-range snapshot."""
    return render_template("broker_trend.html", user=current_user, rangeDate=getRangeDate())


@views.route('/kepemilikan-saham')
@login_required
def kepemilikanSaham():
    """
    Komposisi kepemilikan satu emiten dari data bulanan KSEI + registri
    pemegang saham IDX. Angkanya diambil per bulan, bukan per hari, jadi
    halaman ini menjawab "siapa yang pegang saham ini dan ke mana
    arahnya" -- bukan pertanyaan harian yang sudah dijawab Broker
    Footprint / Broker Trend.
    """
    return render_template(
        "kepemilikan_saham.html",
        user=current_user,
        defaultStock=(request.args.get('stock') or 'ADRO').strip().upper(),
    )


@views.route('/perbarui-kepemilikan')
@login_required
def perbaruiKepemilikan():
    """
    Menu perawatan data kepemilikan: status tiap sumber (KSEI, registri
    IDX, LBRPE) dibanding bulan yang seharusnya sudah ada, plus tombol
    untuk menariknya -- pengganti `python -m website.ownership ...`.
    Statusnya dimuat lewat AJAX supaya halaman terbuka seketika.
    """
    return render_template("perbarui_kepemilikan.html", user=current_user)


@views.route('/scanner-lab')
@login_required
def scannerLab():
    """
    Hasil delapan script riset sinyal yang selama ini cuma mengendap
    sebagai CSV, diperkaya dengan data kepemilikan KSEI dan broker harian.

    Halaman ini sengaja menampilkan statistik tiap scanner apa adanya --
    termasuk yang kalah dari baseline pasar. Menyembunyikan scanner yang
    hasilnya buruk akan membuat halaman ini menyesatkan.
    """
    return render_template("scanner_lab.html", user=current_user)


@views.route('/saham/<stock>')
@login_required
def stockHub(stock):
    """
    Satu halaman berisi semua yang app ini tahu tentang satu emiten:
    harga, chart, struktur kepemilikan, screen yang menampungnya beserta
    rekam jejak screen itu, dan sinyal scanner yang sedang berjalan.

    Sebelumnya informasi ini tersebar di enam halaman.
    """
    ticker = (stock or '').strip().upper()[:6]
    candle_research = None
    if ticker == 'BRPT':
        import json
        archive = os.path.join(current_app.root_path, 'research_notes',
                               'brpt_candle_2026-11-06.json')
        try:
            with open(archive, encoding='utf-8') as file:
                candle_research = json.load(file)
        except (OSError, ValueError):
            current_app.logger.warning('Arsip riset candle BRPT tidak tersedia', exc_info=True)
    return render_template("stock_hub.html", user=current_user, stock=ticker,
                           candle_research=candle_research,
                           tanggal_riset=tanggal_id(candle_research['snapshot']['date'])
                           if candle_research else None)


@views.route('/kering-screener')
@login_required
def keringScreener():
    """
    Menu untuk bdm_screener_v2.py (<external-tools>/Saham Kering) --
    screener akumulasi bandar dengan panjang window bervariasi.

    Diimpor langsung dari scriptnya (lihat website/kering_screener.py),
    bukan ditulis ulang -- skornya murni trailing jadi "kandidat terbaru"
    otomatis berarti kandidat sungguhan sampai hari ini.

    Dirender lewat stocks_image.html (chart-viewer yang sama dengan
    Watchlist/Screens) alih-alih tabel sendiri, supaya tampilannya
    konsisten -- satu kandidat, satu chart besar, navigasi ‹ ›, kartu
    keputusan di atasnya (yang sekarang H-5 s.d. sekarang, jadi detail
    kesehatan-arus-per-checkpoint yang dulu ada di tabel tidak diulang
    lagi di sini). ?force=1 memicu pemindaian ulang (tombol "Pindai
    Ulang" di page_actions).
    """
    days_back = request.args.get('days_back', 30, type=int)
    force = request.args.get('force') == '1'

    report = kering_report(days_back=days_back, force=force)
    if not report.get('available'):
        flash(report.get('message') or 'Kering Screener tidak tersedia', category='error')
        return render_template("stocks_image.html", user=current_user, tickers=[],
                               context='kering', db_type_name='Kering Screener', rangeDate=getRangeDate())

    candidates = report['candidates']
    tickers = [c['ticker'] for c in candidates]
    focusDates = [c['date'] for c in candidates]
    candidateMeta = [{'skor': c['skor'], 'K': c['K'], 'naik_pct': c['naik_pct']} for c in candidates]

    return render_template(
        "stocks_image.html",
        user=current_user,
        tickers=tickers,
        focusDates=focusDates,
        candidateMeta=candidateMeta,
        context='kering',
        db_type_name='Kering Screener',
        add_targets=['BestStocks', 'BestLowStocks', 'PatternUpStocks'],
        allow_delete=False,
        rangeDate=getRangeDate(),
        keringDaysBack=days_back,
        keringSummary=report['summary'],
        keringKalibrasi=report['kalibrasi'],
        keringConfig=report['config'],
        keringAsOf=report['as_of'],
        keringNEmiten=report['n_emiten'],
        keringStale=report.get('stale', False),
    )


@views.route('/insider-activity')
@login_required
def insiderActivity():
    r"""
    Menu untuk data InsiderActivityAll.py (di <external-tools>/BDM\) --
    transaksi direksi/komisaris/pengendali dari Stockbit, ditarik rutin
    ke <market-data>/Monthly\All\ tapi belum pernah dipakai di app ini.
    """
    return render_template("insider_activity.html", user=current_user)


@views.route('/dicicil-insider')
@login_required
def dicicilInsider():
    """
    Emiten yang dibeli RUTIN oleh orang dalam -- sedikit-sedikit tapi
    berminggu-minggu. Bahan pemantauan, bukan sinyal; lihat dicicil_insider.py.
    """
    return render_template("dicicil_insider.html", user=current_user)


@views.route('/ramai-dibahas')
@login_required
def ramaiDibahas():
    """
    Emiten yang lagi banyak diomongin di Stream Stockbit & forum Telegram.
    Bahan pemantauan, bukan sinyal; lihat ramai_dibahas.py.
    """
    return render_template("ramai_dibahas.html", user=current_user)


@views.route('/kabar-semalam')
@login_required
def kabarSemalam():
    """
    Layar pagi: kabar luar negeri yang sudah final sejak IDX tutup dan saham
    yang kena lampu merah pagi ini. Lihat kabar_semalam.py.
    """
    return render_template("kabar_semalam.html", user=current_user)


@views.route('/rapat-agen')
@login_required
def rapatAgen():
    """
    Rapat agen tanpa LLM: kandidat dekat support + dicicil insider ditimbang
    Analis, Pembantah, Manajer Risiko, Pengamat Pasar, lalu diputus Hakim dan
    dicatat Notulen. Lihat rapat_agen.py.
    """
    return render_template("rapat_agen.html", user=current_user)


@views.route('/radar-insider')
@login_required
def radarInsider():
    """
    insider_activity.py dibaca dalam konteks, bukan sendirian -- insider
    BELI polos nyaris tidak ada informasi (win 49,5%), tapi disilang sama
    Jatuh Dalam atau Akumulasi Palsu jadi konfirmasi nyata. Insider JUAL
    diuji arah kebalik: bukan "menyebabkan turun", tapi peringatan dini
    saham itu lebih mungkin jatuh dalam 40 hari ke depan. Status kalibrasi,
    bukan teruji -- lihat insider_signal.py.
    """
    return render_template("radar_insider.html", user=current_user)


@views.route('/watchlist-digest')
@login_required
def watchlistDigest():
    """
    Menyilangkan Portfolio/Best/Best Low/Pattern Up dengan Scanner Lab,
    Kering Screener, Screen Eval, Kesehatan Arus, dan Aktivitas Insider --
    "dari saham yang saya pantau, mana yang hari ini punya sesuatu yang
    layak dilihat?" tanpa membuka lima halaman terpisah.
    """
    return render_template("watchlist_digest.html", user=current_user)


@views.route('/jurnal-keputusan')
@login_required
def decisionJournal():
    """
    "Waktu Anda menambah saham ini ke watchlist, kartu keputusannya
    bilang apa -- dan apa yang terjadi sejak itu." Bukan backtest pasar
    (itu sudah dijawab modul lain); ini tentang kalibrasi keputusan
    ANDA SENDIRI dari waktu ke waktu, dibaca dari DecisionSnapshot yang
    ditangkap admin() setiap kali menambah saham ke Portfolio/Best/Best
    Low/Pattern Up (lihat decision_journal.py).
    """
    return render_template("decision_journal.html", user=current_user)


@views.route('/serapan-float')
@login_required
def serapanFloat():
    """
    Arus broker harian dibagi float scripless KSEI -- dua data terbesar app
    ini yang selama ini tidak pernah dikalikan. Lihat float_squeeze.py: tesis
    "float mengering = bullish" diuji lebih dulu dan DITOLAK datanya; yang
    berarti ternyata tandanya (melepas vs menyerap), bukan besarnya.
    """
    return render_template("serapan_float.html", user=current_user)


@views.route('/akumulasi-palsu')
@login_required
def akumulasiPalsu():
    """
    Kapan "Top5 net beli" sebenarnya tidak berarti apa-apa. Hipotesis awal
    (deteksi lewat pelebaran jumlah broker penjual) diuji dan gagal; yang
    memisahkan justru posisi harga. Lihat fake_accumulation.py.
    """
    return render_template("akumulasi_palsu.html", user=current_user)


@views.route('/jatuh-dalam')
@login_required
def jatuhDalam():
    """
    Emiten yang harganya sudah jauh di bawah puncak 120 harinya.

    Halaman ini lahir dari hipotesis yang GAGAL: "cari saham yang naik
    banyak setelah harganya melandai". Melandai diuji pada 15 kombinasi
    ambang x horizon di dua sampel dan justru menurunkan peluang rally di
    semuanya. Yang bertahan cuma sisi "sudah jatuh"-nya. Lihat
    jatuh_dalam.py.
    """
    return render_template("jatuh_dalam.html", user=current_user)


@views.route('/tembus-basis')
@login_required
def tembusBasis():
    """
    Emiten yang keluar dari basis harga tenang atau mencetak puncak 52
    minggu, dengan volume >2x rata-rata.

    Lahir dari hipotesis yang GAGAL: "harga tenang 30 hari -> lebih mungkin
    naik" diuji di ~750 emiten likuid dan justru menurunkan peluangnya.
    Yang bertahan di luar sampel adalah SAAT basis tenang itu ditembus.
    Lihat tembus_basis.py.
    """
    return render_template("tembus_basis.html", user=current_user)


@views.route('/skor-kecondongan')
@login_required
def skorKecondongan():
    """
    Peringkat harian semua emiten layak dari dua ukuran yang sudah lolos
    luar sampel: dekat puncak 52 minggu dan tenang. Yang paling kokoh sisi
    bawahnya (desil 1 = hindari). Lihat kecondongan.py dan
    riset_pola_naik/skor.py.
    """
    return render_template("kecondongan.html", user=current_user)


@views.route('/tembus-basis/chart')
@login_required
def tembusBasisChart():
    """
    Chart sinyal hari bursa terakhir dan kemarin -- dua hari yang masih
    sesuai aturan masuk yang diuji (beli di close hari setelah sinyal).
    Viewer yang sama dengan Watchlist dan Penemu Pola, ditandai di tanggal
    sinyalnya.
    """
    from .tembus_basis import sinyal_terbaru

    sinyal = sinyal_terbaru(umur_max=1)
    if not sinyal:
        flash('Tidak ada sinyal Tembus Basis di hari bursa terakhir atau kemarin.', category='error')
        return redirect(url_for('views.tembusBasis'))

    return render_template(
        "stocks_image.html",
        user=current_user,
        tickers=[s for s, _ in sinyal],
        focusDates=[d for _, d in sinyal],
        context='tembus',
        db_type_name='Tembus Basis',
        add_targets=['BestStocks', 'BestLowStocks', 'PatternUpStocks'],
        allow_delete=False,
        rangeDate=getRangeDate(),
    )


@views.route('/penemu-pola')
@login_required
def penemuPola():
    """
    Menguji ribuan kombinasi metrik secara otomatis dengan koreksi
    pengujian-berganda (Benjamini-Hochberg), alih-alih menebak satu
    hipotesis lalu mengujinya dengan tangan. Lihat pattern_miner.py.
    """
    return render_template("penemu_pola.html", user=current_user)


@views.route('/penemu-pola/saham')
@login_required
def penemuPolaSaham():
    """
    Chart semua emiten yang HARI INI jatuh di keranjang satu pola.

    Dirender lewat stocks_image.html -- viewer yang sama dengan Watchlist
    dan Kering Screener -- bukan daftar kode. Daftar kode masih menyisakan
    langkah manual (klik satu, balik, klik lagi) untuk pertanyaan yang
    sebenarnya cuma satu: "yang kena pola ini kelihatannya bagaimana".
    """
    from .pattern_miner import saham_pola

    temuan = saham_pola(request.args.get('k'))
    if not temuan or not temuan.get('saham'):
        flash('Pola itu tidak punya emiten yang cocok hari ini.', category='error')
        return redirect(url_for('views.penemuPola'))

    return render_template(
        "stocks_image.html",
        user=current_user,
        tickers=temuan['saham'],
        context='pola',
        db_type_name=temuan['label'],
        add_targets=['BestStocks', 'BestLowStocks', 'PatternUpStocks'],
        allow_delete=False,
        rangeDate=getRangeDate(),
        polaTemuan=temuan,
    )


@views.route('/sidik-jari-broker')
@login_required
def sidikJariBroker():
    """
    Mengelompokkan broker menurut CARA mereka berdagang (kontrarian vs
    momentum, sabar vs cepat, fokus vs sebar), bukan menurut berapa lot
    hari ini. Lihat broker_fingerprint.py.
    """
    return render_template("sidik_jari_broker.html", user=current_user)


@views.route('/rontgen-portofolio')
@login_required
def rontgenPortofolio():
    """
    Menjalankan isi portofolio melewati SEMUA kalibrasi app ini (Lensa
    Keramaian, Akumulasi Palsu, Serapan Float, Kesehatan Arus, Kering
    Screener) lalu menjumlahkannya jadi satu potret, dibobot modal nyata
    dari tabel Position. Lihat portfolio_xray.py.
    """
    return render_template("rontgen_portofolio.html", user=current_user)


@views.route('/kepercayaan-data')
@login_required
def kepercayaanData():
    """
    Skor kelengkapan data per emiten -- supaya angka yang dihitung dari
    data bolong bisa dibedakan dari yang tegak. Lihat data_confidence.py.
    """
    return render_template("kepercayaan_data.html", user=current_user)


@views.route('/audit-screener')
@login_required
def auditScreener():
    """
    Recall, bukan presisi: dari semua rally besar yang benar-benar terjadi,
    berapa yang sempat ditandai Kering Screener -- dan kriteria mana yang
    paling sering menggagalkan yang terlewat. Lihat signal_recall.py.
    """
    return render_template("audit_screener.html", user=current_user)


@views.route('/research')
@login_required
def research():
    """
    Laboratorium riset: eksperimen yang jalannya menit sampai puluhan menit,
    dengan log langsung dan riwayat hasil. Beda dari halaman lain yang
    semuanya menghitung ulang di dalam satu request -- lihat research.py
    soal kenapa pola cache-pickle biasa tidak muat untuk ini.

    Eksperimen pertama: RL Trading (rl_trading.py) -- satu kebijakan yang
    memutuskan sekaligus saham mana, porsinya, TP/SL-nya, dan lama hold-nya,
    diuji walk-forward terhadap beli-tahan dan kebijakan acak.
    """
    return render_template("research.html", user=current_user)


@views.route('/digital-twin')
@login_required
def digitalTwin():
    """
    Market Digital Twin: klon digital beberapa saham BEI yang dijalankan
    ribuan agen berpersona (ritel, institusi lokal, asing, bandar, pedagang
    cepat), dikalibrasi dari data project. Menjawab "bagaimana JIKA ..."
    dengan membandingkan dunia tanpa dan dengan skenario -- bukan ramalan.
    Mesinnya di website/twin/, jalannya lewat kerangka riset latar belakang
    (research.py) karena satu run Monte Carlo makan puluhan detik.
    """
    return render_template("digital_twin.html", user=current_user)


@views.route('/takaran-risiko')
@login_required
def takaranRisiko():
    """
    Seberapa keras sebuah emiten akan berayun, bukan ke mana.

    Satu-satunya kalibrasi di app ini yang LOLOS uji luar sampel:
    korelasi kelipatan risiko antar sampel +0,90, kelipatan peluang
    +0,95 -- sementara ARAH korelasinya -0,31 (menyesatkan, bukan
    sekadar lemah). Lihat risiko.py.
    """
    return render_template("takaran_risiko.html", user=current_user)


@views.route('/emiten-hilang')
@login_required
def emitenHilang():
    """
    Siapa yang berhenti mengirim data, dan dalam keadaan apa.

    Mengukur lubang survivorship yang merusak backtest menu lain --
    terutama Jatuh Dalam, karena emiten yang jatuh dalam lalu disuspend
    permanen adalah persis kelompok yang hilang dari data. Lihat
    survivorship.py.
    """
    return render_template("emiten_hilang.html", user=current_user)


@views.route('/apa-berubah')
@login_required
def apaBerubah():
    """
    Emiten mana yang MASUK dan KELUAR tiap layar sejak hari bursa
    sebelumnya -- supaya membaca app ini tidak berarti membuka sembilan
    belas menu dan mengingat sendiri isi kemarin. Lihat perubahan.py.
    """
    return render_template("apa_berubah.html", user=current_user)


@views.route('/status-bukti')
@login_required
def statusBukti():
    """
    Untuk tiap menu: temuannya pernah diuji di luar tempat dia lahir
    atau belum. Dirender server-side karena datanya tabel tetap, bukan
    hasil hitungan. Lihat status_bukti.py.
    """
    from .status_bukti import ringkasan
    return render_template("status_bukti.html", user=current_user, data=ringkasan())


@views.route('/stocklang')
@login_required
def stocklangPage():
    """
    Editor StockLang di browser: ketik skrip, Run, lihat keluaran + grafik.
    Bahasanya di stocklang/, jalannya lewat stocklang_web.py.
    """
    from .stocklang_web import contoh
    return render_template("stocklang.html", user=current_user, contoh=contoh())


@views.route('/stocklang/run', methods=['POST'])
@login_required
def stocklangRun():
    from .stocklang_web import jalankan
    src = (request.get_json(silent=True) or {}).get('src', '')
    return jsonify(jalankan(str(src)))


@views.route('/stocklang/tulis', methods=['POST'])
@login_required
def stocklangTulis():
    """Permintaan bahasa biasa -> skrip StockLang lewat Claude (berbayar), langsung dicoba jalan."""
    from .stocklang_web import tulis
    teks = (request.get_json(silent=True) or {}).get('teks', '')
    return jsonify(tulis(str(teks)))


@views.route('/sebaran-kabar')
@login_required
def sebaranKabar():
    """
    Sebaran Kabar: bagaimana satu kabar tentang emiten menyebar di komunitas
    investor -- siapa ikut beli, siapa masuk telat, kapan orang dalam keluar.
    Model berbasis agen tanpa LLM, disetel dari Ramai Dibahas, KSEI, dan
    Summary. Pelengkap Digital Twin (narasi, bukan harga). Lihat sebaran/.
    """
    from .sebaran import daftar_kabar
    kode = re.sub(r'[^A-Z0-9]', '', request.args.get('kode', '').upper())[:6]
    return render_template("sebaran_kabar.html", user=current_user,
                           kabar=daftar_kabar(), kode=kode)


@views.route('/sebaran-kabar/konteks')
@login_required
def sebaranKabarKonteks():
    from .sebaran import konteks_emiten
    return jsonify(konteks_emiten(request.args.get('kode', '')))


@views.route('/sebaran-kabar/jalankan', methods=['POST'])
@login_required
def sebaranKabarJalankan():
    from .sebaran import jalankan
    return jsonify(jalankan(request.get_json(silent=True) or {}))


@views.route('/stocklang/skrip')
@login_required
def stocklangDaftarSkrip():
    from .stocklang_web import daftar_skrip
    return jsonify(daftar_skrip())


@views.route('/stocklang/skrip/<nama>')
@login_required
def stocklangMuatSkrip(nama):
    from .stocklang_web import muat_skrip
    s = muat_skrip(nama)
    return (jsonify(s), 200) if s else (jsonify({'error': 'skrip tidak ditemukan'}), 404)


@views.route('/stocklang/skrip/simpan', methods=['POST'])
@login_required
def stocklangSimpanSkrip():
    from .stocklang_web import simpan_skrip
    d = request.get_json(silent=True) or {}
    ok, pesan = simpan_skrip(str(d.get('nama', '')).strip(), str(d.get('src', '')), bool(d.get('jurnal')))
    return jsonify({'ok': ok, 'pesan': pesan})


@views.route('/stocklang/skrip/hapus', methods=['POST'])
@login_required
def stocklangHapusSkrip():
    from .stocklang_web import hapus_skrip
    d = request.get_json(silent=True) or {}
    return jsonify({'ok': hapus_skrip(str(d.get('nama', '')))})


@views.route('/stocklang/jurnal')
@login_required
def stocklangJurnal():
    from .stocklang_jurnal import evaluasi
    return jsonify(evaluasi())


@views.route('/stocklang/laporan-data')
@login_required
def stocklangLaporanData():
    """Laporan harian StockLang yang disimpan kesehatan.py; ikut ekspor HP (menu 'stocklang')."""
    from .stocklang_laporan import baca
    return jsonify(baca())


@views.route('/stocklang/jurnal/catat', methods=['POST'])
@login_required
def stocklangCatatJurnal():
    """Sama dengan yang dijalankan kesehatan.py tiap hari; aman diulang (tidak dobel)."""
    from .stocklang_jurnal import catat
    return jsonify(catat())


@views.route('/kalender-pasar')
@login_required
def kalenderPasar():
    return render_template('agenda_pasar.html', user=current_user, kind='kalender', title='Kalender Pasar')


@views.route('/agenda-emiten')
@login_required
def agendaEmiten():
    return render_template('agenda_pasar.html', user=current_user, kind='emiten', title='Agenda Emiten')


@views.route('/rotasi-sektor')
@login_required
def rotasiSektor():
    return render_template('rotasi_sektor.html', user=current_user)


@views.route('/musiman-saham')
@login_required
def musiman_saham_page():
    return render_template('histori_emiten.html', user=current_user, kind='musiman_saham',
                           title='Musiman Saham', endpoint='/musiman-saham-data')


@views.route('/perubahan-kepemilikan')
@login_required
def perubahan_kepemilikan_page():
    return render_template('histori_emiten.html', user=current_user, kind='perubahan_kepemilikan',
                           title='Perubahan Kepemilikan', endpoint='/perubahan-kepemilikan-data')
