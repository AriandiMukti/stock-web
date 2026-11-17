from .models import scoped_query
from flask_login import current_user
"""
Rontgen portofolio: menjalankan isi portofolio Anda melewati SEMUA kalibrasi
yang sudah dimiliki app ini, lalu menjumlahkannya jadi satu potret.

KENAPA INI ADA
App ini punya banyak kalibrasi historis -- Lensa Keramaian (grid volume x
nilai), Akumulasi Palsu (grid harga x arus), Serapan Float, Kesehatan Arus,
Kering Screener -- tapi semuanya menjawab per saham. Tidak ada satu layar
pun yang menjawab pertanyaan yang sebenarnya paling penting:

    "Menurut app saya sendiri, portofolio saya sekarang seperti apa?"

Ringkasan Watchlist menampilkan baris per saham, tapi tidak pernah
menjumlahkannya. Padahal punya 3 saham yang semuanya duduk di sel terburuk
itu keadaan yang sangat berbeda dari punya 3 saham yang tersebar.

DIBOBOT MODAL, BUKAN JUMLAH SAHAM
Kalau ada posisi sungguhan (tabel Position: lot + harga beli), pembobotannya
memakai NILAI PASAR SEKARANG (lot x 100 x harga terakhir). Rata-rata biasa
akan menyesatkan: saham yang isinya 5% modal tidak boleh dihitung sama berat
dengan yang isinya 60%. Kalau belum ada posisi sungguhan, jatuh ke watchlist
Portfolio dengan bobot sama rata, dan itu dinyatakan apa adanya di hasilnya.

ANGKA UTAMANYA: WIN RATE TERTIMBANG
Tiap kalibrasi menempatkan saham pada satu sel yang punya win rate historis.
Angka utama halaman ini adalah rata-rata tertimbang modal dari win rate
sel-sel itu, dibandingkan baseline pasar.

    "Portofolio Anda duduk di sel-sel yang historisnya win 31%,
     sementara baseline pasar di periode yang sama 36,5%."

BATASNYA -- PENTING
- Ini BUKAN ramalan. Win rate sel adalah rata-rata KELOMPOK dari periode
  Jan-Sep 2026 yang didominasi pasar turun. Portofolio yang "duduk di sel
  bagus" tetap bisa rugi, dan sebaliknya.
- Kalibrasinya belum pernah diuji di luar sampel (dikalibrasi dan dinilai
  pada 8 bulan yang sama), jadi sebagian mungkin kebetulan.
- Angka tertimbang menyembunyikan sebaran: dua portofolio dengan rata-rata
  sama bisa sangat berbeda isinya. Karena itu tabel per saham tetap
  ditampilkan di bawah ringkasannya, bukan diganti olehnya.
"""
import time

BASELINE_PASAR = 36.5  # win rate baseline 40 hari, sama dengan fake_accumulation


def _holdings():
    """
    (daftar_holding, sumber, catatan). Posisi sungguhan didahulukan;
    kalau kosong, pakai watchlist Portfolio dengan bobot sama rata.
    """
    from .models import Position, PortfolioStocks

    posisi = Position.query.filter_by(userId=current_user.id).all()
    if posisi:
        out = []
        for p in posisi:
            if not p.stock:
                continue
            out.append({
                'stock': p.stock.strip().upper(),
                'lots': float(p.lots or 0),
                'buy_price': float(p.buyPrice or 0),
                'buy_date': p.buyDate.isoformat() if p.buyDate else None,
            })
        if out:
            return out, 'posisi', 'Dibobot nilai pasar posisi sungguhan (tabel Position).'

    tickers = sorted({s.data.strip().upper() for s in scoped_query(PortfolioStocks).all() if s.data})
    return ([{'stock': t, 'lots': None, 'buy_price': None, 'buy_date': None} for t in tickers],
            'watchlist',
            'Belum ada posisi sungguhan di Portfolio P&L, jadi memakai watchlist '
            'Portfolio dengan bobot SAMA RATA -- bukan bobot modal.')


def build(days_fake=20, days_float=60):
    """Potret portofolio lengkap. Selalu mengembalikan dict siap-render."""
    from .crowding import measure as crowd_measure
    from .fake_accumulation import measure as fake_measure
    from .float_squeeze import measure as float_measure, scripless_map
    from .flow_health import check_current

    holdings, sumber, catatan = _holdings()
    if not holdings:
        return {'available': False,
                'message': 'Portfolio kosong -- belum ada posisi maupun saham di watchlist Portfolio.'}

    # Kandidat Kering Screener diambil sekali (hasilnya sudah di-cache modulnya)
    kering_set = set()
    try:
        from .kering_screener import build_report
        rep = build_report()
        if rep.get('available'):
            kering_set = {c['ticker'] for c in rep.get('candidates', [])}
    except Exception:
        pass

    smap = {}
    try:
        smap = scripless_map()
    except Exception:
        pass

    rows = []
    for h in holdings:
        stock = h['stock']
        row = dict(h)

        crowd = None
        fake = None
        floatx = None
        flow = None
        try:
            crowd = crowd_measure(stock)
        except Exception:
            pass
        try:
            fake = fake_measure(stock, days=days_fake)
        except Exception:
            pass
        try:
            floatx = float_measure(stock, days=days_float, scripless_info=smap.get(stock))
        except Exception:
            pass
        try:
            flow = check_current(stock)
        except Exception:
            pass
        # Takaran Risiko sengaja dipanggil di sini, bukan dihitung ulang:
        # angka yang muncul di halaman ini harus SAMA PERSIS dengan yang
        # muncul di Halaman Saham dan Takaran Risiko. Satu perhitungan,
        # satu tempat -- lihat risiko.untuk_ticker().
        takaran = None
        try:
            from .risiko import untuk_ticker as risiko_ticker
            takaran = risiko_ticker(stock)
        except Exception:
            pass

        harga = None
        for src in (fake, crowd, floatx):
            if src and src.get('last_close') is not None:
                harga = src['last_close']
                break
            if src and src.get('close') is not None:
                harga = src['close']
                break

        lots = h.get('lots')
        nilai_sekarang = (lots * 100.0 * harga) if (lots and harga) else None
        nilai_modal = (lots * 100.0 * h['buy_price']) if (lots and h.get('buy_price')) else None

        row.update({
            'last_close': harga,
            'nilai_sekarang': nilai_sekarang,
            'nilai_modal': nilai_modal,
            'pnl_pct': (round((harga - h['buy_price']) / h['buy_price'] * 100.0, 2)
                        if (harga and h.get('buy_price')) else None),

            'crowd_verdict': crowd.get('verdict') if crowd else None,
            'crowd_label': crowd.get('verdict_label') if crowd else None,
            'crowd_win': crowd.get('cell_win_rate') if crowd else None,
            'crowd_vs': crowd.get('vs_baseline') if crowd else None,

            'fake_cell': fake.get('cell') if fake else None,
            'fake_win': fake.get('cell_win') if fake else None,
            'fake_vs': fake.get('vs_baseline') if fake else None,
            'fake_verdict': fake.get('verdict') if fake else None,
            'is_fake': bool(fake.get('is_fake')) if fake else False,
            'is_best': bool(fake.get('is_best')) if fake else False,

            'float_bucket': floatx.get('bucket') if floatx else None,
            'float_label': floatx.get('label') if floatx else None,
            'float_pct': floatx.get('absorption_pct') if floatx else None,

            'flow_label': flow.get('label') if (flow and flow.get('available')) else None,
            'flow_arah': flow.get('arah_arus') if (flow and flow.get('available')) else None,

            'kering': stock in kering_set,

            'x_rugi': takaran.get('x_rugi') if takaran else None,
            'x_naik': takaran.get('x_naik') if takaran else None,
            'risiko_label': takaran.get('label') if takaran else None,
            'risiko_verdict': takaran.get('verdict') if takaran else None,
            'volat': takaran.get('volat') if takaran else None,
        })
        rows.append(row)

    # ---- Pembobotan ----
    total_nilai = sum(r['nilai_sekarang'] or 0 for r in rows)
    pakai_modal = sumber == 'posisi' and total_nilai > 0
    for r in rows:
        if pakai_modal:
            r['bobot'] = (r['nilai_sekarang'] or 0) / total_nilai
        else:
            r['bobot'] = 1.0 / len(rows)
        r['bobot_pct'] = round(r['bobot'] * 100, 1)

    def tertimbang(key):
        """Rata-rata tertimbang; hanya baris yang punya nilai ikut dihitung,
        lalu bobotnya dinormalkan ulang supaya tidak bias ke bawah."""
        pakai = [r for r in rows if r.get(key) is not None]
        w = sum(r['bobot'] for r in pakai)
        if not pakai or w <= 0:
            return None, 0.0
        return round(sum(r[key] * r['bobot'] for r in pakai) / w, 1), round(w * 100, 1)

    fake_win, fake_cover = tertimbang('fake_win')
    crowd_win, crowd_cover = tertimbang('crowd_win')

    def eksposur(key, nilai):
        return round(sum(r['bobot'] for r in rows if r.get(key) == nilai) * 100, 1)

    def eksposur_bool(key):
        return round(sum(r['bobot'] for r in rows if r.get(key)) * 100, 1)

    # Penyumbang risiko: bobot x seberapa jauh selnya di bawah baseline
    penyumbang = []
    for r in rows:
        if r.get('fake_vs') is None:
            continue
        if r['fake_vs'] >= 0:
            continue
        penyumbang.append({
            'stock': r['stock'],
            'bobot_pct': r['bobot_pct'],
            'fake_cell': r['fake_cell'],
            'fake_vs': r['fake_vs'],
            'dampak': round(r['bobot'] * abs(r['fake_vs']), 2),
        })
    penyumbang.sort(key=lambda x: -x['dampak'])

    # ---- Sumbangan risiko: porsi MODAL vs porsi RISIKO ----
    #
    # Ini menjawab pertanyaan yang tidak dijawab bagian mana pun di atas.
    # Semua kalibrasi lain di halaman ini soal ARAH ("selnya historisnya
    # win berapa persen") -- dan arah adalah hal yang berkali-kali gagal
    # direplikasi di app ini. Besaran ayunan sebaliknya: korelasi antar
    # sampel +0,90 (lihat risiko.BUKTI). Jadi bagian inilah satu-satunya
    # di halaman ini yang berdiri di atas temuan yang lolos luar sampel.
    #
    # Sumbangan risiko = bobot modal x kelipatan risiko, dinormalkan.
    # Dua posisi berbobot 20% tidak menyumbang risiko sama besar kalau
    # yang satu 0,4x dan yang lain 1,8x.
    punya_risiko = [r for r in rows if r.get('x_rugi')]
    total_x = sum(r['bobot'] * r['x_rugi'] for r in punya_risiko)
    risiko_baris = []
    for r in punya_risiko:
        sumbang = (r['bobot'] * r['x_rugi'] / total_x) if total_x > 0 else None
        r['risiko_pct'] = round(sumbang * 100, 1) if sumbang is not None else None
        # Selisih inilah yang layak dilihat: modal 15% tapi risiko 38%.
        r['risiko_vs_modal'] = (round(r['risiko_pct'] - r['bobot_pct'], 1)
                                if r['risiko_pct'] is not None else None)
        risiko_baris.append({
            'stock': r['stock'], 'bobot_pct': r['bobot_pct'],
            'risiko_pct': r['risiko_pct'], 'selisih': r['risiko_vs_modal'],
            'x_rugi': r['x_rugi'], 'x_naik': r['x_naik'],
            'label': r['risiko_label'], 'verdict': r['risiko_verdict'],
        })
    risiko_baris.sort(key=lambda x: -(x['risiko_pct'] or 0))

    cakupan_risiko = round(sum(r['bobot'] for r in punya_risiko) * 100, 1)
    x_rugi_porto = (round(total_x / sum(r['bobot'] for r in punya_risiko), 2)
                    if punya_risiko else None)
    x_naik_porto = (round(sum(r['bobot'] * r['x_naik'] for r in punya_risiko if r.get('x_naik'))
                          / sum(r['bobot'] for r in punya_risiko if r.get('x_naik')), 2)
                    if any(r.get('x_naik') for r in punya_risiko) else None)
    # Berapa banyak risiko yang duduk di tiga posisi teratas -- ukuran
    # kepadatan yang tidak terlihat dari bobot modal saja.
    tiga_teratas = round(sum(x['risiko_pct'] or 0 for x in risiko_baris[:3]), 1)

    rows.sort(key=lambda r: -(r['bobot'] or 0))

    return {
        'available': True,
        'sumber': sumber,
        'catatan': catatan,
        'dibobot_modal': pakai_modal,
        'rows': rows,
        'n': len(rows),
        'total_nilai': total_nilai if pakai_modal else None,
        'total_modal': (sum(r['nilai_modal'] or 0 for r in rows) if pakai_modal else None),
        'baseline': BASELINE_PASAR,
        'fake_win': fake_win,
        'fake_cover': fake_cover,
        'fake_vs_baseline': (round(fake_win - BASELINE_PASAR, 1) if fake_win is not None else None),
        'crowd_win': crowd_win,
        'crowd_cover': crowd_cover,
        'eksposur': {
            'sel_terburuk': eksposur_bool('is_fake'),
            'sel_terbaik': eksposur_bool('is_best'),
            'bandar_melepas': eksposur('float_bucket', 'distribusi'),
            'serapan_ringan': eksposur('float_bucket', 'ringan'),
            'ramai_sangat_jauh': eksposur('crowd_verdict', 'sangat_jauh'),
            'ramai_jauh': eksposur('crowd_verdict', 'jauh'),
            'kandidat_kering': eksposur_bool('kering'),
        },
        'penyumbang_risiko': penyumbang[:10],
        'takaran': {
            'baris': risiko_baris,
            'cakupan': cakupan_risiko,
            'x_rugi': x_rugi_porto,
            'x_naik': x_naik_porto,
            'tiga_teratas': tiga_teratas,
            'catatan': (
                'Satu-satunya bagian halaman ini yang berdiri di atas temuan yang LOLOS uji '
                'luar sampel (korelasi kelipatan risiko antar sampel +0,90). Bagian lain di '
                'halaman ini soal arah, dan arah berkali-kali gagal direplikasi. '
                'Lihat Status Bukti.'),
        },
        'days_fake': days_fake,
        'days_float': days_float,
        'as_of': time.strftime('%Y-%m-%d %H:%M'),
    }
