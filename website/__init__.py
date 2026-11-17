from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from os import path
from flask_login import LoginManager
import os
import threading



db = SQLAlchemy()
csrf = CSRFProtect()
DB_NAME = "database.db"

def create_app(warm_cache=False, test_config=None):
    from .runtime_paths import RUNTIME_DIR, PROJECT_DIR, prepare_runtime
    from pathlib import Path
    from sqlalchemy.engine import make_url
    app = Flask(__name__, instance_path=str(RUNTIME_DIR / 'databases'))
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL') or
            'sqlite:///' + (RUNTIME_DIR / 'databases' / DB_NAME).as_posix(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1',
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE='Lax',
        REMEMBER_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1',
        DREAM_AGENT_WORKER_ENABLED=os.environ.get('DREAM_AGENT_WORKER_ENABLED') == '1',
        DEMO_MODE=(RUNTIME_DIR / 'data' / 'demo-provenance.json').is_file(),
    )
    if test_config is not None:
        app.config.update(test_config)
    secret = app.config.get('SECRET_KEY')
    if not isinstance(secret, str) or (not app.testing and len(secret) < 32):
        raise ValueError('Set SECRET_KEY to a randomly generated value of at least 32 characters')
    database_url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
    if database_url.get_backend_name() == 'sqlite' and database_url.database not in {None, '', ':memory:'}:
        database_path = Path(database_url.database)
        if not database_path.is_absolute():
            database_path = Path(app.instance_path) / database_path
        if database_path.resolve().is_relative_to(PROJECT_DIR):
            raise ValueError('SQLite database must be outside the source-code directory')
    prepare_runtime()


    db.init_app(app)
    csrf.init_app(app)

    from .views import views
    from .auth import auth
    from .utilities import utilities
    
    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')
    app.register_blueprint(utilities, url_prefix='/')

    from .dream_agent_web import dream_agent_web
    app.register_blueprint(dream_agent_web)

    from .ema_weekly import ema_weekly
    app.register_blueprint(ema_weekly)

    @app.context_processor
    def inject_data_provenance():
        return {'demo_mode': app.config['DEMO_MODE']}

    @app.after_request
    def mark_demo_responses(response):
        if app.config['DEMO_MODE']:
            response.headers['X-Data-Provenance'] = 'synthetic-demo'
        return response

    from .models import User, Note, stockList

    @app.context_processor
    def inject_stock_list():
        # Powers the "/" quick-search command palette in base.html, which
        # needs the full recognized-ticker universe on every page, not
        # just whatever subset a given view's own tickers list contains.
        return dict(all_stocks=stockList)

    @app.context_processor
    def inject_kesegaran_data():
        # Chip "data s/d ..." di topbar tiap halaman. fakta_data() di-cache
        # 10 menit, jadi ini tidak membaca berkas di setiap render.
        # data_basi: lebih dari 4 hari kalender -- akhir pekan plus satu
        # hari libur masih wajar, lebih dari itu unduhan hariannya macet.
        try:
            from datetime import date
            from .views import fakta_data, tanggal_id
            fd = fakta_data()
            sampai = fd.get('data_sampai')
            basi = bool(sampai) and (date.today() - date.fromisoformat(sampai)).days > 4
            return dict(data_sampai=sampai, data_sampai_id=tanggal_id(sampai), data_basi=basi)
        except Exception:
            return dict(data_sampai=None, data_sampai_id=None, data_basi=False)

    create_database(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        try:
            return db.session.get(User, int(id))
        except (TypeError, ValueError):
            return None

    if warm_cache:
        _start_cache_warmup(app)

    from .dream_agent.worker import install as install_dream_worker
    install_dream_worker(app)

    return app


def _start_cache_warmup(app):
    """
    Memanaskan cache Scanner Lab / Kering Screener / Screen Eval di
    background begitu server start, supaya PENGUNJUNG PERTAMA tidak
    kena cold-scan ~60 detik (nyata terjadi: Watchlist/Screens dan
    Halaman Saham sama-sama memanggil build_hub() -> cached_scan()).

    Memanaskan SEMUA days_back yang dipakai app ini: 14 (Ringkasan
    Watchlist), 60 (Scanner Lab), 90 (Halaman Saham, kartu keputusan di
    Watchlist/Screens). live_scan.py:cached_scan() dulu cuma punya SATU
    file cache dipakai bersama -- days_back yang beda saling menimpa,
    jadi membuka Ringkasan Watchlist lalu Watchlist biasa langsung
    memicu pemindaian ulang penuh (~48-60 detik), dan karena dev server
    Flask satu-thread, itu memblokir SELURUH app selama itu (nyata
    dilaporkan sebagai "aplikasi jadi tidak responsif"). Sudah diperbaiki
    supaya tiap days_back punya file cache sendiri -- baris di bawah
    memanaskan ketiganya sekali di awal supaya tidak ada yang kosong.
    Kering Screener & Screen Eval cache-nya tunggal (tidak bergantung
    parameter), jadi memanaskan keduanya selalu membantu di mana pun
    dipakai.

    CATATAN reloader: main.py sengaja TIDAK memakai use_reloader=False
    supaya auto-reload Werkzeug tetap jalan (server otomatis restart
    sendiri saat file .py berubah, tidak perlu direstart manual) --
    sempat dicoba dimatikan untuk menghindari pemanasan ganda, tapi
    trade-off-nya (harus restart manual tiap ubah kode) lebih mahal
    daripada boros ~60 detik CPU background sekali di awal. Akibatnya:
    dengan debug=True + reloader aktif, create_app() terpanggil dua
    kali (proses pemantau reloader, lalu proses child-nya) dan
    pemanasan ini BISA jalan dua kali -- tidak merusak apa pun (cache-
    nya idempoten, ditimpa ulang saja), cuma boros waktu CPU sesaat.
    Kedua launch config khusus testing (bdm-flask, bdm-flask-nologin)
    tetap eksplisit set use_reloader=False (tidak diubah), jadi di situ
    tidak ada pemanasan ganda -- tapi juga tidak ada auto-reload, sesuai
    kebutuhan alur kerja testing lewat tool ini.
    """
    def _warm():
        import time
        t0 = time.time()
        with app.app_context():
            try:
                from .live_scan import cached_scan
                for db in (90, 14, 60):
                    cached_scan(days_back=db)
            except Exception as exc:
                print('Pemanasan cache live_scan gagal:', exc)
            try:
                from .kering_screener import refresh as kering_refresh
                kering_refresh()
            except Exception as exc:
                print('Pemanasan cache Kering Screener gagal:', exc)
            try:
                from .screen_eval import build_report as screen_build_report
                screen_build_report()
            except Exception as exc:
                print('Pemanasan cache Screen Eval gagal:', exc)
            # Cache memori milik /saham-data: data insider (~5 detik, dulu
            # dibayar pembuka Halaman Saham pertama) dan panel KSEI.
            try:
                from .insider_activity import load_all as insider_load_all
                insider_load_all()
            except Exception as exc:
                print('Pemanasan data insider gagal:', exc)
            try:
                from .scanner import ownership_panel
                ownership_panel()
            except Exception as exc:
                print('Pemanasan panel KSEI gagal:', exc)
        print('Cache Scanner Lab/Kering Screener/Screen Eval/insider/KSEI dipanaskan dalam %.1f detik.' % (time.time() - t0))

    threading.Thread(target=_warm, name='cache-warmup', daemon=True).start()

def create_database(app):
    # db.create_all(app=app) is the old Flask-SQLAlchemy API (removed in
    # Flask-SQLAlchemy 3.x). It now needs an active app context instead.
    #
    # create_all() only creates tables that don't exist yet â€” it never
    # touches or drops existing ones â€” so this must run every startup,
    # not just when database.db is missing. Gating it behind that check
    # meant any model added after the db file first existed (e.g.
    # WatchlistHistory) would silently never get its table created.
    with app.app_context():
        db.create_all()
        _tambah_kolom_baru()


# Kolom yang ditambahkan ke tabel yang SUDAH ADA. create_all() di atas
# hanya membuat tabel yang belum ada -- ia tidak pernah menyentuh tabel
# lama, jadi kolom baru pada model yang tabelnya sudah terlanjur dibuat
# tidak akan pernah muncul dan setiap query ke kolom itu gagal saat
# dijalankan, bukan saat start. Daftar ini yang menutup celahnya.
KOLOM_BARU = [
    ('position', 'sellPrice', 'FLOAT'),
    ('position', 'sellDate', 'DATE'),
    ('cash_balance', 'userId', 'INTEGER'),
    ('decision_snapshot', 'userId', 'INTEGER'),
]


def _tambah_kolom_baru():
    """ALTER TABLE idempoten untuk KOLOM_BARU. Aman dijalankan tiap start."""
    from sqlalchemy import inspect, text

    pemeriksa = inspect(db.engine)
    tabel_ada = set(pemeriksa.get_table_names())
    for tabel, kolom, tipe in KOLOM_BARU:
        if tabel not in tabel_ada:
            continue                      # create_all() akan membuatnya lengkap
        punya = {c['name'] for c in pemeriksa.get_columns(tabel)}
        if kolom in punya:
            continue
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE %s ADD COLUMN "%s" %s'
                              % (tabel, kolom, tipe)))
        print('Kolom ditambahkan: %s.%s' % (tabel, kolom))
    if 'cash_balance' in tabel_ada:
        with db.engine.begin() as conn:
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_cash_balance_user ON cash_balance ("userId")'))
